#!/usr/bin/env node
/**
 * Matter HIL controller CLI (host-side matter.js 0.18).
 *
 * Commands:
 *   ensure-ready --network-name <name> --dataset <hex>
 *   commission <manualCode|MT:...> [--network-name <name>] [--dataset <hex>]
 *   onoff on|off|toggle [--node-id <id>]
 *   reset-fabric
 *   status
 *
 * Env:
 *   MATTER_HIL_STORAGE - controller storage directory (default: ./storage)
 *   MATTER_HIL_BLE_HCI - Linux HCI adapter id (optional)
 */

import { mkdirSync, rmSync, existsSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

// Must load Node.js platform environment before any Matter APIs
import "@matter/nodejs";
import "@matter/nodejs-ble";

import { Environment, Logger, Seconds } from "@matter/general";
import {
  ControllerBehavior,
  NetworkClient,
  ServerNode,
} from "@matter/node";
import { OnOffClient } from "@matter/node/behaviors/on-off";
import { FabricAuthority, Ble } from "@matter/protocol";
import {
  ManualPairingCodeCodec,
  NodeId,
  QrPairingCodeCodec,
} from "@matter/types";
import { GeneralCommissioning } from "@matter/types/clusters";

const __dirname = dirname(fileURLToPath(import.meta.url));
const log = Logger.get("matter-hil-ctl");
const ADMIN_FABRIC_LABEL = "SilabsMatterHIL";
const CONTROLLER_ID = "matter-hil-controller";

function usage(exitCode = 1) {
  console.error(`Usage:
  matter_hil_ctl.mjs ensure-ready --network-name <name> --dataset <hex>
  matter_hil_ctl.mjs commission <manualCode|MT:...> [--network-name <name>] [--dataset <hex>]
  matter_hil_ctl.mjs onoff on|off|toggle [--node-id <id>]
  matter_hil_ctl.mjs reset-fabric
  matter_hil_ctl.mjs status`);
  process.exit(exitCode);
}

function parseArgs(argv) {
  const args = { _: [] };
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a.startsWith("--")) {
      const key = a.slice(2);
      const val = argv[i + 1] && !argv[i + 1].startsWith("--") ? argv[++i] : true;
      args[key] = val;
    } else {
      args._.push(a);
    }
  }
  return args;
}

function storageDir() {
  return resolve(process.env.MATTER_HIL_STORAGE || join(__dirname, "storage"));
}

function statePath() {
  return join(storageDir(), "hil_state.json");
}

function loadState() {
  const p = statePath();
  if (!existsSync(p)) {
    return {};
  }
  return JSON.parse(readFileSync(p, "utf8"));
}

function saveState(state) {
  mkdirSync(storageDir(), { recursive: true });
  writeFileSync(statePath(), JSON.stringify(state, null, 2));
}

function emitJson(obj) {
  console.log(JSON.stringify(obj));
}

function decodePairingCode(code) {
  const trimmed = String(code).trim();
  if (trimmed.toUpperCase().startsWith("MT:")) {
    const qr = QrPairingCodeCodec.decode(trimmed.toUpperCase())[0];
    return {
      passcode: qr.passcode,
      discriminator: qr.discriminator,
      shortDiscriminator: undefined,
    };
  }
  const digits = trimmed.replace(/[^0-9]/g, "");
  const decoded = ManualPairingCodeCodec.decode(digits);
  return {
    passcode: decoded.passcode,
    discriminator: undefined,
    shortDiscriminator: decoded.shortDiscriminator,
  };
}

async function createController({ enableBle = false } = {}) {
  mkdirSync(storageDir(), { recursive: true });
  const environment = Environment.default;

  // Point StorageService at our HIL storage directory
  environment.vars.set("path.root", storageDir());
  if (enableBle) {
    environment.vars.set("ble.enable", true);
    const hci = process.env.MATTER_HIL_BLE_HCI;
    if (hci !== undefined && hci !== "") {
      environment.vars.set("ble.hci.id", Number(hci));
    }
  }

  const bleEnabled = enableBle && environment.maybeGet(Ble) !== undefined;

  const nodeEnvironment = new Environment(CONTROLLER_ID, environment);
  const node = await ServerNode.create(
    ServerNode.RootEndpointWithoutGroupcast.with(ControllerBehavior),
    {
      environment: nodeEnvironment,
      id: CONTROLLER_ID,
      network: {
        ble: false,
        tcp: true,
        autoStartCommissionedPeers: false,
      },
      basicInformation: {
        productName: ADMIN_FABRIC_LABEL,
      },
      controller: {
        adminFabricLabel: ADMIN_FABRIC_LABEL,
        ble: bleEnabled,
      },
      commissioning: {
        enabled: false,
      },
      subscriptions: {
        persistenceEnabled: false,
      },
    },
  );

  const fabricAuthority = await node.env.load(FabricAuthority);
  await fabricAuthority.defaultFabric({ adminFabricLabel: ADMIN_FABRIC_LABEL });
  await node.start();

  return { node, environment, bleEnabled };
}

async function closeController(node) {
  try {
    await node?.close();
  } catch (e) {
    log.warn(`Controller close warning: ${e}`);
  }
}

async function cmdEnsureReady(args) {
  const networkName = args["network-name"] || process.env.MATTER_HIL_THREAD_NAME;
  const dataset = args.dataset || process.env.MATTER_HIL_THREAD_DATASET;
  if (!networkName || !dataset) {
    throw new Error(
      "ensure-ready requires --network-name and --dataset (or env MATTER_HIL_THREAD_NAME / MATTER_HIL_THREAD_DATASET)",
    );
  }
  const state = loadState();
  state.threadNetworkName = networkName;
  state.threadOperationalDataset = String(dataset).replace(/\s+/g, "").toLowerCase();
  saveState(state);

  const { node } = await createController({ enableBle: false });
  try {
    const commissioned = node.peers.commissioned.map((p) => String(p.peerAddress?.nodeId ?? p.id));
    emitJson({
      ok: true,
      command: "ensure-ready",
      threadNetworkName: state.threadNetworkName,
      datasetLength: state.threadOperationalDataset.length,
      commissionedNodes: commissioned,
    });
  } finally {
    await closeController(node);
  }
}

async function cmdCommission(args) {
  const pairing = args._[1];
  if (!pairing) {
    usage();
  }
  const state = loadState();
  const networkName =
    args["network-name"] || state.threadNetworkName || process.env.MATTER_HIL_THREAD_NAME;
  const dataset = (
    args.dataset ||
    state.threadOperationalDataset ||
    process.env.MATTER_HIL_THREAD_DATASET ||
    ""
  )
    .replace(/\s+/g, "")
    .toLowerCase();
  if (!networkName || !dataset) {
    throw new Error(
      "Thread credentials missing; run ensure-ready first or pass --network-name/--dataset",
    );
  }

  const ids = decodePairingCode(pairing);
  const { node, bleEnabled } = await createController({ enableBle: true });
  if (!bleEnabled) {
    await closeController(node);
    throw new Error(
      "BLE is not available on this host (matter.js Ble transport not installed). Enable Bluetooth and ensure @matter/nodejs-ble native deps built.",
    );
  }

  try {
    const commissioningOptions = {
      passcode: ids.passcode,
      discriminator: ids.discriminator,
      shortDiscriminator: ids.shortDiscriminator,
      autoSubscribe: false,
      regulatoryLocation: GeneralCommissioning.RegulatoryLocationType.IndoorOutdoor,
      regulatoryCountryCode: "XX",
      onAttestationFailure: () => true, // accept development/test certificates
      threadNetwork: {
        networkName,
        operationalDataset: dataset,
      },
      timeout: Seconds(120),
    };

    // Remove undefined discriminator fields
    if (commissioningOptions.discriminator === undefined) {
      delete commissioningOptions.discriminator;
    }
    if (commissioningOptions.shortDiscriminator === undefined) {
      delete commissioningOptions.shortDiscriminator;
    }

    const peer = await node.peers.commission({
      ...commissioningOptions,
      discoveryCapabilities: { ble: true, onIpNetwork: true },
    });

    const nodeId = peer.peerAddress?.nodeId;
    state.lastNodeId = String(nodeId);
    state.threadNetworkName = networkName;
    state.threadOperationalDataset = dataset;
    saveState(state);

    emitJson({
      ok: true,
      command: "commission",
      nodeId: String(nodeId),
      threadNetworkName: networkName,
    });
  } finally {
    await closeController(node);
  }
}

async function cmdOnoff(args) {
  const action = (args._[1] || "").toLowerCase();
  if (!["on", "off", "toggle"].includes(action)) {
    usage();
  }
  const state = loadState();
  const nodeIdStr = args["node-id"] || state.lastNodeId;
  if (!nodeIdStr) {
    throw new Error("No node id; commission a device first or pass --node-id");
  }

  const { node } = await createController({ enableBle: false });
  try {
    const nodeId = NodeId(BigInt(nodeIdStr));
    const peer = node.peers.commissioned.find((p) => p.peerAddress?.nodeId === nodeId);
    if (!peer) {
      throw new Error(`Node ${nodeIdStr} is not commissioned on this controller fabric`);
    }

    await peer.setStateOf(NetworkClient, { autoSubscribe: false });
    if (peer.stateOf(NetworkClient).isDisabled) {
      await peer.enable();
    } else {
      await peer.start();
    }

    // Wait briefly for endpoint structure
    const deadline = Date.now() + 60000;
    while (Date.now() < deadline) {
      const eps = [...peer.endpoints].filter((ep) => ep.number !== 0 && ep.behaviors.has(OnOffClient));
      if (eps.length > 0) {
        const ep = eps[0];
        const cmds = ep.commandsOf(OnOffClient);
        if (action === "on") {
          await cmds.on();
        } else if (action === "off") {
          await cmds.off();
        } else {
          await cmds.toggle();
        }
        emitJson({
          ok: true,
          command: "onoff",
          action,
          nodeId: nodeIdStr,
          endpoint: ep.number,
        });
        return;
      }
      await new Promise((r) => setTimeout(r, 500));
    }
    throw new Error("Timed out waiting for OnOff endpoint on commissioned node");
  } finally {
    await closeController(node);
  }
}

async function cmdResetFabric() {
  const dir = storageDir();
  if (existsSync(dir)) {
    rmSync(dir, { recursive: true, force: true });
  }
  mkdirSync(dir, { recursive: true });
  emitJson({ ok: true, command: "reset-fabric", storage: dir });
}

async function cmdStatus() {
  const state = loadState();
  let commissionedNodes = [];
  let bleAvailable = false;
  try {
    const { node, bleEnabled } = await createController({ enableBle: true });
    bleAvailable = bleEnabled;
    commissionedNodes = node.peers.commissioned.map((p) => String(p.peerAddress?.nodeId ?? p.id));
    await closeController(node);
  } catch (e) {
    // ignore if storage empty / BLE unavailable for status
  }
  emitJson({
    ok: true,
    command: "status",
    storage: storageDir(),
    threadNetworkName: state.threadNetworkName || null,
    hasDataset: Boolean(state.threadOperationalDataset),
    lastNodeId: state.lastNodeId || null,
    commissionedNodes,
    bleAvailable,
  });
}

async function main() {
  // Keep stdout mostly JSON; matter.js logs go to stderr via Logger
  Logger.level = "warn";
  const args = parseArgs(process.argv.slice(2));
  const cmd = args._[0];
  if (!cmd) {
    usage();
  }

  switch (cmd) {
    case "ensure-ready":
      await cmdEnsureReady(args);
      break;
    case "commission":
      await cmdCommission(args);
      break;
    case "onoff":
      await cmdOnoff(args);
      break;
    case "reset-fabric":
      await cmdResetFabric();
      break;
    case "status":
      await cmdStatus();
      break;
    case "help":
    case "--help":
    case "-h":
      usage(0);
      break;
    default:
      console.error(`Unknown command: ${cmd}`);
      usage();
  }
}

main().catch((err) => {
  emitJson({ ok: false, error: String(err?.stack || err) });
  process.exit(1);
});
