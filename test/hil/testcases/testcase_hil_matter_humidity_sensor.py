import os
import re
import time

import util.hil_util as hil_util
import util.matter_otbr_util as matter_otbr_util

HUMIDITY_SENSOR_SKETCH = os.path.normpath(os.path.join(
    os.path.dirname(__file__),
    "..", "..", "..",
    "libraries", "Matter", "examples", "matter_humidity_sensor",
    "matter_humidity_sensor.ino",
))

NODE_ID = matter_otbr_util.DEFAULT_NODE_ID

# Example: current_humidity += 0.5f; if > 100.0f wrap to 0.0f
HUMIDITY_STEP = 0.5
HUMIDITY_SERIAL_RE = re.compile(r"Current humidity: (\d+\.\d)%\n")


def _wait_for_next_humidity_serial(monitor, after_index=0, timeout=30):
    """
    Wait for the next 'Current humidity: X.Y%' line at/after after_index in the
    SerialMonitor buffer. Returns (percent, match_end_index) or (None, after_index).
    """
    print("-" * 40)
    print(f"Waiting up to {timeout}s for next humidity Serial line (after idx {after_index})")
    print("-" * 40)
    deadline = time.time() + timeout
    while time.time() < deadline:
        text = monitor.text()
        for match in HUMIDITY_SERIAL_RE.finditer(text):
            if match.start() >= after_index:
                percent = float(match.group(1))
                print(f"Observed Serial humidity: {percent:.1f}%")
                return percent, match.end()
        time.sleep(0.1)
    print("Timed out waiting for humidity Serial line")
    return None, after_index


def _is_one_humidity_increment(previous, current):
    """True if current is previous + 0.5, or wrap from 100.0 → 0.0."""
    expected = previous + HUMIDITY_STEP
    if expected > 100.0:
        return current == 0.0
    return abs(current - expected) < 0.05


def testcase_hil_matter_humidity_sensor(current_board, variant, current_board_port):
    """
    Testcase: HIL Matter humidity sensor
    Description: Flashes the Matter humidity sensor example, commissions it via
    SSH chip-tool on a Silicon Labs Matter Hub (Pi), then verifies one humidity
    increment (+0.5%, wrapping 100% -> 0%) on Serial and via MeasuredValue.

    Opt-in only: requires test_hil.py --matter-otbr <pi-ip>.
    """
    did_run = False
    if variant != "matter":
        return did_run, True
    if not matter_otbr_util.is_enabled():
        return did_run, True

    did_run = True
    monitor = None

    if not matter_otbr_util.check_ssh_connectivity():
        print(f"Cannot SSH to Matter Hub at {matter_otbr_util.otbr_host}")
        return did_run, False

    # Clear Matter commissioning / NVM from any previous run
    if not hil_util.arduino_cli_burn_bootloader(current_board, current_board_port):
        print(f"Bootloader burn failed for '{current_board}'")
        return did_run, False

    success = hil_util.arduino_cli_build_and_flash(
        current_board, variant, HUMIDITY_SENSOR_SKETCH, current_board_port
    )
    if not success:
        print(f"Build/upload failed for '{variant}' on '{current_board}'")
        return did_run, False

    time.sleep(2)
    try:
        monitor = hil_util.SerialMonitor(current_board_port)
    except Exception as e:
        print(f"Failed to open serial monitor: {e}")
        return did_run, False

    try:
        time.sleep(5)

        if not matter_otbr_util.commission_with_defaults(node_id=NODE_ID):
            print("Commissioning via Matter Hub failed")
            return did_run, False

        # First attribute read marks the appliance online so setup() can exit into loop()
        ok, _ = matter_otbr_util.matter_read_humidity_percent(node_id=NODE_ID)
        if not ok:
            print("humidity attribute read failed (needed to mark DUT online)")
            return did_run, False

        if not monitor.wait_for("Matter device is now online", timeout=60):
            print("DUT did not come online on Matter after attribute read")
            return did_run, False

        humidity_1, idx = _wait_for_next_humidity_serial(monitor, after_index=0, timeout=30)
        if humidity_1 is None:
            print("DUT did not print an initial humidity value")
            return did_run, False

        ok, matter_1 = matter_otbr_util.matter_read_humidity_percent(node_id=NODE_ID)
        if not ok or matter_1 is None:
            print("Failed to read initial humidity MeasuredValue")
            return did_run, False
        if abs(matter_1 - humidity_1) > 0.15:
            print(f"Matter humidity {matter_1:.2f}% does not match Serial {humidity_1:.1f}%")
            return did_run, False

        # Example publishes every 10s; wait for the next stepped value
        humidity_2, _ = _wait_for_next_humidity_serial(monitor, after_index=idx, timeout=20)
        if humidity_2 is None:
            print("DUT did not print a second humidity value (expected +0.5% step)")
            return did_run, False

        if not _is_one_humidity_increment(humidity_1, humidity_2):
            print(
                f"Humidity did not increment by {HUMIDITY_STEP}: "
                f"{humidity_1:.1f}% -> {humidity_2:.1f}%"
            )
            return did_run, False

        ok, matter_2 = matter_otbr_util.matter_read_humidity_percent(node_id=NODE_ID)
        if not ok or matter_2 is None:
            print("Failed to read humidity MeasuredValue after increment")
            return did_run, False
        if abs(matter_2 - humidity_2) > 0.15:
            print(
                f"Matter humidity {matter_2:.2f}% does not match Serial {humidity_2:.1f}% "
                f"after increment"
            )
            return did_run, False

        print(f"Humidity increment OK: {humidity_1:.1f}% -> {humidity_2:.1f}%")
        return did_run, True
    finally:
        if monitor is not None:
            monitor.close()
