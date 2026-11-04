import os
import re
import time

import util.hil_util as hil_util
import util.matter_otbr_util as matter_otbr_util

CO2_SENSOR_SKETCH = os.path.normpath(os.path.join(
    os.path.dirname(__file__),
    "..", "..", "..",
    "libraries", "Matter", "examples", "matter_co2_sensor", "matter_co2_sensor.ino",
))

NODE_ID = matter_otbr_util.DEFAULT_NODE_ID

# Example: current_co2 += 15.0f; if > 10000.0f wrap to 0.0f
CO2_STEP_PPM = 15.0
CO2_SERIAL_RE = re.compile(r"Current CO2 concentration: (\d+) ppm\n")


def _wait_for_next_co2_serial(monitor, after_index=0, timeout=30):
    """
    Wait for the next 'Current CO2 concentration: N ppm' line at/after after_index.
    Returns (ppm, match_end_index) or (None, after_index).
    """
    print("-" * 40)
    print(f"Waiting up to {timeout}s for next CO2 Serial line (after idx {after_index})")
    print("-" * 40)
    deadline = time.time() + timeout
    while time.time() < deadline:
        text = monitor.text()
        for match in CO2_SERIAL_RE.finditer(text):
            if match.start() >= after_index:
                ppm = float(match.group(1))
                print(f"Observed Serial CO2: {ppm:.0f} ppm")
                return ppm, match.end()
        time.sleep(0.1)
    print("Timed out waiting for CO2 Serial line")
    return None, after_index


def _is_one_co2_increment(previous, current):
    """True if current is previous + 15 ppm, or wrap from >10000 path (10005→0)."""
    expected = previous + CO2_STEP_PPM
    if expected > 10000.0:
        return current == 0.0
    return abs(current - expected) < 0.5


def testcase_hil_matter_co2_sensor(current_board, variant, current_board_port):
    """
    Testcase: HIL Matter CO2 sensor
    Description: Flashes the Matter CO2 sensor example, commissions it via SSH
    chip-tool on a Silicon Labs Matter Hub (Pi), then verifies one concentration
    increment (+15 ppm, wrapping above 10000 -> 0) on Serial and via MeasuredValue.

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
        current_board, variant, CO2_SENSOR_SKETCH, current_board_port
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
        ok, _ = matter_otbr_util.matter_read_co2_ppm(node_id=NODE_ID)
        if not ok:
            print("CO2 attribute read failed (needed to mark DUT online)")
            return did_run, False

        if not monitor.wait_for("Matter device is now online", timeout=60):
            print("DUT did not come online on Matter after attribute read")
            return did_run, False

        co2_1, idx = _wait_for_next_co2_serial(monitor, after_index=0, timeout=30)
        if co2_1 is None:
            print("DUT did not print an initial CO2 value")
            return did_run, False

        ok, matter_1 = matter_otbr_util.matter_read_co2_ppm(node_id=NODE_ID)
        if not ok or matter_1 is None:
            print("Failed to read initial CO2 MeasuredValue")
            return did_run, False
        if abs(matter_1 - co2_1) > 0.5:
            print(f"Matter CO2 {matter_1:.0f} ppm does not match Serial {co2_1:.0f} ppm")
            return did_run, False

        # Example publishes every 10s; wait for the next stepped value
        co2_2, _ = _wait_for_next_co2_serial(monitor, after_index=idx, timeout=20)
        if co2_2 is None:
            print("DUT did not print a second CO2 value (expected +15 ppm step)")
            return did_run, False

        if not _is_one_co2_increment(co2_1, co2_2):
            print(
                f"CO2 did not increment by {CO2_STEP_PPM:.0f} ppm: "
                f"{co2_1:.0f} -> {co2_2:.0f}"
            )
            return did_run, False

        ok, matter_2 = matter_otbr_util.matter_read_co2_ppm(node_id=NODE_ID)
        if not ok or matter_2 is None:
            print("Failed to read CO2 MeasuredValue after increment")
            return did_run, False
        if abs(matter_2 - co2_2) > 0.5:
            print(
                f"Matter CO2 {matter_2:.0f} ppm does not match Serial {co2_2:.0f} ppm "
                f"after increment"
            )
            return did_run, False

        print(f"CO2 increment OK: {co2_1:.0f} ppm -> {co2_2:.0f} ppm")
        return did_run, True
    finally:
        if monitor is not None:
            monitor.close()
