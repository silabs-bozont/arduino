"""
Helpers for Matter HIL against a Silicon Labs Matter Hub (Raspberry Pi).

Uses SSH + chip-tool on the Pi (official SilabsMatterPi image).
Opt-in: set otbr_host via test_hil.py --matter-otbr <ip>.
SSH password is prompted once (or taken from MATTER_OTBR_SSH_PASSWORD) and kept
in memory for the process lifetime — never written to disk by this module.
"""

import getpass
import math
import os
import re
import shlex
import subprocess
import tempfile

# Set by test_hil.py when --matter-otbr <ip> is provided; None means Matter HIL is skipped.
otbr_host = None
# Runtime-only SSH password (getpass / env); not persisted.
otbr_password = None

DEFAULT_SSH_USER = "ubuntu"
DEFAULT_NODE_ID = 100
# Arduino Matter dynamic endpoints start after the ZAP placeholder (endpoint 2) → first appliance is 3
DEFAULT_ENDPOINT = 3
# Arduino Matter examples use the CHIP development defaults (same as mattertool).
DEFAULT_PINCODE = "20202021"
DEFAULT_DISCRIMINATOR = "3840"
# Prefer the prebuilt chip-tool binary directly (avoids matterTool.sh → activate.sh).
CHIPTOOL_PATH = "$HOME/connectedhomeip/out/standalone/chip-tool"
# Matter LevelControl CurrentLevel range used by Arduino MatterDimmableLightbulb
LEVEL_CONTROL_MAX = 254


def percent_to_matter_level(percent):
    """
    Match MatterDimmableLightbulb::set_brightness_percent():
    ceil(percent * max_level / 100), percent clamped to 0-100.
    """
    percent = max(0, min(100, int(percent)))
    return int(math.ceil(percent * LEVEL_CONTROL_MAX / 100.0))


def is_enabled():
    return bool(otbr_host)


def ssh_user():
    return os.environ.get("MATTER_OTBR_SSH_USER", DEFAULT_SSH_USER)


def ensure_ssh_password():
    """
    Load SSH password into otbr_password for this process only.
    Prefer MATTER_OTBR_SSH_PASSWORD if set; otherwise prompt once via getpass.
    """
    global otbr_password
    if otbr_password:
        return otbr_password

    env_pw = os.environ.get("MATTER_OTBR_SSH_PASSWORD")
    if env_pw:
        otbr_password = env_pw
        return otbr_password

    otbr_password = getpass.getpass(
        f"SSH password for {ssh_user()}@{otbr_host}: "
    )
    return otbr_password


def ssh_run(remote_command, timeout=180):
    """
    Run a command on the Matter Hub over SSH.
    Uses an in-memory password via SSH_ASKPASS (no sshpass / no password on disk).
    Falls back to key/agent auth if no password is configured.
    """
    if not otbr_host:
        raise RuntimeError("Matter OTBR host is not configured (--matter-otbr)")

    ssh_cmd = [
        "ssh",
        "-o", "StrictHostKeyChecking=accept-new",
        "-o", "ConnectTimeout=15",
        "-o", "NumberOfPasswordPrompts=1",
        f"{ssh_user()}@{otbr_host}",
        remote_command,
    ]

    env = os.environ.copy()
    askpass_path = None
    if otbr_password:
        # Force OpenSSH to call ASKPASS instead of a TTY prompt (non-interactive HIL).
        askpass = tempfile.NamedTemporaryFile("w", delete=False, prefix="hil_ssh_askpass_", suffix=".sh")
        askpass.write("#!/bin/sh\nprintf '%s\\n' \"$MATTER_OTBR_SSH_ASKPASS_PASSWORD\"\n")
        askpass.close()
        os.chmod(askpass.name, 0o700)
        askpass_path = askpass.name
        env["MATTER_OTBR_SSH_ASKPASS_PASSWORD"] = otbr_password
        env["SSH_ASKPASS"] = askpass_path
        env["SSH_ASKPASS_REQUIRE"] = "force"
        env.setdefault("DISPLAY", ":0")
        # Prefer password auth when a password was supplied
        ssh_cmd[1:1] = [
            "-o", "PreferredAuthentications=password",
            "-o", "PubkeyAuthentication=no",
        ]
    else:
        ssh_cmd[1:1] = ["-o", "BatchMode=yes"]

    try:
        proc = subprocess.run(
            ssh_cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env,
            stdin=subprocess.DEVNULL,
        )
    finally:
        if askpass_path:
            try:
                os.unlink(askpass_path)
            except OSError:
                pass

    if proc.stdout:
        print(proc.stdout)
    if proc.stderr:
        print(proc.stderr)
    if proc.returncode != 0:
        print(f"SSH command failed with exit code {proc.returncode}")
        return False, proc.stdout + proc.stderr
    return True, proc.stdout + proc.stderr


def ssh_bash(script, timeout=180):
    """Run a bash script on the Pi in a login shell (loads PATH; no alias reliance)."""
    remote = f"bash -lc {shlex.quote(script)}"
    return ssh_run(remote, timeout=timeout)


def check_ssh_connectivity():
    """Check if SSH connectivity to the Matter hub is available."""
    print("-" * 40)
    print(f"Checking remote connectivity to Matter hub ({ssh_user()}@{otbr_host})")
    print("-" * 40)
    ok, _ = ssh_run("echo matter-otbr-ok", timeout=30)
    if ok:
        print("Connectivity to Matter hub is available")
    else:
        print("Connection to Matter hub failed")
    return ok


def parse_pairing_codes_from_text(serial_text):
    """
    Extract manual pairing code digits and optional QR MT: payload from DUT serial output.
    Returns (manual_code_digits_or_None, qr_payload_or_None).
    """
    manual = None
    qr = None

    m = re.search(r"Manual pairing code:\s*([0-9\-]+)", serial_text)
    if m:
        manual = re.sub(r"\D", "", m.group(1))

    m = re.search(r"[?&]data=(MT:[^\s&]+)", serial_text)
    if m:
        qr = m.group(1)

    return manual, qr


def parse_setup_payload_on_pi(payload):
    """
    Ask chip-tool on the Pi to parse a manual code or MT: QR payload.
    Returns (pincode, discriminator) or (None, None).
    """
    script = f"{CHIPTOOL_PATH} payload parse-setup-payload {shlex.quote(payload)}"
    ok, output = ssh_bash(script, timeout=60)
    if not ok:
        return None, None

    pincode = None
    discriminator = None

    m = re.search(r"Passcode:\s*(\d+)", output, re.IGNORECASE)
    if m:
        pincode = m.group(1)

    # Prefer long discriminator when present
    m = re.search(r"Long discriminator:\s*(\d+)", output, re.IGNORECASE)
    if m:
        discriminator = m.group(1)
    else:
        m = re.search(r"Discriminator:\s*(\d+)", output, re.IGNORECASE)
        if m:
            discriminator = m.group(1)

    if pincode is None or discriminator is None:
        print("Failed to parse passcode/discriminator from chip-tool output")
        return None, None

    print(f"Parsed Passcode={pincode} Discriminator={discriminator}")
    return pincode, discriminator


def start_thread_and_commission(pincode, discriminator, node_id=DEFAULT_NODE_ID):
    """
    On the Pi: start a fresh Thread network (ot-ctl), then BLE-Thread commission the DUT.
    Mirrors mattertool startThread + bleThread without sourcing activate.sh.
    """
    script = f"""
set -e
CHIPTOOL={CHIPTOOL_PATH}
PINCODE={shlex.quote(str(pincode))}
DISCRIMINATOR={shlex.quote(str(discriminator))}
NODE_ID={int(node_id)}

# Clear prior chip-tool session state so re-commissioning is reliable
rm -rf /tmp/chip_* 2>/dev/null || true

echo "Starting a new Thread network"
sudo ot-ctl factoryreset
sleep 3
sudo ot-ctl srp server disable
sudo ot-ctl thread stop
sudo ot-ctl ifconfig down
sudo ot-ctl dataset init new
sudo ot-ctl dataset commit active
sudo ot-ctl srp server enable
sudo ot-ctl ifconfig up
sudo ot-ctl thread start
sleep 7
THREAD_DATA_SET=$(sudo ot-ctl dataset active -x | sed -n 1p | tr -d '\\r')
echo "Thread dataset: $THREAD_DATA_SET"
if [ -z "$THREAD_DATA_SET" ] || [ "$THREAD_DATA_SET" = "Error" ]; then
  echo "Failed to read Thread dataset"
  exit 1
fi

echo "Commissioning node $NODE_ID over BLE-Thread"
"$CHIPTOOL" pairing ble-thread "$NODE_ID" hex:"$THREAD_DATA_SET" "$PINCODE" "$DISCRIMINATOR" --bypass-attestation-verifier true
echo "COMMISSION_OK node=$NODE_ID"
"""
    print("-" * 40)
    print(f"Setting up Thread network and commissioning node with ID '{node_id}'")
    print("-" * 40)

    ok, output = ssh_bash(script, timeout=300)
    if not ok or "COMMISSION_OK" not in output:
        print("Thread start / BLE commissioning failed")
        return False
    return True


def matter_onoff(on, node_id=DEFAULT_NODE_ID, endpoint=DEFAULT_ENDPOINT):
    print("-" * 40)
    print(f"Sending Matter on/off command: {'ON' if on else 'OFF'} to node {node_id}, endpoint {endpoint}")
    print("-" * 40)
    cmd = "on" if on else "off"
    script = f"{CHIPTOOL_PATH} onoff {cmd} {int(node_id)} {int(endpoint)}"
    ok, _ = ssh_bash(script, timeout=60)
    return ok


def matter_read_onoff(node_id=DEFAULT_NODE_ID, endpoint=DEFAULT_ENDPOINT):
    """
    Read the OnOff attribute. Arduino Matter marks the appliance online only
    after an external attribute read (see emberAfExternalAttributeReadCallback).
    """
    print("-" * 40)
    print(f"Reading Matter on/off attribute from node {node_id}, endpoint {endpoint}")
    print("-" * 40)
    script = f"{CHIPTOOL_PATH} onoff read on-off {int(node_id)} {int(endpoint)}"
    ok, _ = ssh_bash(script, timeout=60)
    return ok


def matter_move_to_level(level, node_id=DEFAULT_NODE_ID, endpoint=DEFAULT_ENDPOINT):
    """
    LevelControl move-to-level (CurrentLevel is 0-254 on Arduino Matter bulbs).
    """
    level = max(0, min(LEVEL_CONTROL_MAX, int(level)))
    print("-" * 40)
    print(f"Sending Matter move-to-level {level} to node {node_id}, endpoint {endpoint}")
    print("-" * 40)
    # Level, TransitionTime, OptionsMask, OptionsOverride, node, endpoint
    script = (
        f"{CHIPTOOL_PATH} levelcontrol move-to-level "
        f"{level} 0 0 0 {int(node_id)} {int(endpoint)}"
    )
    ok, _ = ssh_bash(script, timeout=60)
    return ok


def matter_set_brightness_percent(percent, node_id=DEFAULT_NODE_ID, endpoint=DEFAULT_ENDPOINT):
    """Set dimmable bulb brightness to a 0-100 percent via LevelControl."""
    level = percent_to_matter_level(percent)
    print(f"Brightness {percent}% -> Matter level {level}")
    return matter_move_to_level(level, node_id=node_id, endpoint=endpoint)


def matter_read_temperature_celsius(node_id=DEFAULT_NODE_ID, endpoint=DEFAULT_ENDPOINT):
    """
    Read TemperatureMeasurement MeasuredValue via chip-tool.
    Matter encodes the value in hundredths of a degree Celsius (int16).
    Returns (success, celsius_float_or_None).
    """
    print("-" * 40)
    print(f"Reading Matter temperature from node {node_id}, endpoint {endpoint}")
    print("-" * 40)
    script = (
        f"{CHIPTOOL_PATH} temperaturemeasurement read measured-value "
        f"{int(node_id)} {int(endpoint)}"
    )
    ok, output = ssh_bash(script, timeout=60)
    if not ok:
        return False, None

    m = re.search(r"MeasuredValue:\s*(-?\d+)", output)
    if not m:
        print("Failed to parse MeasuredValue from chip-tool output")
        return False, None

    raw = int(m.group(1))
    celsius = raw / 100.0
    print(f"MeasuredValue raw={raw} -> {celsius:.2f} C")
    return True, celsius


def commission_with_defaults(node_id=DEFAULT_NODE_ID):
    """
    Start Thread on the Pi and BLE-commission the DUT using the default
    development passcode/discriminator (skips reading pairing codes from Serial).
    """
    print(
        f"Commissioning with defaults: "
        f"PINCODE={DEFAULT_PINCODE} DISCRIMINATOR={DEFAULT_DISCRIMINATOR} NODE_ID={node_id}"
    )
    return start_thread_and_commission(
        DEFAULT_PINCODE, DEFAULT_DISCRIMINATOR, node_id=node_id
    )


def commission_from_serial_text(serial_text, node_id=DEFAULT_NODE_ID):
    """
    Parse pairing info from DUT serial, resolve passcode/discriminator on the Pi,
    start Thread, and commission over BLE.
    """
    manual, qr = parse_pairing_codes_from_text(serial_text)
    payload = qr or manual
    if not payload:
        print("No manual pairing code or QR payload found in serial output")
        return False

    print(f"Using setup payload: {payload}")
    pincode, discriminator = parse_setup_payload_on_pi(payload)
    if pincode is None:
        return False

    return start_thread_and_commission(pincode, discriminator, node_id=node_id)
