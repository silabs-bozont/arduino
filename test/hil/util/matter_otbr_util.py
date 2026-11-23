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
import time

# Set by test_hil.py when --matter-otbr <ip> is provided; None means Matter HIL is skipped.
otbr_host = None
# Runtime-only SSH password (getpass / env); not persisted.
otbr_password = None

DEFAULT_SSH_USER = "ubuntu"
DEFAULT_NODE_ID = 100
# Arduino Matter dynamic endpoints start after the ZAP placeholder (endpoint 2) → first appliance is 3
DEFAULT_ENDPOINT = 3
# Time Synchronization cluster lives on the root endpoint
ROOT_ENDPOINT = 0
# Unix seconds for 2000-01-01T00:00:00Z (Matter epoch base)
MATTER_EPOCH_UNIX_S = 946684800
# Arduino Matter examples use the CHIP development defaults (same as mattertool).
DEFAULT_PINCODE = "20202021"
DEFAULT_DISCRIMINATOR = "3840"
# Prefer the prebuilt chip-tool binary directly (avoids matterTool.sh → activate.sh).
CHIPTOOL_PATH = "$HOME/connectedhomeip/out/standalone/chip-tool"
# Matter LevelControl CurrentLevel range used by Arduino MatterDimmableLightbulb
LEVEL_CONTROL_MAX = 254
# TimeSynchronization::GranularityEnum / TimeSourceEnum used by SetUTCTime HIL
TIME_GRANULARITY_MILLISECONDS = 3
TIME_SOURCE_ADMIN = 2


def percent_to_matter_level(percent):
    """
    Match MatterDimmableLightbulb::set_brightness_percent():
    ceil(percent * max_level / 100), percent clamped to 0-100.
    """
    percent = max(0, min(100, int(percent)))
    return int(math.ceil(percent * LEVEL_CONTROL_MAX / 100.0))


def latest_serial_float(monitor, pattern, group=1):
    """Return the last float captured by pattern in the SerialMonitor buffer, or None."""
    last = None
    for match in pattern.finditer(monitor.text()):
        last = float(match.group(group))
    return last


def matter_matches_serial_or_steps_ahead(
    serial_value,
    matter_value,
    step,
    max_steps_ahead=2,
    wrap_above=None,
    wrap_below=None,
    wrap_to=0.0,
    tol=0.5,
):
    """
    Compare a Matter attribute read to a Serial snapshot for stepped sensors.

    chip-tool is often slow enough that the DUT publishes 1-2 more increments
    before the read returns, so Matter can be ahead of Serial. Accept equality
    or Matter == Serial advanced by 1..max_steps_ahead steps (step may be
    negative for discharging sensors). Optional wrap:
      step > 0 and next > wrap_above -> wrap_to
      step < 0 and next < wrap_below -> wrap_to
    Reject Matter lagging behind Serial.
    """
    v = float(serial_value)
    matter_value = float(matter_value)
    step = float(step)
    for _ in range(int(max_steps_ahead) + 1):
        if abs(matter_value - v) <= float(tol):
            return True
        nxt = v + step
        if step > 0 and wrap_above is not None and nxt > float(wrap_above):
            v = float(wrap_to)
        elif step < 0 and wrap_below is not None and nxt < float(wrap_below):
            v = float(wrap_to)
        else:
            v = nxt
    return False


def matter_matches_monitor_serial_or_steps_ahead(
    monitor,
    serial_re,
    matter_value,
    step,
    fallback_serial=None,
    group=1,
    max_steps_ahead=2,
    wrap_above=None,
    wrap_below=None,
    wrap_to=0.0,
    tol=0.5,
):
    """
    Like matter_matches_serial_or_steps_ahead, but rebases against the latest
    Serial line in the monitor. chip-tool retries (e.g. 70s busy wait) let the
    DUT keep stepping; comparing to a stale Serial snapshot then fails even
    when Matter is correct. Prefer the newest Serial value; fall back to
    fallback_serial if the buffer has no match.
    """
    serial_value = latest_serial_float(monitor, serial_re, group=group)
    if serial_value is None:
        serial_value = fallback_serial
    if serial_value is None:
        return False
    if fallback_serial is not None and abs(float(serial_value) - float(fallback_serial)) > float(tol):
        print(
            f"Serial baseline refreshed for Matter compare: "
            f"{fallback_serial} -> {serial_value}"
        )
    return matter_matches_serial_or_steps_ahead(
        serial_value,
        matter_value,
        step,
        max_steps_ahead=max_steps_ahead,
        wrap_above=wrap_above,
        wrap_below=wrap_below,
        wrap_to=wrap_to,
        tol=tol,
    )


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
        try:
            proc = subprocess.run(
                ssh_cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                env=env,
                stdin=subprocess.DEVNULL,
            )
        except subprocess.TimeoutExpired as e:
            # Treat hangs (OTBR/IPv6 unreachable mid chip-tool) as failure so
            # chiptool_run / commissioning can retry instead of crashing HIL.
            stdout = e.stdout or ""
            stderr = e.stderr or ""
            if isinstance(stdout, bytes):
                stdout = stdout.decode("utf-8", errors="ignore")
            if isinstance(stderr, bytes):
                stderr = stderr.decode("utf-8", errors="ignore")
            print(f"SSH command timed out after {timeout}s")
            if stdout:
                print(stdout)
            if stderr:
                print(stderr)
            return False, stdout + stderr
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


# chip-tool default commissioning window is ~120s; CASE retries after a Thread
# join flake can need longer (seen: Network is unreachable → busy → retry ~103s).
PAIRING_TIMEOUT_S = 300
COMMISSION_ATTEMPTS = 2
COMMISSION_RETRY_DELAY_S = 15

# Operational chip-tool reads/writes: same OTBR/IPv6 "Network is unreachable" flake.
# After a mid-CASE failure the DUT often returns busy with ~65535 ms wait — a 5s
# retry then fails immediately. Wait out that window before the second attempt.
CHIPTOOL_ATTEMPTS = 5
CHIPTOOL_RETRY_DELAY_S = 5
CHIPTOOL_CASE_RETRY_DELAY_S = 70
CHIPTOOL_CMD_TIMEOUT_S = 60
# Leave headroom under the SSH timeout so chip-tool can exit cleanly.
CHIPTOOL_INTERACTIVE_TIMEOUT_S = 45


def _chiptool_case_flake(output):
    text = (output or "").lower()
    return any(
        needle in text
        for needle in (
            "network is unreachable",
            "resource is busy",
            "case session",
            "timed out",
            "timeout",
        )
    )


def _chiptool_retry_delay_s(output):
    """Prefer DUT-reported busy wait; otherwise a CASE-flake default or short delay."""
    m = re.search(r"minimum wait time:\s*(\d+)\s*ms", output or "", re.IGNORECASE)
    if m:
        # +1s slack past the advertised busy window
        return max(CHIPTOOL_RETRY_DELAY_S, int(math.ceil(int(m.group(1)) / 1000.0) + 1))
    if _chiptool_case_flake(output):
        return CHIPTOOL_CASE_RETRY_DELAY_S
    return CHIPTOOL_RETRY_DELAY_S


def _kill_stale_chiptool():
    """
    Stop a chip-tool left running after an SSH timeout mid-CASE.

    Use killall (not pkill -f): a -f pattern matching the chip-tool path also
    matches this SSH remote command line and can kill the cleanup shell itself
    (SSH exit 255), which looked like a hung retry.
    """
    print("Clearing any leftover chip-tool process on the Matter Hub")
    # killall -q: quiet if none; || true: never fail the HIL helper
    ssh_bash("killall -q chip-tool 2>/dev/null || true", timeout=15)


def chiptool_run(script, timeout=CHIPTOOL_CMD_TIMEOUT_S):
    """
    Run a chip-tool command on the Pi; retry once on failure.

    CASE/IPv6 flakes kill connectivity mid-handshake and leave the DUT busy; the
    retry waits out that busy window and clears any leftover chip-tool process.
    """
    if "--timeout" not in script:
        script = f"{script} --timeout {int(CHIPTOOL_INTERACTIVE_TIMEOUT_S)}"

    output = ""
    for attempt in range(1, CHIPTOOL_ATTEMPTS + 1):
        ok, output = ssh_bash(script, timeout=timeout)
        if ok:
            return True, output
        if attempt < CHIPTOOL_ATTEMPTS:
            delay = _chiptool_retry_delay_s(output)
            print(
                f"chip-tool command failed (attempt {attempt}/{CHIPTOOL_ATTEMPTS}); "
                f"will retry once after DUT CASE/busy settle"
            )
            _kill_stale_chiptool()
            print(
                f"Waiting {delay}s before chip-tool retry "
                f"(DUT busy window after Network is unreachable / CASE abort)..."
            )
            time.sleep(delay)
            print(f"Retrying chip-tool (attempt {attempt + 1}/{CHIPTOOL_ATTEMPTS})")
    return False, output


def _start_thread_and_commission_once(pincode, discriminator, node_id=DEFAULT_NODE_ID):
    """
    On the Pi: reset hub state, start a fresh Thread network, then BLE-Thread
    commission the DUT. Mirrors mattertool startThread + bleThread without
    sourcing activate.sh.
    """
    script = f"""
set -e
CHIPTOOL={CHIPTOOL_PATH}
PINCODE={shlex.quote(str(pincode))}
DISCRIMINATOR={shlex.quote(str(discriminator))}
NODE_ID={int(node_id)}
PAIRING_TIMEOUT={int(PAIRING_TIMEOUT_S)}

echo "Resetting Matter Hub state before commissioning"
# Leftover chip-tool from a timed-out SSH session can confuse the next pair
killall -q chip-tool 2>/dev/null || true
# Clear prior chip-tool session / fabric state so re-commissioning is reliable
rm -rf /tmp/chip_* 2>/dev/null || true

# Bounce OTBR: clears sticky Thread/IPv6 border routes that cause mid-CASE
# "Network is unreachable" after the DUT joins Thread
if command -v systemctl >/dev/null 2>&1; then
  sudo systemctl restart otbr-agent
  # otbr-agent needs a moment before ot-ctl talks to the RCP again
  sleep 8
fi

# BLE HCI often needs a kick after a failed pairing (hciuart / stale connections)
if command -v hciconfig >/dev/null 2>&1; then
  sudo hciconfig hci0 down 2>/dev/null || true
  sleep 1
  sudo hciconfig hci0 up 2>/dev/null || true
elif command -v bluetoothctl >/dev/null 2>&1; then
  sudo bluetoothctl power off >/dev/null 2>&1 || true
  sleep 1
  sudo bluetoothctl power on >/dev/null 2>&1 || true
fi
sleep 2

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

# Wait until we are leader/router so border routing is up before CASE over Thread
THREAD_READY=0
for _i in $(seq 1 30); do
  STATE=$(sudo ot-ctl state 2>/dev/null | sed -n 1p | tr -d '\\r')
  echo "Thread state: $STATE"
  case "$STATE" in
    leader|router)
      THREAD_READY=1
      break
      ;;
  esac
  sleep 1
done
if [ "$THREAD_READY" != 1 ]; then
  echo "Thread network did not become leader/router in time"
  exit 1
fi
# Extra settle for on-mesh / off-mesh IPv6 routes via OTBR
sleep 5

THREAD_DATA_SET=$(sudo ot-ctl dataset active -x | sed -n 1p | tr -d '\\r')
echo "Thread dataset: $THREAD_DATA_SET"
if [ -z "$THREAD_DATA_SET" ] || [ "$THREAD_DATA_SET" = "Error" ]; then
  echo "Failed to read Thread dataset"
  exit 1
fi

echo "Commissioning node $NODE_ID over BLE-Thread"
"$CHIPTOOL" pairing ble-thread "$NODE_ID" hex:"$THREAD_DATA_SET" "$PINCODE" "$DISCRIMINATOR" \\
  --bypass-attestation-verifier true --timeout "$PAIRING_TIMEOUT"
echo "COMMISSION_OK node=$NODE_ID"
"""
    print("-" * 40)
    print(f"Setting up Thread network and commissioning node with ID '{node_id}'")
    print("-" * 40)

    # SSH must outlive chip-tool's pairing timeout + OTBR/Thread bring-up
    ok, output = ssh_bash(script, timeout=PAIRING_TIMEOUT_S + 120)
    if not ok or "COMMISSION_OK" not in output:
        print("Thread start / BLE commissioning failed")
        return False
    return True


def start_thread_and_commission(
    pincode, discriminator, node_id=DEFAULT_NODE_ID, before_retry=None
):
    """
    Fresh Thread network + BLE-Thread commission, with one retry.

    OTBR/IPv6 can flake mid-CASE after Thread join ("Network is unreachable").
    Retry uses a new Thread dataset (ot-ctl factoryreset). Pass before_retry to
    also reset the DUT (clear failsafe/fabric, restore BLE advertising) — see
    hil_util.prepare_matter_dut_recommission.
    """
    for attempt in range(1, COMMISSION_ATTEMPTS + 1):
        if attempt > 1:
            print(
                f"Commissioning attempt {attempt}/{COMMISSION_ATTEMPTS}: "
                f"fresh Thread network after {COMMISSION_RETRY_DELAY_S}s"
            )
            if before_retry is not None:
                print("Running before_retry hook (DUT recommission prepare)")
                if not before_retry():
                    print("before_retry hook failed")
                    return False
            time.sleep(COMMISSION_RETRY_DELAY_S)

        if _start_thread_and_commission_once(pincode, discriminator, node_id=node_id):
            return True

        if attempt < COMMISSION_ATTEMPTS:
            print(
                "Commissioning failed; will retry once with a new Thread network"
            )

    return False


def matter_onoff(on, node_id=DEFAULT_NODE_ID, endpoint=DEFAULT_ENDPOINT):
    print("-" * 40)
    print(f"Sending Matter on/off command: {'ON' if on else 'OFF'} to node {node_id}, endpoint {endpoint}")
    print("-" * 40)
    cmd = "on" if on else "off"
    script = f"{CHIPTOOL_PATH} onoff {cmd} {int(node_id)} {int(endpoint)}"
    ok, _ = chiptool_run(script)
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
    ok, _ = chiptool_run(script)
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
    ok, _ = chiptool_run(script)
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
    ok, output = chiptool_run(script)
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


def get_pi_unix_time():
    """Return current Unix seconds from the Matter Hub (Pi), or None on failure."""
    ok, output = ssh_bash("date -u +%s", timeout=30)
    if not ok:
        return None
    m = re.search(r"(\d+)", output)
    if not m:
        print("Failed to parse Unix time from Matter Hub date output")
        return None
    return int(m.group(1))


def unix_to_matter_epoch_us(unix_s):
    """Convert Unix seconds to Matter epoch microseconds (since 2000-01-01 UTC)."""
    return int((int(unix_s) - MATTER_EPOCH_UNIX_S) * 1_000_000)


def matter_set_utc_time(
    unix_s=None,
    node_id=DEFAULT_NODE_ID,
    endpoint=ROOT_ENDPOINT,
    granularity=TIME_GRANULARITY_MILLISECONDS,
    time_source=TIME_SOURCE_ADMIN,
):
    """
    Invoke TimeSynchronization SetUTCTime on the DUT (root endpoint by default).
    If unix_s is None, uses the Matter Hub's current UTC time.
    Returns (success, unix_s_used_or_None).
    """
    if unix_s is None:
        unix_s = get_pi_unix_time()
        if unix_s is None:
            return False, None
    unix_s = int(unix_s)
    matter_us = unix_to_matter_epoch_us(unix_s)
    print("-" * 40)
    print(
        f"Setting Matter UTC time on node {node_id} ep {endpoint}: "
        f"unix={unix_s} matter_us={matter_us} granularity={granularity} "
        f"time_source={time_source}"
    )
    print("-" * 40)
    # chip-tool: set-utctime UTCTime Granularity node-id endpoint-id [--TimeSource N]
    # TimeSource is optional-flag, not a positional (passing it positionally
    # shifts node/endpoint and breaks --timeout parsing).
    script = (
        f"{CHIPTOOL_PATH} timesynchronization set-utctime "
        f"{matter_us} {int(granularity)} "
        f"{int(node_id)} {int(endpoint)} "
        f"--TimeSource {int(time_source)}"
    )
    ok, _ = chiptool_run(script)
    return ok, unix_s if ok else None


def matter_set_timezone(
    offset_seconds,
    node_id=DEFAULT_NODE_ID,
    endpoint=ROOT_ENDPOINT,
    valid_at=0,
    name=None,
):
    """
    Invoke TimeSynchronization SetTimeZone with a single timezone entry.
    offset_seconds: east of UTC (e.g. 3600 for UTC+1).
    """
    if name:
        payload = (
            f'[{{"offset": {int(offset_seconds)}, "validAt": {int(valid_at)}, '
            f'"name": "{name}"}}]'
        )
    else:
        payload = f'[{{"offset": {int(offset_seconds)}, "validAt": {int(valid_at)}}}]'
    print("-" * 40)
    print(
        f"Setting Matter timezone on node {node_id} ep {endpoint}: "
        f"offset={offset_seconds}s"
    )
    print("-" * 40)
    # chip-tool command name is set-time-zone (not set-timezone)
    script = (
        f"{CHIPTOOL_PATH} timesynchronization set-time-zone "
        f"{shlex.quote(payload)} {int(node_id)} {int(endpoint)}"
    )
    ok, _ = chiptool_run(script)
    return ok


def matter_set_dst_offset(
    offset_seconds=0,
    node_id=DEFAULT_NODE_ID,
    endpoint=ROOT_ENDPOINT,
    valid_starting=0,
):
    """
    Invoke TimeSynchronization SetDSTOffset with a single always-valid entry.
    Arduino TimeZoneDatabase is None, so hubs typically must supply DST after TZ.
    """
    # validUntil omitted / null → open-ended
    payload = (
        f'[{{"offset": {int(offset_seconds)}, '
        f'"validStarting": {int(valid_starting)}, "validUntil": null}}]'
    )
    print("-" * 40)
    print(
        f"Setting Matter DST offset on node {node_id} ep {endpoint}: "
        f"offset={offset_seconds}s"
    )
    print("-" * 40)
    # chip-tool: set-dstoffset (matches cluster command SetDSTOffset)
    script = (
        f"{CHIPTOOL_PATH} timesynchronization set-dstoffset "
        f"{shlex.quote(payload)} {int(node_id)} {int(endpoint)}"
    )
    ok, _ = chiptool_run(script)
    return ok


def matter_read_pressure_hpa(node_id=DEFAULT_NODE_ID, endpoint=DEFAULT_ENDPOINT):
    """
    Read PressureMeasurement MeasuredValue via chip-tool.
    Matter stores 0.1 kPa units; Arduino MatterPressure sets hPa as int16, and
    1 hPa == 0.1 kPa, so the raw value is numerically hPa.
    Returns (success, hpa_float_or_None).
    """
    print("-" * 40)
    print(f"Reading Matter pressure from node {node_id}, endpoint {endpoint}")
    print("-" * 40)
    script = (
        f"{CHIPTOOL_PATH} pressuremeasurement read measured-value "
        f"{int(node_id)} {int(endpoint)}"
    )
    ok, output = chiptool_run(script)
    if not ok:
        return False, None

    m = re.search(r"MeasuredValue:\s*(-?\d+)", output)
    if not m:
        print("Failed to parse MeasuredValue from chip-tool output")
        return False, None

    raw = int(m.group(1))
    hpa = float(raw)
    print(f"MeasuredValue raw={raw} -> {hpa:.1f} hPa")
    return True, hpa


def matter_read_flow_m3h(node_id=DEFAULT_NODE_ID, endpoint=DEFAULT_ENDPOINT):
    """
    Read FlowMeasurement MeasuredValue via chip-tool.
    Matter/Arduino encode raw = 10 x flow (m3/h).
    Returns (success, m3h_float_or_None).
    """
    print("-" * 40)
    print(f"Reading Matter flow from node {node_id}, endpoint {endpoint}")
    print("-" * 40)
    script = (
        f"{CHIPTOOL_PATH} flowmeasurement read measured-value "
        f"{int(node_id)} {int(endpoint)}"
    )
    ok, output = chiptool_run(script)
    if not ok:
        return False, None

    m = re.search(r"MeasuredValue:\s*(-?\d+)", output)
    if not m:
        print("Failed to parse MeasuredValue from chip-tool output")
        return False, None

    raw = int(m.group(1))
    m3h = raw / 10.0
    print(f"MeasuredValue raw={raw} -> {m3h:.2f} m3/h")
    return True, m3h


def matter_read_occupancy(node_id=DEFAULT_NODE_ID, endpoint=DEFAULT_ENDPOINT):
    """
    Read OccupancySensing Occupancy via chip-tool.
    Arduino DeviceOccupancySensor stores a bool; Matter bit 0 set => occupied.
    Returns (success, occupied_bool_or_None).
    """
    print("-" * 40)
    print(f"Reading Matter occupancy from node {node_id}, endpoint {endpoint}")
    print("-" * 40)
    script = (
        f"{CHIPTOOL_PATH} occupancysensing read occupancy "
        f"{int(node_id)} {int(endpoint)}"
    )
    ok, output = chiptool_run(script)
    if not ok:
        return False, None

    m = re.search(r"Occupancy:\s*(\d+)", output)
    if not m:
        print("Failed to parse Occupancy from chip-tool output")
        return False, None

    raw = int(m.group(1))
    occupied = bool(raw & 0x1)
    print(f"Occupancy raw={raw} -> {'occupied' if occupied else 'unoccupied'}")
    return True, occupied


def matter_read_contact_state(node_id=DEFAULT_NODE_ID, endpoint=DEFAULT_ENDPOINT):
    """
    Read BooleanState StateValue via chip-tool (Matter contact sensor).
    Returns (success, contact_detected_bool_or_None).
    """
    print("-" * 40)
    print(f"Reading Matter contact StateValue from node {node_id}, endpoint {endpoint}")
    print("-" * 40)
    script = (
        f"{CHIPTOOL_PATH} booleanstate read state-value "
        f"{int(node_id)} {int(endpoint)}"
    )
    ok, output = chiptool_run(script)
    if not ok:
        return False, None

    m = re.search(r"StateValue:\s*(TRUE|FALSE|true|false|1|0)", output)
    if not m:
        print("Failed to parse StateValue from chip-tool output")
        return False, None

    raw = m.group(1).upper()
    detected = raw in ("TRUE", "1")
    print(f"StateValue={m.group(1)} -> {'detected' if detected else 'lost'}")
    return True, detected


# MatterAirQuality::AirQuality_t / AirQualityEnum (skip UNKNOWN / UNDEFINED for HIL cycle)
AIR_QUALITY_LABELS = {
    1: "good",
    2: "fair",
    3: "moderate",
    4: "poor",
    5: "very poor",
    6: "extremely poor",
}


def matter_read_air_quality(node_id=DEFAULT_NODE_ID, endpoint=DEFAULT_ENDPOINT):
    """
    Read AirQuality AirQuality via chip-tool.
    Returns (success, enum_int_or_None) where enum matches MatterAirQuality::AirQuality_t.
    """
    print("-" * 40)
    print(f"Reading Matter air-quality from node {node_id}, endpoint {endpoint}")
    print("-" * 40)
    script = (
        f"{CHIPTOOL_PATH} airquality read air-quality "
        f"{int(node_id)} {int(endpoint)}"
    )
    ok, output = chiptool_run(script)
    if not ok:
        return False, None

    m = re.search(r"AirQuality:\s*(\d+)", output)
    if not m:
        print("Failed to parse AirQuality from chip-tool output")
        return False, None

    raw = int(m.group(1))
    label = AIR_QUALITY_LABELS.get(raw, f"raw={raw}")
    print(f"AirQuality raw={raw} -> {label}")
    return True, raw


def matter_read_bat_percent_remaining(node_id=DEFAULT_NODE_ID, endpoint=DEFAULT_ENDPOINT):
    """
    Read PowerSource BatPercentRemaining via chip-tool.
    Matter encodes percent as raw = 2 x percent (0-200 → 0-100%).
    Matches MatterSimplePowerSource::set_battery_percent().
    Returns (success, percent_int_or_None).
    """
    print("-" * 40)
    print(f"Reading Matter bat-percent-remaining from node {node_id}, endpoint {endpoint}")
    print("-" * 40)
    script = (
        f"{CHIPTOOL_PATH} powersource read bat-percent-remaining "
        f"{int(node_id)} {int(endpoint)}"
    )
    ok, output = chiptool_run(script)
    if not ok:
        return False, None

    # Flat "BatPercentRemaining: 200" or nullable "Value: 200" forms
    m = re.search(r"BatPercentRemaining:\s*(\d+)", output)
    if not m:
        m = re.search(r"BatPercentRemaining:[\s\S]*?Value:\s*(\d+)", output)
    if not m:
        print("Failed to parse BatPercentRemaining from chip-tool output")
        return False, None

    raw = int(m.group(1))
    percent = raw // 2
    print(f"BatPercentRemaining raw={raw} -> {percent}%")
    return True, percent


def matter_read_bat_voltage_mv(node_id=DEFAULT_NODE_ID, endpoint=DEFAULT_ENDPOINT):
    """
    Read PowerSource BatVoltage via chip-tool (millivolts).
    Returns (success, mv_int_or_None).
    """
    print("-" * 40)
    print(f"Reading Matter bat-voltage from node {node_id}, endpoint {endpoint}")
    print("-" * 40)
    script = (
        f"{CHIPTOOL_PATH} powersource read bat-voltage "
        f"{int(node_id)} {int(endpoint)}"
    )
    ok, output = chiptool_run(script)
    if not ok:
        return False, None

    m = re.search(r"BatVoltage:\s*(\d+)", output)
    if not m:
        m = re.search(r"BatVoltage:[\s\S]*?Value:\s*(\d+)", output)
    if not m:
        print("Failed to parse BatVoltage from chip-tool output")
        return False, None

    mv = int(m.group(1))
    print(f"BatVoltage raw={mv} mV")
    return True, mv


def matter_read_humidity_percent(node_id=DEFAULT_NODE_ID, endpoint=DEFAULT_ENDPOINT):
    """
    Read RelativeHumidityMeasurement MeasuredValue via chip-tool.
    Matter encodes the value in hundredths of a percent (uint16, 0-10000).
    Returns (success, percent_float_or_None).
    """
    print("-" * 40)
    print(f"Reading Matter humidity from node {node_id}, endpoint {endpoint}")
    print("-" * 40)
    script = (
        f"{CHIPTOOL_PATH} relativehumiditymeasurement read measured-value "
        f"{int(node_id)} {int(endpoint)}"
    )
    ok, output = chiptool_run(script)
    if not ok:
        return False, None

    m = re.search(r"MeasuredValue:\s*(-?\d+)", output)
    if not m:
        print("Failed to parse MeasuredValue from chip-tool output")
        return False, None

    raw = int(m.group(1))
    percent = raw / 100.0
    print(f"MeasuredValue raw={raw} -> {percent:.2f} %RH")
    return True, percent


def matter_illuminance_raw_to_lux(raw):
    """
    IlluminanceMeasurement MeasuredValue: 0 means too low to measure;
    otherwise lux = 10 ^ ((raw - 1) / 10000). Matches MatterIlluminance.
    """
    raw = int(raw)
    if raw <= 0:
        return 0.0
    return 10 ** ((raw - 1) / 10000.0)


def matter_read_illuminance_lux(node_id=DEFAULT_NODE_ID, endpoint=DEFAULT_ENDPOINT):
    """
    Read IlluminanceMeasurement MeasuredValue via chip-tool and convert to lux.
    Returns (success, lux_float_or_None).
    """
    print("-" * 40)
    print(f"Reading Matter illuminance from node {node_id}, endpoint {endpoint}")
    print("-" * 40)
    script = (
        f"{CHIPTOOL_PATH} illuminancemeasurement read measured-value "
        f"{int(node_id)} {int(endpoint)}"
    )
    ok, output = chiptool_run(script)
    if not ok:
        return False, None

    m = re.search(r"MeasuredValue:\s*(-?\d+)", output)
    if not m:
        print("Failed to parse MeasuredValue from chip-tool output")
        return False, None

    raw = int(m.group(1))
    lux = matter_illuminance_raw_to_lux(raw)
    print(f"MeasuredValue raw={raw} -> {lux:.2f} lx")
    return True, lux


def _matter_read_concentration(cluster, label, unit, node_id, endpoint):
    """
    Read a concentration-measurement MeasuredValue (Matter single/float).
    Returns (success, value_float_or_None).
    """
    print("-" * 40)
    print(f"Reading Matter {label} from node {node_id}, endpoint {endpoint}")
    print("-" * 40)
    script = (
        f"{CHIPTOOL_PATH} {cluster} read measured-value "
        f"{int(node_id)} {int(endpoint)}"
    )
    ok, output = chiptool_run(script)
    if not ok:
        return False, None

    m = re.search(r"MeasuredValue:\s*([-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?)", output)
    if not m:
        print("Failed to parse MeasuredValue from chip-tool output")
        return False, None

    value = float(m.group(1))
    print(f"MeasuredValue -> {value:.0f} {unit}")
    return True, value


def matter_read_co2_ppm(node_id=DEFAULT_NODE_ID, endpoint=DEFAULT_ENDPOINT):
    """
    Read CarbonDioxideConcentrationMeasurement MeasuredValue via chip-tool.
    Value is a float in ppm (Matter single/float attribute).
    Returns (success, ppm_float_or_None).
    """
    return _matter_read_concentration(
        "carbondioxideconcentrationmeasurement", "CO2", "ppm", node_id, endpoint
    )


def matter_read_co_ppb(node_id=DEFAULT_NODE_ID, endpoint=DEFAULT_ENDPOINT):
    """
    Read CarbonMonoxideConcentrationMeasurement MeasuredValue via chip-tool.
    Value is a float in ppb (Matter single/float attribute).
    Returns (success, ppb_float_or_None).
    """
    return _matter_read_concentration(
        "carbonmonoxideconcentrationmeasurement", "CO", "ppb", node_id, endpoint
    )


def matter_read_tvoc_ppb(node_id=DEFAULT_NODE_ID, endpoint=DEFAULT_ENDPOINT):
    """
    Read TotalVolatileOrganicCompoundsConcentrationMeasurement MeasuredValue.
    Value is a float in ppb (Matter single/float attribute).
    Returns (success, ppb_float_or_None).
    """
    return _matter_read_concentration(
        "totalvolatileorganiccompoundsconcentrationmeasurement",
        "TVOC",
        "ppb",
        node_id,
        endpoint,
    )


# Matter Thermostat SystemMode (MatterThermostat::thermostat_mode_t)
THERMOSTAT_MODE_OFF = 0
THERMOSTAT_MODE_HEAT = 4


def celsius_to_matter_temp_raw(celsius):
    """Matter thermostat temps are hundredths of a degree Celsius (int16)."""
    return int(round(float(celsius) * 100.0))


def matter_temp_raw_to_celsius(raw):
    return int(raw) / 100.0


def matter_read_thermostat_system_mode(node_id=DEFAULT_NODE_ID, endpoint=DEFAULT_ENDPOINT):
    """
    Read Thermostat SystemMode (also marks the appliance online on first read).
    Returns (success, mode_int_or_None).
    """
    print("-" * 40)
    print(f"Reading Matter thermostat system-mode from node {node_id}, endpoint {endpoint}")
    print("-" * 40)
    script = (
        f"{CHIPTOOL_PATH} thermostat read system-mode "
        f"{int(node_id)} {int(endpoint)}"
    )
    ok, output = chiptool_run(script)
    if not ok:
        return False, None

    m = re.search(r"SystemMode:\s*(\d+)", output)
    if not m:
        print("Failed to parse SystemMode from chip-tool output")
        return False, None

    mode = int(m.group(1))
    print(f"SystemMode={mode}")
    return True, mode


def matter_write_thermostat_system_mode(mode, node_id=DEFAULT_NODE_ID, endpoint=DEFAULT_ENDPOINT):
    """Write Thermostat SystemMode (0=Off, 4=Heat)."""
    mode = int(mode)
    print("-" * 40)
    print(f"Writing Matter thermostat system-mode={mode} to node {node_id}, endpoint {endpoint}")
    print("-" * 40)
    script = (
        f"{CHIPTOOL_PATH} thermostat write system-mode "
        f"{mode} {int(node_id)} {int(endpoint)}"
    )
    ok, _ = chiptool_run(script)
    return ok


def matter_read_occupied_heating_setpoint_c(node_id=DEFAULT_NODE_ID, endpoint=DEFAULT_ENDPOINT):
    """
    Read OccupiedHeatingSetpoint (hundredths of °C) and return Celsius.
    Returns (success, celsius_float_or_None).
    """
    print("-" * 40)
    print(
        f"Reading Matter occupied-heating-setpoint from node {node_id}, endpoint {endpoint}"
    )
    print("-" * 40)
    script = (
        f"{CHIPTOOL_PATH} thermostat read occupied-heating-setpoint "
        f"{int(node_id)} {int(endpoint)}"
    )
    ok, output = chiptool_run(script)
    if not ok:
        return False, None

    m = re.search(r"OccupiedHeatingSetpoint:\s*(-?\d+)", output)
    if not m:
        print("Failed to parse OccupiedHeatingSetpoint from chip-tool output")
        return False, None

    raw = int(m.group(1))
    celsius = matter_temp_raw_to_celsius(raw)
    print(f"OccupiedHeatingSetpoint raw={raw} -> {celsius:.1f} C")
    return True, celsius


def matter_write_occupied_heating_setpoint_c(
    celsius, node_id=DEFAULT_NODE_ID, endpoint=DEFAULT_ENDPOINT
):
    """Write OccupiedHeatingSetpoint from a Celsius value (stored as °C x 100)."""
    raw = celsius_to_matter_temp_raw(celsius)
    print("-" * 40)
    print(
        f"Writing Matter occupied-heating-setpoint={celsius:.1f} C (raw {raw}) "
        f"to node {node_id}, endpoint {endpoint}"
    )
    print("-" * 40)
    script = (
        f"{CHIPTOOL_PATH} thermostat write occupied-heating-setpoint "
        f"{raw} {int(node_id)} {int(endpoint)}"
    )
    ok, _ = chiptool_run(script)
    return ok


def matter_read_min_heat_setpoint_limit_c(node_id=DEFAULT_NODE_ID, endpoint=DEFAULT_ENDPOINT):
    """Read MinHeatSetpointLimit; returns (success, celsius_float_or_None)."""
    print("-" * 40)
    print(f"Reading Matter min-heat-setpoint-limit from node {node_id}, endpoint {endpoint}")
    print("-" * 40)
    script = (
        f"{CHIPTOOL_PATH} thermostat read min-heat-setpoint-limit "
        f"{int(node_id)} {int(endpoint)}"
    )
    ok, output = chiptool_run(script)
    if not ok:
        return False, None

    m = re.search(r"MinHeatSetpointLimit:\s*(-?\d+)", output)
    if not m:
        print("Failed to parse MinHeatSetpointLimit from chip-tool output")
        return False, None

    raw = int(m.group(1))
    celsius = matter_temp_raw_to_celsius(raw)
    print(f"MinHeatSetpointLimit raw={raw} -> {celsius:.1f} C")
    return True, celsius


def matter_read_max_heat_setpoint_limit_c(node_id=DEFAULT_NODE_ID, endpoint=DEFAULT_ENDPOINT):
    """Read MaxHeatSetpointLimit; returns (success, celsius_float_or_None)."""
    print("-" * 40)
    print(f"Reading Matter max-heat-setpoint-limit from node {node_id}, endpoint {endpoint}")
    print("-" * 40)
    script = (
        f"{CHIPTOOL_PATH} thermostat read max-heat-setpoint-limit "
        f"{int(node_id)} {int(endpoint)}"
    )
    ok, output = chiptool_run(script)
    if not ok:
        return False, None

    m = re.search(r"MaxHeatSetpointLimit:\s*(-?\d+)", output)
    if not m:
        print("Failed to parse MaxHeatSetpointLimit from chip-tool output")
        return False, None

    raw = int(m.group(1))
    celsius = matter_temp_raw_to_celsius(raw)
    print(f"MaxHeatSetpointLimit raw={raw} -> {celsius:.1f} C")
    return True, celsius


# Matter FanControl FanMode values (DeviceFan::fan_mode_t)
FAN_MODE_OFF = 0
FAN_MODE_LOW = 1
FAN_MODE_MED = 2
FAN_MODE_HIGH = 3
FAN_MODE_ON = 4
FAN_MODE_AUTO = 5
FAN_MODE_SMART = 6


def matter_read_fan_mode(node_id=DEFAULT_NODE_ID, endpoint=DEFAULT_ENDPOINT):
    """Read FanControl FanMode (also marks the appliance online on first attribute read)."""
    print("-" * 40)
    print(f"Reading Matter fan-mode from node {node_id}, endpoint {endpoint}")
    print("-" * 40)
    script = f"{CHIPTOOL_PATH} fancontrol read fan-mode {int(node_id)} {int(endpoint)}"
    ok, _ = chiptool_run(script)
    return ok


def matter_write_fan_mode(mode, node_id=DEFAULT_NODE_ID, endpoint=DEFAULT_ENDPOINT):
    """Write FanControl FanMode (0=Off … 6=Smart)."""
    mode = int(mode)
    print("-" * 40)
    print(f"Writing Matter fan-mode={mode} to node {node_id}, endpoint {endpoint}")
    print("-" * 40)
    script = (
        f"{CHIPTOOL_PATH} fancontrol write fan-mode "
        f"{mode} {int(node_id)} {int(endpoint)}"
    )
    ok, _ = chiptool_run(script)
    return ok


def matter_write_fan_percent(percent, node_id=DEFAULT_NODE_ID, endpoint=DEFAULT_ENDPOINT):
    """Write FanControl PercentSetting (0-100)."""
    percent = max(0, min(100, int(percent)))
    print("-" * 40)
    print(f"Writing Matter fan percent-setting={percent} to node {node_id}, endpoint {endpoint}")
    print("-" * 40)
    script = (
        f"{CHIPTOOL_PATH} fancontrol write percent-setting "
        f"{percent} {int(node_id)} {int(endpoint)}"
    )
    ok, _ = chiptool_run(script)
    return ok


def app_lift_percent_to_matter_100ths(app_percent):
    """
    Arduino MatterWindowCovering app percent: 100%=fully open, 0%=fully closed.
    Matter LiftPercent100ths: 0=fully open, 10000=fully closed.
    """
    app_percent = max(0, min(100, int(app_percent)))
    return 10000 - app_percent * 100


def matter_read_window_covering_position(node_id=DEFAULT_NODE_ID, endpoint=DEFAULT_ENDPOINT):
    """
    Read CurrentPositionLiftPercent100ths (marks the appliance online on first read).
    Returns (success, matter_percent100ths_or_None).
    """
    print("-" * 40)
    print(f"Reading window covering position from node {node_id}, endpoint {endpoint}")
    print("-" * 40)
    script = (
        f"{CHIPTOOL_PATH} windowcovering read current-position-lift-percent100ths "
        f"{int(node_id)} {int(endpoint)}"
    )
    ok, output = chiptool_run(script)
    if not ok:
        return False, None

    m = re.search(r"CurrentPositionLiftPercent100ths:\s*(-?\d+)", output)
    if not m:
        # Some chip-tool builds print a generic AttributeValue / Data line
        m = re.search(r"Percent100ths:\s*(-?\d+)", output)
    if not m:
        print("Failed to parse CurrentPositionLiftPercent100ths from chip-tool output")
        return False, None

    value = int(m.group(1))
    print(f"CurrentPositionLiftPercent100ths={value}")
    return True, value


def matter_window_covering_up_or_open(node_id=DEFAULT_NODE_ID, endpoint=DEFAULT_ENDPOINT):
    print("-" * 40)
    print(f"Window covering up-or-open node {node_id}, endpoint {endpoint}")
    print("-" * 40)
    script = f"{CHIPTOOL_PATH} windowcovering up-or-open {int(node_id)} {int(endpoint)}"
    ok, _ = chiptool_run(script)
    return ok


def matter_window_covering_down_or_close(node_id=DEFAULT_NODE_ID, endpoint=DEFAULT_ENDPOINT):
    print("-" * 40)
    print(f"Window covering down-or-close node {node_id}, endpoint {endpoint}")
    print("-" * 40)
    script = f"{CHIPTOOL_PATH} windowcovering down-or-close {int(node_id)} {int(endpoint)}"
    ok, _ = chiptool_run(script)
    return ok


def matter_window_covering_stop_motion(node_id=DEFAULT_NODE_ID, endpoint=DEFAULT_ENDPOINT):
    print("-" * 40)
    print(f"Window covering stop-motion node {node_id}, endpoint {endpoint}")
    print("-" * 40)
    script = f"{CHIPTOOL_PATH} windowcovering stop-motion {int(node_id)} {int(endpoint)}"
    ok, _ = chiptool_run(script)
    return ok


def matter_window_covering_go_to_app_percent(app_percent, node_id=DEFAULT_NODE_ID, endpoint=DEFAULT_ENDPOINT):
    """
    GoToLiftPercentage using Arduino app percent (100%=open, 0%=closed).
    """
    matter_100ths = app_lift_percent_to_matter_100ths(app_percent)
    print("-" * 40)
    print(
        f"Window covering go-to-lift-percentage app={app_percent}% "
        f"(Matter {matter_100ths}) node {node_id}, endpoint {endpoint}"
    )
    print("-" * 40)
    script = (
        f"{CHIPTOOL_PATH} windowcovering go-to-lift-percentage "
        f"{matter_100ths} {int(node_id)} {int(endpoint)}"
    )
    ok, _ = chiptool_run(script)
    return ok


def commission_with_defaults(node_id=DEFAULT_NODE_ID, before_retry=None):
    """
    Start Thread on the Pi and BLE-commission the DUT using the default
    development passcode/discriminator (skips reading pairing codes from Serial).

    before_retry: optional callable() -> bool run before the second attempt
    (typically hil_util.prepare_matter_dut_recommission wrapped by the testcase).
    """
    print(
        f"Commissioning with defaults: "
        f"PINCODE={DEFAULT_PINCODE} DISCRIMINATOR={DEFAULT_DISCRIMINATOR} NODE_ID={node_id}"
    )
    return start_thread_and_commission(
        DEFAULT_PINCODE,
        DEFAULT_DISCRIMINATOR,
        node_id=node_id,
        before_retry=before_retry,
    )


def commission_from_serial_text(serial_text, node_id=DEFAULT_NODE_ID, before_retry=None):
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

    return start_thread_and_commission(
        pincode, discriminator, node_id=node_id, before_retry=before_retry
    )
