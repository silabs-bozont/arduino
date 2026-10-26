"""
Helpers for Matter HIL: OTBR REST, pairing-code parsing, serial waits, matter.js CLI.
"""

import json
import os
import re
import shutil
import sys
import subprocess
import time
import urllib.error
import urllib.request

import serial

from util.hil_util import bcolors

DEFAULT_OTBR_URL = "http://127.0.0.1:8081"

CONTROLLER_DIR = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "matter", "controller")
)
CONTROLLER_SCRIPT = os.path.join(CONTROLLER_DIR, "matter_hil_ctl.mjs")
MATTER_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "matter"))
SOCAT_PID_FILE = os.path.join(MATTER_DIR, "otbr_data", "rcp-socat.pid")
SOCAT_TCP_PORT = int(os.environ.get("MATTER_HIL_RCP_TCP_PORT", "9999"))


def otbr_url():
    return os.environ.get("MATTER_HIL_OTBR_URL", DEFAULT_OTBR_URL).rstrip("/")


def _http_json(method, url, body=None, accept="application/json", timeout=10):
    data = None
    headers = {"Accept": accept}
    if body is not None:
        if isinstance(body, (dict, list, str)):
            payload = body if isinstance(body, str) else json.dumps(body)
            data = payload.encode("utf-8")
            headers["Content-Type"] = "application/json"
        else:
            data = body
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="ignore")
            status = resp.status
            content_type = resp.headers.get("Content-Type", "")
            return status, raw, content_type
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", errors="ignore")
        return e.code, raw, e.headers.get("Content-Type", "")


def check_otbr_ready(timeout_s=90):
    """
    Wait until OTBR REST answers and Thread is up (or can be formed).
    Returns (ok: bool, info: dict).
    """
    base = otbr_url()
    deadline = time.time() + timeout_s
    last_err = None
    detached_tries = 0
    while time.time() < deadline:
        try:
            status, raw, _ = _http_json("GET", f"{base}/node/state")
            if status == 200:
                state = raw.strip().strip('"')
                if state in ("leader", "router", "child"):
                    return True, {"state": state}
                # Try to form / enable network
                ensure_thread_network()
                status2, raw2, _ = _http_json("GET", f"{base}/node/state")
                if status2 == 200:
                    state2 = raw2.strip().strip('"')
                    if state2 in ("leader", "router", "child"):
                        return True, {"state": state2}
                    if state2 == "detached":
                        detached_tries += 1
                        # Colima/Docker Desktop cannot run OTBR Thread netif properly.
                        if platform_is_darwin() and detached_tries >= 3:
                            return False, {
                                "error": (
                                    "OTBR stuck in state=detached on macOS. "
                                    "Colima/Docker cannot form a Thread network here "
                                    "(wpan0/netif failures). Run OTBR on Linux "
                                    "(e.g. Raspberry Pi) with the RCP, or point "
                                    "MATTER_HIL_OTBR_URL at a remote OTBR."
                                )
                            }
                last_err = f"OTBR state={state}"
            else:
                last_err = f"HTTP {status}: {raw}"
        except Exception as e:
            last_err = str(e)
        time.sleep(2)
    return False, {"error": last_err or "OTBR not ready"}


def ensure_thread_network():
    """
    Ensure an active Thread dataset exists and the interface is enabled.
    """
    base = otbr_url()
    status_state, raw_state, _ = _http_json("GET", f"{base}/node/state")
    state = raw_state.strip().strip('"') if status_state == 200 else ""

    status, raw, _ = _http_json("GET", f"{base}/node/dataset/active", accept="text/plain")
    have_dataset = status == 200 and bool(raw.strip()) and "application/json" not in ""

    if have_dataset and state in ("leader", "router", "child"):
        return

    if have_dataset and state in ("detached", "disabled", ""):
        # Dataset present but not attached — try enable; if stuck, recreate dataset
        _http_json("PUT", f"{base}/node/state", body='"enable"')
        time.sleep(2)
        status_state, raw_state, _ = _http_json("GET", f"{base}/node/state")
        state = raw_state.strip().strip('"') if status_state == 200 else ""
        if state in ("leader", "router", "child"):
            return
        print(f"OTBR stuck in state={state!r}; recreating Thread dataset", flush=True)
        _http_json("PUT", f"{base}/node/state", body='"disable"')
        time.sleep(1)

    # Create a new active dataset
    put_status, put_raw, _ = _http_json(
        "PUT",
        f"{base}/node/dataset/active",
        body={
            "NetworkName": os.environ.get("MATTER_HIL_THREAD_NAME", "SilabsMatterHIL"),
            "Channel": int(os.environ.get("MATTER_HIL_THREAD_CHANNEL", "15")),
        },
    )
    if put_status not in (200, 204):
        print(f"dataset PUT status={put_status} body={put_raw!r}; trying empty body")
        put_status, put_raw, _ = _http_json("PUT", f"{base}/node/dataset/active", body={})
        print(f"empty dataset PUT status={put_status} body={put_raw!r}")
    _http_json("PUT", f"{base}/node/state", body='"enable"')
    time.sleep(3)


def get_thread_credentials():
    """
    Returns (network_name, operational_dataset_hex) or (None, None) on failure.
    """
    base = otbr_url()
    ensure_thread_network()

    status_name, raw_name, _ = _http_json("GET", f"{base}/node/network-name")
    if status_name != 200:
        return None, None
    network_name = raw_name.strip().strip('"')

    status_ds, raw_ds, ctype = _http_json(
        "GET", f"{base}/node/dataset/active", accept="text/plain"
    )
    if status_ds == 200 and raw_ds.strip() and "application/json" not in (ctype or ""):
        dataset = raw_ds.strip().replace('"', "").replace("\n", "")
        if re.fullmatch(r"[0-9a-fA-F]+", dataset):
            return network_name, dataset.lower()

    # JSON fallback — look for ActiveTimestamp / Channel etc; prefer Hex from plain again
    status_json, raw_json, _ = _http_json("GET", f"{base}/node/dataset/active")
    if status_json == 200 and raw_json.strip():
        try:
            data = json.loads(raw_json)
            # Some OTBR builds expose NetworkName inside the dataset JSON
            if isinstance(data, dict) and data.get("NetworkName"):
                network_name = data["NetworkName"]
        except json.JSONDecodeError:
            pass

    # Last resort: docker exec ot-ctl
    dataset = _dataset_via_docker_exec()
    if dataset:
        return network_name, dataset
    return network_name or None, None


def _dataset_via_docker_exec():
    if not shutil.which("docker"):
        return None
    try:
        proc = subprocess.run(
            ["docker", "exec", "matter-hil-otbr", "ot-ctl", "dataset", "active", "-x"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        out = (proc.stdout or "") + (proc.stderr or "")
        for line in out.splitlines():
            line = line.strip()
            if re.fullmatch(r"[0-9a-fA-F]{32,}", line):
                return line.lower()
    except Exception:
        return None
    return None


def parse_pairing_from_serial(text):
    """
    Extract manual pairing code and/or QR payload from DUT serial output.
    Returns dict with keys manual_code, qr_payload (values may be None).
    """
    manual = None
    qr_payload = None
    m = re.search(r"Manual pairing code:\s*([0-9\-]+)", text)
    if m:
        manual = m.group(1).strip()
    m = re.search(r"QR code URL:.*[?&]data=([^\s&]+)", text)
    if m:
        qr_payload = m.group(1).strip()
    return {"manual_code": manual, "qr_payload": qr_payload}


def wait_for_serial_substring(port, expected, timeout_s=120, baud=115200):
    """
    Keep reading serial until expected substring appears or timeout.
    Returns (success, accumulated_text).
    """
    print("-" * 40)
    print(f"Waiting up to {timeout_s}s for serial '{expected}' on '{port}'")
    print("-" * 40)
    deadline = time.time() + timeout_s
    buf = ""
    try:
        ser = serial.Serial(port, baudrate=baud, timeout=1)
    except serial.SerialException as e:
        print(f"Error opening serial port: {e}")
        return False, ""

    try:
        while time.time() < deadline:
            chunk = ser.read(4096).decode("utf-8", errors="ignore")
            if chunk:
                print(chunk, end="" if chunk.endswith("\n") else "\n")
                buf += chunk
                if expected in buf:
                    print(f"{bcolors.OKGREEN}Found expected serial text{bcolors.ENDC}")
                    return True, buf
            else:
                time.sleep(0.2)
    finally:
        ser.close()

    print(f"{bcolors.FAIL}Timed out waiting for: {expected}{bcolors.ENDC}")
    return False, buf


def read_serial_for(port, duration_s=3, baud=115200):
    try:
        ser = serial.Serial(port, baudrate=baud, timeout=1)
    except serial.SerialException as e:
        print(f"Error opening serial port: {e}")
        return ""
    try:
        time.sleep(duration_s)
        return ser.read_all().decode("utf-8", errors="ignore")
    finally:
        ser.close()


def matter_ctl_available():
    if not os.path.isfile(CONTROLLER_SCRIPT):
        return False
    if not shutil.which("node"):
        return False
    node_modules = os.path.join(CONTROLLER_DIR, "node_modules", "@matter", "main")
    return os.path.isdir(node_modules)


def run_matter_ctl(*cli_args, timeout_s=180):
    """
    Run matter_hil_ctl.mjs and parse the last JSON line from stdout.
    Returns (ok, result_dict).
    """
    if not matter_ctl_available():
        return False, {
            "error": "matter.js controller not installed; run npm install in test/hil/matter/controller"
        }

    cmd = ["node", CONTROLLER_SCRIPT, *cli_args]
    print("-" * 40)
    print(f"Running: {' '.join(cmd)}")
    print("-" * 40)
    env = os.environ.copy()
    env.setdefault("MATTER_HIL_STORAGE", os.path.join(CONTROLLER_DIR, "storage"))

    proc = subprocess.run(
        cmd,
        cwd=CONTROLLER_DIR,
        capture_output=True,
        text=True,
        timeout=timeout_s,
        env=env,
    )
    if proc.stderr:
        print(proc.stderr)
    if proc.stdout:
        print(proc.stdout)

    result = None
    for line in reversed((proc.stdout or "").splitlines()):
        line = line.strip()
        if line.startswith("{") and line.endswith("}"):
            try:
                result = json.loads(line)
                break
            except json.JSONDecodeError:
                continue

    if result is None:
        return False, {
            "error": "no JSON result from matter_hil_ctl",
            "returncode": proc.returncode,
            "stdout": proc.stdout,
            "stderr": proc.stderr,
        }

    ok = bool(result.get("ok")) and proc.returncode == 0
    return ok, result


def preflight_matter_hil():
    """
    Check infra for the e2e lightbulb test.
    Returns (ready: bool, reason: str).
    """
    if not os.environ.get("MATTER_HIL_RCP_PORT") and not _otbr_container_running():
        # RCP port only required to start OTBR; if OTBR already up, continue
        pass

    ok, info = check_otbr_ready(timeout_s=30)
    if not ok:
        return False, f"OTBR not ready: {info}"

    if not matter_ctl_available():
        return False, "matter.js controller dependencies missing (npm install)"

    name, dataset = get_thread_credentials()
    if not name or not dataset:
        return False, "Could not read Thread network name / active dataset from OTBR"

    ok, result = run_matter_ctl(
        "ensure-ready", "--network-name", name, "--dataset", dataset, timeout_s=60
    )
    if not ok:
        return False, f"matter.js ensure-ready failed: {result}"

    return True, f"OTBR={info.get('state')} network={name}"


def _otbr_container_running():
    if not shutil.which("docker"):
        return False
    try:
        proc = subprocess.run(
            ["docker", "inspect", "-f", "{{.State.Running}}", "matter-hil-otbr"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        return proc.returncode == 0 and proc.stdout.strip() == "true"
    except Exception:
        return False





def docker_compose_cmd():
    """
    Return the base argv for Compose: prefer `docker compose` (v2 plugin),
    fall back to standalone `docker-compose`.
    """
    # Probe `docker compose version` — missing plugin yields non-zero / unknown command
    try:
        proc = subprocess.run(
            ["docker", "compose", "version"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if proc.returncode == 0:
            return ["docker", "compose"]
    except Exception:
        pass

    if shutil.which("docker-compose"):
        return ["docker-compose"]

    raise RuntimeError(
        "Neither 'docker compose' nor 'docker-compose' is available. "
        "Install Docker Compose V2 plugin or the docker-compose CLI."
    )



def _prepare_docker_env(env):
    """
    Ensure Compose can pull public images under Colima/Homebrew Docker on macOS.

    Homebrew Docker often sets credsStore=osxkeychain while the helper binary is
    missing, which breaks image pulls. Matter HIL only needs public images, so
    strip credsStore when the helper is unavailable.
    """
    import json
    import tempfile

    docker_config_dir = os.path.expanduser("~/.docker")
    config_path = os.path.join(docker_config_dir, "config.json")
    if not os.path.isfile(config_path):
        return env

    try:
        with open(config_path, "r", encoding="utf-8") as f:
            cfg = json.load(f)
    except Exception:
        return env

    creds_store = cfg.get("credsStore") or cfg.get("credStore")
    if not creds_store:
        return env

    helper_name = f"docker-credential-{creds_store}"
    if shutil.which(helper_name):
        return env

    cfg_no_creds = dict(cfg)
    cfg_no_creds.pop("credsStore", None)
    cfg_no_creds.pop("credStore", None)

    tmp_dir = tempfile.mkdtemp(prefix="matter-hil-docker-config-")
    tmp_config = os.path.join(tmp_dir, "config.json")
    with open(tmp_config, "w", encoding="utf-8") as f:
        json.dump(cfg_no_creds, f, indent=2)

    env = dict(env)
    env["DOCKER_CONFIG"] = tmp_dir
    print(
        f"Note: '{helper_name}' not in PATH; using temporary Docker config without credsStore"
    )
    return env


def _otbr_compose_overlay():
    import platform
    system = platform.system()
    if system == "Linux":
        return "docker-compose.linux.yml"
    if system == "Darwin":
        return "docker-compose.macos.yml"
    raise RuntimeError(f"Unsupported OS for OTBR: {system}")


def _otbr_compose_env(rcp_port, network_device=None):
    env = os.environ.copy()
    env["MATTER_HIL_RCP_PORT"] = rcp_port
    env.setdefault("MATTER_HIL_OTBR_BAUD", "460800")
    env.setdefault("MATTER_HIL_OTBR_FLOW", "0")
    if network_device:
        # macOS / Colima: container-side PTY created by socat-otbr-tcp
        env["MATTER_HIL_OTBR_DEVICE"] = "/tmp/ttyOTBR"
        env["MATTER_HIL_NETWORK_DEVICE"] = network_device
    else:
        env["MATTER_HIL_OTBR_DEVICE"] = rcp_port
        env["MATTER_HIL_NETWORK_DEVICE"] = ""
    if platform_is_linux() and not env.get("MATTER_HIL_BACKBONE_IF"):
        backbone = detect_backbone_iface()
        if backbone:
            env["MATTER_HIL_BACKBONE_IF"] = backbone
            print(f"Using backbone interface: {backbone}")
        else:
            env.setdefault("MATTER_HIL_BACKBONE_IF", "eth0")
    else:
        env.setdefault("MATTER_HIL_BACKBONE_IF", "eth0")
    return _prepare_docker_env(env)



def platform_is_darwin():
    import platform
    return platform.system() == "Darwin"


def macos_rcp_callout_path(rcp_port):
    """Prefer /dev/cu.* on macOS (callout) over /dev/tty.* for host socat."""
    if rcp_port.startswith("/dev/tty."):
        cu = "/dev/cu." + rcp_port[len("/dev/tty."):]
        if os.path.exists(cu):
            return cu
    return rcp_port


def start_macos_rcp_tcp_bridge(rcp_port, tcp_port=None):
    """
    Bridge host USB RCP serial <-> TCP so Colima OTBR can use NETWORK_DEVICE.
    Returns (ok, info).
    """
    tcp_port = tcp_port or SOCAT_TCP_PORT
    serial_path = macos_rcp_callout_path(rcp_port)
    baud = os.environ.get("MATTER_HIL_OTBR_BAUD", "460800")
    stop_macos_rcp_tcp_bridge()

    bridge_script = os.path.join(MATTER_DIR, "rcp_tcp_bridge.py")
    if not os.path.isfile(bridge_script):
        return False, f"missing bridge script: {bridge_script}"

    cmd = [
        sys.executable,
        bridge_script,
        "--serial",
        serial_path,
        "--port",
        str(tcp_port),
        "--baud",
        str(baud),
    ]
    print("-" * 40)
    print(f"Starting macOS RCP TCP bridge: {serial_path} <-> :{tcp_port}")
    print("-" * 40)
    log_path = os.path.join(MATTER_DIR, "otbr_data", "rcp-socat.log")
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    logf = open(log_path, "ab", buffering=0)
    proc = subprocess.Popen(cmd, stdout=logf, stderr=logf, start_new_session=True)
    time.sleep(0.8)
    if proc.poll() is not None:
        return False, f"RCP TCP bridge exited immediately; see {log_path}"

    with open(SOCAT_PID_FILE, "w", encoding="utf-8") as f:
        f.write(str(proc.pid))
    return True, f"rcp-tcp-bridge pid={proc.pid} port={tcp_port}"


def stop_macos_rcp_tcp_bridge():
    if not os.path.isfile(SOCAT_PID_FILE):
        return
    try:
        with open(SOCAT_PID_FILE, "r", encoding="utf-8") as f:
            pid = int(f.read().strip())
        os.kill(pid, 15)
        time.sleep(0.3)
        try:
            os.kill(pid, 9)
        except ProcessLookupError:
            pass
    except Exception:
        pass
    try:
        os.remove(SOCAT_PID_FILE)
    except OSError:
        pass


def platform_is_linux():
    import platform
    return platform.system() == "Linux"


def detect_backbone_iface():
    try:
        proc = subprocess.run(
            ["ip", "route", "show", "default"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if proc.returncode == 0 and proc.stdout.strip():
            parts = proc.stdout.split()
            if "dev" in parts:
                return parts[parts.index("dev") + 1]
    except Exception:
        pass
    return None


def start_otbr(rcp_port, ready_timeout_s=120):
    """
    Start the HA-style OTBR Docker container for the given RCP serial port.
    On macOS, bridges USB RCP over TCP (socat) because Colima cannot pass USB.
    Returns (ok: bool, info: str).
    """
    if not shutil.which("docker") and not shutil.which("docker-compose"):
        return False, "docker not found; install Docker Engine (Linux) or OrbStack/Colima (macOS)"

    if not rcp_port:
        return False, "RCP serial port is required"

    if not os.path.exists(rcp_port):
        return False, f"RCP serial device not found: {rcp_port}"

    os.makedirs(os.path.join(MATTER_DIR, "otbr_data"), exist_ok=True)
    overlay = _otbr_compose_overlay()
    network_device = None

    if platform_is_darwin():
        ok, info = start_macos_rcp_tcp_bridge(rcp_port)
        if not ok:
            return False, info
        print(info)
        network_device = f"host.docker.internal:{SOCAT_TCP_PORT}"

    env = _otbr_compose_env(rcp_port, network_device=network_device)
    os.environ["MATTER_HIL_RCP_PORT"] = rcp_port

    print("-" * 40)
    print(f"Starting OTBR with RCP '{rcp_port}'")
    if network_device:
        print(f"NETWORK_DEVICE={network_device} (macOS TCP bridge)")
    print("-" * 40)
    try:
        compose = docker_compose_cmd()
    except RuntimeError as e:
        if platform_is_darwin():
            stop_macos_rcp_tcp_bridge()
        return False, str(e)

    proc = subprocess.run(
        [*compose, "-f", "docker-compose.yml", "-f", overlay, "up", "-d"],
        cwd=MATTER_DIR,
        capture_output=True,
        text=True,
        timeout=180,
        env=env,
    )
    if proc.stdout:
        print(proc.stdout)
    if proc.stderr:
        print(proc.stderr)
    if proc.returncode != 0:
        if platform_is_darwin():
            stop_macos_rcp_tcp_bridge()
        return False, f"docker compose up failed (exit {proc.returncode})"

    ok, info = check_otbr_ready(timeout_s=ready_timeout_s)
    if not ok:
        # Best-effort dump of container logs for diagnosis
        try:
            logs = subprocess.run(
                ["docker", "logs", "--tail", "80", "matter-hil-otbr"],
                capture_output=True,
                text=True,
                timeout=20,
            )
            if logs.stdout or logs.stderr:
                print(logs.stdout)
                print(logs.stderr)
        except Exception:
            pass
        stop_otbr(rcp_port)
        return False, f"OTBR started but not ready: {info}"
    return True, f"OTBR ready ({info.get('state')})"


def stop_otbr(rcp_port=None):
    """
    Stop the Matter HIL OTBR container. Best-effort; returns (ok, info).
    """
    if not shutil.which("docker"):
        return False, "docker not found"

    overlay = _otbr_compose_overlay()
    port = rcp_port or os.environ.get("MATTER_HIL_RCP_PORT") or "/dev/null"
    env = _otbr_compose_env(port)

    print("-" * 40)
    print("Stopping OTBR")
    print("-" * 40)
    try:
        try:
            compose = docker_compose_cmd()
        except RuntimeError as e:
            return False, str(e)

        proc = subprocess.run(
            [*compose, "-f", "docker-compose.yml", "-f", overlay, "down"],
            cwd=MATTER_DIR,
            capture_output=True,
            text=True,
            timeout=120,
            env=env,
        )
        if proc.stdout:
            print(proc.stdout)
        if proc.stderr:
            print(proc.stderr)
        if proc.returncode != 0:
            if platform_is_darwin():
                stop_macos_rcp_tcp_bridge()
            return False, f"docker compose down failed (exit {proc.returncode})"
        if platform_is_darwin():
            stop_macos_rcp_tcp_bridge()
        return True, "OTBR stopped"
    except Exception as e:
        if platform_is_darwin():
            stop_macos_rcp_tcp_bridge()
        return False, str(e)

def sketch_path_matter_lightbulb():
    """Absolute path to the built-in matter_lightbulb example."""
    # test/hil/util -> repo root is ../../.. from util? util is test/hil/util
    # core root = test/hil/util/../../..
    core_root = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
    return os.path.join(
        core_root,
        "libraries",
        "Matter",
        "examples",
        "matter_lightbulb",
        "matter_lightbulb.ino",
    )
