# Matter HIL (MVP)

End-to-end Matter testing for the Silicon Labs Arduino Core: commission a DUT
running a built-in Matter example onto a Thread network formed by a second board
flashed as an **OpenThread RCP** plus a host **OTBR** container (HA-style), then
control it with a host-side **matter.js** controller and assert DUT Serial output.

## Hardware

| Role | Board examples | Notes |
|------|----------------|-------|
| **DUT** | Nano Matter, Thing Plus Matter, xG24, XIAO MG24 | Flashed with Matter example (`protocol_stack=matter`) |
| **RCP** | Nano Matter, Thing Plus Matter, XIAO MG24 | Flash OpenThread RCP hex once |

Flash RCP firmware (from the core tree):

```bash
python3 extra/firmware/extra_firmware_flasher.py thingplus_matter thread
# or: nano_matter / xiao_mg24
```

## Host software

- Docker with USB device access
  - **Linux**: Docker Engine (`network_mode: host`)
  - **macOS**: **OrbStack** or **Colima** (Docker Desktop cannot pass USB RCPs usefully)
- Node.js ≥ 20.19
- Host Bluetooth (for BLE commissioning)
- `arduino-cli` with Silicon Labs core installed
- Python packages used by HIL (`pyserial`, etc.)


## macOS / Colima note

**OTBR Thread formation does not work under Colima/Docker Desktop on macOS**
(OpenThread stays `detached`; `wpan0` netif fails). For Matter HIL e2e:

- Run OTBR + RCP on **Linux** (Raspberry Pi or a Linux HIL host), **or**
- Point `MATTER_HIL_OTBR_URL` at an already-running remote OTBR and skip local
  container start (future/split setup).

The runner still bridges the RCP over TCP on macOS (`rcp_tcp_bridge.py`) when
attempting a local container, but expect a fast failure if Thread never becomes
`leader`.

## One-time controller setup

```bash
cd test/hil/matter/controller
npm install
# On first BLE use, approve native scripts if prompted:
#   npm install-scripts approve @stoprocent/noble @stoprocent/bleno @stoprocent/bluetooth-hci-socket
```

## Run Matter lightbulb HIL (recommended)

Self-contained: starts OTBR, runs the lightbulb e2e test, tears OTBR down.

```bash
cd test/hil
python3 test_matter_lightbulb_hil.py <board> <dut_port> <rcp_port>
```

Example:

```bash
python3 test_matter_lightbulb_hil.py nano_matter \
    /dev/tty.usbmodem202C8AE63 /dev/tty.usbmodem0004490513501
```

Optional env (rarely needed):

| Variable | Default | Meaning |
|----------|---------|---------|
| `MATTER_HIL_OTBR_URL` | `http://127.0.0.1:8081` | OTBR REST base URL |
| `MATTER_HIL_OTBR_BAUD` | `460800` | RCP UART baud |
| `MATTER_HIL_OTBR_FLOW` | `0` | Hardware flow control (`0` for Silabs Arduino RCP) |
| `MATTER_HIL_BACKBONE_IF` | auto / `eth0` | Linux backbone interface |
| `MATTER_HIL_SKIP` | unset | Set to `1` to skip e2e when using full `test_hil.py` suite |

Manual OTBR scripts (`matter/start_otbr.sh` / `stop_otbr.sh`) remain for debugging.
The full suite (`test_hil.py`) still includes `matter_lightbulb` when OTBR is
already running; prefer `test_matter_lightbulb_hil.py` for one-shot e2e.

To exercise only the controller manually:

```bash
cd test/hil/matter/controller
node matter_hil_ctl.mjs status
node matter_hil_ctl.mjs ensure-ready --network-name NAME --dataset HEX
node matter_hil_ctl.mjs commission '34970133282'
node matter_hil_ctl.mjs onoff on
node matter_hil_ctl.mjs onoff off
node matter_hil_ctl.mjs onoff toggle
```

## What the MVP asserts

1. OTBR is up and has an active Thread dataset  
2. DUT flashes `libraries/Matter/examples/matter_lightbulb`  
3. Pairing code parsed from Serial  
4. matter.js BLE-commissions the DUT onto the OTBR Thread network  
5. Serial shows `Matter device is now online`  
6. On / Off / Toggle → Serial `Bulb ON` / `Bulb OFF` / `Bulb ON`

## Architecture

```
Host (macOS or Linux)
  HIL Python ──► DUT serial (flash + asserts)
  matter.js   ──► BLE commission + OnOff IP commands
  OTBR Docker ──► USB serial ──► RCP board
DUT ◄── Thread ──► RCP / OTBR
```

## Expanding later

Add sibling testcases for other built-in examples; reuse
`util/matter_hil_util.py` (OTBR dataset, pairing parse, serial wait, ctl wrappers).

## Local lab note (example)

On a dual-board desk setup:

| Port | Board | Role |
|------|-------|------|
| `/dev/tty.usbmodem0004490513501` | SparkFun Thing Plus Matter | RCP (`extra_firmware_flasher.py thingplus_matter thread`) |
| `/dev/tty.usbmodem202C8AE63` | Arduino Nano Matter | DUT |

```bash
cd test/hil
python3 test_matter_lightbulb_hil.py nano_matter \
    /dev/tty.usbmodem202C8AE63 /dev/tty.usbmodem0004490513501
```
