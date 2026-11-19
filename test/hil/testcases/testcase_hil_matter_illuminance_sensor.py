import os
import re
import time

import util.hil_util as hil_util
import util.matter_otbr_util as matter_otbr_util

ILLUMINANCE_SENSOR_SKETCH = os.path.normpath(os.path.join(
    os.path.dirname(__file__),
    "..", "..", "..",
    "libraries", "Matter", "examples", "matter_illuminance_sensor",
    "matter_illuminance_sensor.ino",
))

NODE_ID = matter_otbr_util.DEFAULT_NODE_ID

# Example: current_illuminance_lux += 15.0f; if > 2000.0f wrap to 0.0f
ILLUMINANCE_STEP_LUX = 15.0
ILLUMINANCE_SERIAL_RE = re.compile(r"Current light level: (\d+\.\d{2}) lx\n")


def _wait_for_next_illuminance_serial(monitor, after_index=0, timeout=30):
    """
    Wait for the next 'Current light level: X.XX lx' line at/after after_index.
    Returns (lux, match_end_index) or (None, after_index).
    """
    print("-" * 40)
    print(f"Waiting up to {timeout}s for next illuminance Serial line (after idx {after_index})")
    print("-" * 40)
    deadline = time.time() + timeout
    while time.time() < deadline:
        text = monitor.text()
        for match in ILLUMINANCE_SERIAL_RE.finditer(text):
            if match.start() >= after_index:
                lux = float(match.group(1))
                print(f"Observed Serial illuminance: {lux:.2f} lx")
                return lux, match.end()
        time.sleep(0.1)
    print("Timed out waiting for illuminance Serial line")
    return None, after_index


def _is_one_illuminance_increment(previous, current):
    """True if current is previous + 15 lx, or wrap from >2000 → 0.0."""
    expected = previous + ILLUMINANCE_STEP_LUX
    if expected > 2000.0:
        return current == 0.0
    return abs(current - expected) < 0.05


def testcase_hil_matter_illuminance_sensor(current_board, variant, current_board_port):
    """
    Testcase: HIL Matter illuminance sensor
    Description: Flashes the Matter illuminance sensor example, commissions it via
    SSH chip-tool on a Silicon Labs Matter Hub (Pi), then verifies one illuminance
    increment (+15 lx, wrapping >2000 -> 0) on Serial and via MeasuredValue.

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
        current_board, variant, ILLUMINANCE_SENSOR_SKETCH, current_board_port
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

        def _before_commission_retry():
            nonlocal monitor
            ok, monitor = hil_util.prepare_matter_dut_recommission(
                current_board, variant, ILLUMINANCE_SENSOR_SKETCH, current_board_port, monitor
            )
            return ok

        if not matter_otbr_util.commission_with_defaults(
            node_id=NODE_ID, before_retry=_before_commission_retry
        ):
            print("Commissioning via Matter Hub failed")
            return did_run, False

        # First attribute read marks the appliance online so setup() can exit into loop()
        ok, _ = matter_otbr_util.matter_read_illuminance_lux(node_id=NODE_ID)
        if not ok:
            print("illuminance attribute read failed (needed to mark DUT online)")
            return did_run, False

        if not monitor.wait_for("Matter device is now online", timeout=60):
            print("DUT did not come online on Matter after attribute read")
            return did_run, False

        lux_1, idx = _wait_for_next_illuminance_serial(monitor, after_index=0, timeout=30)
        if lux_1 is None:
            print("DUT did not print an initial illuminance value")
            return did_run, False

        ok, matter_1 = matter_otbr_util.matter_read_illuminance_lux(node_id=NODE_ID)
        if not ok or matter_1 is None:
            print("Failed to read initial illuminance MeasuredValue")
            return did_run, False
        # log10 encoding + uint16 truncation; allow a small lux delta
        if abs(matter_1 - lux_1) > 0.5:
            print(f"Matter illuminance {matter_1:.2f} lx does not match Serial {lux_1:.2f} lx")
            return did_run, False

        # Example publishes every 10s; wait for the next stepped value
        lux_2, _ = _wait_for_next_illuminance_serial(monitor, after_index=idx, timeout=20)
        if lux_2 is None:
            print("DUT did not print a second illuminance value (expected +15 lx step)")
            return did_run, False

        if not _is_one_illuminance_increment(lux_1, lux_2):
            print(
                f"Illuminance did not increment by {ILLUMINANCE_STEP_LUX}: "
                f"{lux_1:.2f} lx -> {lux_2:.2f} lx"
            )
            return did_run, False

        ok, matter_2 = matter_otbr_util.matter_read_illuminance_lux(node_id=NODE_ID)
        if not ok or matter_2 is None:
            print("Failed to read illuminance MeasuredValue after increment")
            return did_run, False
        if abs(matter_2 - lux_2) > 0.5:
            print(
                f"Matter illuminance {matter_2:.2f} lx does not match Serial {lux_2:.2f} lx "
                f"after increment"
            )
            return did_run, False

        print(f"Illuminance increment OK: {lux_1:.2f} lx -> {lux_2:.2f} lx")
        return did_run, True
    finally:
        if monitor is not None:
            monitor.close()
