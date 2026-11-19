import os
import re
import time

import util.hil_util as hil_util
import util.matter_otbr_util as matter_otbr_util

TVOC_SENSOR_SKETCH = os.path.normpath(os.path.join(
    os.path.dirname(__file__),
    "..", "..", "..",
    "libraries", "Matter", "examples", "matter_tvoc_sensor", "matter_tvoc_sensor.ino",
))

NODE_ID = matter_otbr_util.DEFAULT_NODE_ID

# Example: current_tvoc += 15.0f; if > 10000.0f wrap to 0.0f
TVOC_STEP_PPB = 15.0
TVOC_SERIAL_RE = re.compile(r"Current TVOC concentration: (\d+) ppb\n")


def _wait_for_next_tvoc_serial(monitor, after_index=0, timeout=30):
    """
    Wait for the next 'Current TVOC concentration: N ppb' line at/after after_index.
    Returns (ppb, match_end_index) or (None, after_index).
    """
    print("-" * 40)
    print(f"Waiting up to {timeout}s for next TVOC Serial line (after idx {after_index})")
    print("-" * 40)
    deadline = time.time() + timeout
    while time.time() < deadline:
        text = monitor.text()
        for match in TVOC_SERIAL_RE.finditer(text):
            if match.start() >= after_index:
                ppb = float(match.group(1))
                print(f"Observed Serial TVOC: {ppb:.0f} ppb")
                return ppb, match.end()
        time.sleep(0.1)
    print("Timed out waiting for TVOC Serial line")
    return None, after_index


def _is_one_tvoc_increment(previous, current):
    """True if current is previous + 15 ppb, or wrap from >10000 path (10005→0)."""
    expected = previous + TVOC_STEP_PPB
    if expected > 10000.0:
        return current == 0.0
    return abs(current - expected) < 0.5


def testcase_hil_matter_tvoc_sensor(current_board, variant, current_board_port):
    """
    Testcase: HIL Matter TVOC sensor
    Description: Flashes the Matter TVOC sensor example, commissions it via SSH
    chip-tool on a Silicon Labs Matter Hub (Pi), then verifies one concentration
    increment (+15 ppb, wrapping above 10000 -> 0) on Serial and via MeasuredValue.

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
        current_board, variant, TVOC_SENSOR_SKETCH, current_board_port
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
                current_board, variant, TVOC_SENSOR_SKETCH, current_board_port, monitor
            )
            return ok

        if not matter_otbr_util.commission_with_defaults(
            node_id=NODE_ID, before_retry=_before_commission_retry
        ):
            print("Commissioning via Matter Hub failed")
            return did_run, False

        # First attribute read marks the appliance online so setup() can exit into loop()
        ok, _ = matter_otbr_util.matter_read_tvoc_ppb(node_id=NODE_ID)
        if not ok:
            print("TVOC attribute read failed (needed to mark DUT online)")
            return did_run, False

        if not monitor.wait_for("Matter device is now online", timeout=60):
            print("DUT did not come online on Matter after attribute read")
            return did_run, False

        tvoc_1, idx = _wait_for_next_tvoc_serial(monitor, after_index=0, timeout=30)
        if tvoc_1 is None:
            print("DUT did not print an initial TVOC value")
            return did_run, False

        ok, matter_1 = matter_otbr_util.matter_read_tvoc_ppb(node_id=NODE_ID)
        if not ok or matter_1 is None:
            print("Failed to read initial TVOC MeasuredValue")
            return did_run, False
        if abs(matter_1 - tvoc_1) > 0.5:
            print(f"Matter TVOC {matter_1:.0f} ppb does not match Serial {tvoc_1:.0f} ppb")
            return did_run, False

        # Example publishes every 10s; wait for the next stepped value
        tvoc_2, _ = _wait_for_next_tvoc_serial(monitor, after_index=idx, timeout=20)
        if tvoc_2 is None:
            print("DUT did not print a second TVOC value (expected +15 ppb step)")
            return did_run, False

        if not _is_one_tvoc_increment(tvoc_1, tvoc_2):
            print(
                f"TVOC did not increment by {TVOC_STEP_PPB:.0f} ppb: "
                f"{tvoc_1:.0f} -> {tvoc_2:.0f}"
            )
            return did_run, False

        ok, matter_2 = matter_otbr_util.matter_read_tvoc_ppb(node_id=NODE_ID)
        if not ok or matter_2 is None:
            print("Failed to read TVOC MeasuredValue after increment")
            return did_run, False
        if abs(matter_2 - tvoc_2) > 0.5:
            print(
                f"Matter TVOC {matter_2:.0f} ppb does not match Serial {tvoc_2:.0f} ppb "
                f"after increment"
            )
            return did_run, False

        print(f"TVOC increment OK: {tvoc_1:.0f} ppb -> {tvoc_2:.0f} ppb")
        return did_run, True
    finally:
        if monitor is not None:
            monitor.close()
