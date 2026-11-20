import os
import re
import time

import util.hil_util as hil_util
import util.matter_otbr_util as matter_otbr_util

OCCUPANCY_SENSOR_SKETCH = os.path.normpath(os.path.join(
    os.path.dirname(__file__),
    "..", "..", "..",
    "libraries", "Matter", "examples", "matter_occupancy_sensor",
    "matter_occupancy_sensor.ino",
))

NODE_ID = matter_otbr_util.DEFAULT_NODE_ID

OCCUPANCY_SERIAL_RE = re.compile(
    r"Current occupancy state: (occupied|unoccupied)\n"
)


def _wait_for_next_occupancy_serial(monitor, after_index=0, timeout=30):
    """
    Wait for the next occupancy Serial line at/after after_index.
    Returns (occupied_bool, match_end_index) or (None, after_index).
    """
    print("-" * 40)
    print(
        f"Waiting up to {timeout}s for next occupancy Serial line "
        f"(after idx {after_index})"
    )
    print("-" * 40)
    deadline = time.time() + timeout
    while time.time() < deadline:
        text = monitor.text()
        for match in OCCUPANCY_SERIAL_RE.finditer(text):
            if match.start() >= after_index:
                occupied = match.group(1) == "occupied"
                print(
                    f"Observed Serial occupancy: "
                    f"{'occupied' if occupied else 'unoccupied'}"
                )
                return occupied, match.end()
        time.sleep(0.1)
    print("Timed out waiting for occupancy Serial line")
    return None, after_index


def _latest_occupancy_serial(monitor):
    """Return the last Serial occupancy bool, or None."""
    last = None
    for match in OCCUPANCY_SERIAL_RE.finditer(monitor.text()):
        last = match.group(1) == "occupied"
    return last


def _matter_occupancy_matches_serial(monitor, captured_occupied, matter_occupied):
    """
    Compare Matter Occupancy to Serial, rebasing to the latest Serial line.
    chip-tool retries can span several 10s toggles.
    """
    serial_occupied = _latest_occupancy_serial(monitor)
    if serial_occupied is None:
        serial_occupied = captured_occupied
    elif serial_occupied != captured_occupied:
        print(
            "Serial baseline refreshed for Matter compare: "
            f"{'occupied' if captured_occupied else 'unoccupied'} -> "
            f"{'occupied' if serial_occupied else 'unoccupied'}"
        )
    if matter_occupied != serial_occupied:
        print(
            f"Matter occupancy {matter_occupied} does not match Serial "
            f"{'occupied' if serial_occupied else 'unoccupied'}"
        )
        return False
    return True


def testcase_hil_matter_occupancy_sensor(current_board, variant, current_board_port):
    """
    Testcase: HIL Matter occupancy sensor
    Description: Flashes the Matter occupancy sensor example, commissions it via
    SSH chip-tool on a Silicon Labs Matter Hub (Pi), then verifies one occupancy
    toggle (~10s) on Serial and via the Occupancy attribute.

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
        current_board, variant, OCCUPANCY_SENSOR_SKETCH, current_board_port
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
                current_board, variant, OCCUPANCY_SENSOR_SKETCH, current_board_port, monitor
            )
            return ok

        if not matter_otbr_util.commission_with_defaults(
            node_id=NODE_ID, before_retry=_before_commission_retry
        ):
            print("Commissioning via Matter Hub failed")
            return did_run, False

        # First attribute read marks the appliance online so setup() can exit into loop()
        ok, _ = matter_otbr_util.matter_read_occupancy(node_id=NODE_ID)
        if not ok:
            print("occupancy attribute read failed (needed to mark DUT online)")
            return did_run, False

        if not monitor.wait_for("Matter device is now online", timeout=60):
            print("DUT did not come online on Matter after attribute read")
            return did_run, False

        # Example toggles every 10s (starts unoccupied → first print is occupied)
        occ_1, idx = _wait_for_next_occupancy_serial(monitor, after_index=0, timeout=30)
        if occ_1 is None:
            print("DUT did not print an initial occupancy state")
            return did_run, False

        ok, matter_1 = matter_otbr_util.matter_read_occupancy(node_id=NODE_ID)
        if not ok or matter_1 is None:
            print("Failed to read initial Occupancy attribute")
            return did_run, False
        if not _matter_occupancy_matches_serial(monitor, occ_1, matter_1):
            return did_run, False

        occ_2, _ = _wait_for_next_occupancy_serial(monitor, after_index=idx, timeout=20)
        if occ_2 is None:
            print("DUT did not print a second occupancy state (expected toggle)")
            return did_run, False
        if occ_2 == occ_1:
            print(
                f"Occupancy did not toggle: stayed "
                f"{'occupied' if occ_1 else 'unoccupied'}"
            )
            return did_run, False

        ok, matter_2 = matter_otbr_util.matter_read_occupancy(node_id=NODE_ID)
        if not ok or matter_2 is None:
            print("Failed to read Occupancy attribute after toggle")
            return did_run, False
        if not _matter_occupancy_matches_serial(monitor, occ_2, matter_2):
            return did_run, False

        print(
            f"Occupancy toggle OK: "
            f"{'occupied' if occ_1 else 'unoccupied'} -> "
            f"{'occupied' if occ_2 else 'unoccupied'}"
        )
        return did_run, True
    finally:
        if monitor is not None:
            monitor.close()
