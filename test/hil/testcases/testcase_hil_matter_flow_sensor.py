import os
import re
import time

import util.hil_util as hil_util
import util.matter_otbr_util as matter_otbr_util

FLOW_SENSOR_SKETCH = os.path.normpath(os.path.join(
    os.path.dirname(__file__),
    "..", "..", "..",
    "libraries", "Matter", "examples", "matter_flow_sensor",
    "matter_flow_sensor.ino",
))

NODE_ID = matter_otbr_util.DEFAULT_NODE_ID

# Example: current_flow += 0.5f; if > 20.0f wrap to 0.0f
FLOW_STEP_M3H = 0.5
FLOW_SERIAL_RE = re.compile(r"Current flow: (\d+\.\d{2}) m3/h\n")


def _wait_for_next_flow_serial(monitor, after_index=0, timeout=30):
    """
    Wait for the next 'Current flow: X.XX m3/h' line at/after after_index.
    Returns (m3h, match_end_index) or (None, after_index).
    """
    print("-" * 40)
    print(f"Waiting up to {timeout}s for next flow Serial line (after idx {after_index})")
    print("-" * 40)
    deadline = time.time() + timeout
    while time.time() < deadline:
        text = monitor.text()
        for match in FLOW_SERIAL_RE.finditer(text):
            if match.start() >= after_index:
                m3h = float(match.group(1))
                print(f"Observed Serial flow: {m3h:.2f} m3/h")
                return m3h, match.end()
        time.sleep(0.1)
    print("Timed out waiting for flow Serial line")
    return None, after_index


def _is_one_flow_increment(previous, current):
    """True if current is previous + 0.5 m3/h, or wrap from >20 → 0.0."""
    expected = previous + FLOW_STEP_M3H
    if expected > 20.0:
        return current == 0.0
    return abs(current - expected) < 0.05


def testcase_hil_matter_flow_sensor(current_board, variant, current_board_port):
    """
    Testcase: HIL Matter flow sensor
    Description: Flashes the Matter flow sensor example, commissions it via SSH
    chip-tool on a Silicon Labs Matter Hub (Pi), then verifies one flow increment
    (+0.5 m3/h, wrapping >20 -> 0) on Serial and via MeasuredValue.

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
        current_board, variant, FLOW_SENSOR_SKETCH, current_board_port
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
                current_board, variant, FLOW_SENSOR_SKETCH, current_board_port, monitor
            )
            return ok

        if not matter_otbr_util.commission_with_defaults(
            node_id=NODE_ID, before_retry=_before_commission_retry
        ):
            print("Commissioning via Matter Hub failed")
            return did_run, False

        # First attribute read marks the appliance online so setup() can exit into loop()
        ok, _ = matter_otbr_util.matter_read_flow_m3h(node_id=NODE_ID)
        if not ok:
            print("flow attribute read failed (needed to mark DUT online)")
            return did_run, False

        if not monitor.wait_for("Matter device is now online", timeout=60):
            print("DUT did not come online on Matter after attribute read")
            return did_run, False

        flow_1, idx = _wait_for_next_flow_serial(monitor, after_index=0, timeout=30)
        if flow_1 is None:
            print("DUT did not print an initial flow value")
            return did_run, False

        ok, matter_1 = matter_otbr_util.matter_read_flow_m3h(node_id=NODE_ID)
        if not ok or matter_1 is None:
            print("Failed to read initial flow MeasuredValue")
            return did_run, False
        if abs(matter_1 - flow_1) > 0.05:
            print(f"Matter flow {matter_1:.2f} m3/h does not match Serial {flow_1:.2f} m3/h")
            return did_run, False

        # Example publishes every 10s; wait for the next stepped value
        flow_2, _ = _wait_for_next_flow_serial(monitor, after_index=idx, timeout=20)
        if flow_2 is None:
            print("DUT did not print a second flow value (expected +0.5 m3/h step)")
            return did_run, False

        if not _is_one_flow_increment(flow_1, flow_2):
            print(
                f"Flow did not increment by {FLOW_STEP_M3H}: "
                f"{flow_1:.2f} m3/h -> {flow_2:.2f} m3/h"
            )
            return did_run, False

        ok, matter_2 = matter_otbr_util.matter_read_flow_m3h(node_id=NODE_ID)
        if not ok or matter_2 is None:
            print("Failed to read flow MeasuredValue after increment")
            return did_run, False
        if abs(matter_2 - flow_2) > 0.05:
            print(
                f"Matter flow {matter_2:.2f} m3/h does not match Serial {flow_2:.2f} m3/h "
                f"after increment"
            )
            return did_run, False

        print(f"Flow increment OK: {flow_1:.2f} m3/h -> {flow_2:.2f} m3/h")
        return did_run, True
    finally:
        if monitor is not None:
            monitor.close()
