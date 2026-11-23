import os
import re
import time

import util.hil_util as hil_util
import util.matter_otbr_util as matter_otbr_util

CONTACT_SENSOR_SKETCH = os.path.normpath(os.path.join(
    os.path.dirname(__file__),
    "..", "sketches", "hil_matter_contact_sensor",
    "hil_matter_contact_sensor.ino",
))

NODE_ID = matter_otbr_util.DEFAULT_NODE_ID

CONTACT_SERIAL_RE = re.compile(
    r"Current contact state: (detected|lost)\n"
)


def _wait_for_next_contact_serial(monitor, after_index=0, timeout=30):
    """
    Wait for the next contact Serial line at/after after_index.
    Returns (detected_bool, match_end_index) or (None, after_index).
    """
    print("-" * 40)
    print(
        f"Waiting up to {timeout}s for next contact Serial line "
        f"(after idx {after_index})"
    )
    print("-" * 40)
    deadline = time.time() + timeout
    while time.time() < deadline:
        text = monitor.text()
        for match in CONTACT_SERIAL_RE.finditer(text):
            if match.start() >= after_index:
                detected = match.group(1) == "detected"
                print(
                    f"Observed Serial contact: "
                    f"{'detected' if detected else 'lost'}"
                )
                return detected, match.end()
        time.sleep(0.1)
    print("Timed out waiting for contact Serial line")
    return None, after_index


def _latest_contact_serial(monitor):
    """Return the last Serial contact bool, or None."""
    last = None
    for match in CONTACT_SERIAL_RE.finditer(monitor.text()):
        last = match.group(1) == "detected"
    return last


def _matter_contact_matches_serial(monitor, captured_detected, matter_detected):
    """
    Compare Matter StateValue to Serial, rebasing to the latest Serial line.
    chip-tool retries can span several 10s toggles.
    """
    serial_detected = _latest_contact_serial(monitor)
    if serial_detected is None:
        serial_detected = captured_detected
    elif serial_detected != captured_detected:
        print(
            "Serial baseline refreshed for Matter compare: "
            f"{'detected' if captured_detected else 'lost'} -> "
            f"{'detected' if serial_detected else 'lost'}"
        )
    if matter_detected != serial_detected:
        print(
            f"Matter contact {matter_detected} does not match Serial "
            f"{'detected' if serial_detected else 'lost'}"
        )
        return False
    return True


def testcase_hil_matter_contact_sensor(current_board, variant, current_board_port):
    """
    Testcase: HIL Matter contact sensor
    Description: Flashes a timed-toggle HIL contact sensor sketch, commissions
    it via SSH chip-tool on a Silicon Labs Matter Hub (Pi), then verifies one
    contact toggle (~10s) on Serial and via BooleanState StateValue.

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
        current_board, variant, CONTACT_SENSOR_SKETCH, current_board_port
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
                current_board, variant, CONTACT_SENSOR_SKETCH, current_board_port, monitor
            )
            return ok

        if not matter_otbr_util.commission_with_defaults(
            node_id=NODE_ID, before_retry=_before_commission_retry
        ):
            print("Commissioning via Matter Hub failed")
            return did_run, False

        # First attribute read marks the appliance online so setup() can exit into loop()
        ok, _ = matter_otbr_util.matter_read_contact_state(node_id=NODE_ID)
        if not ok:
            print("contact StateValue read failed (needed to mark DUT online)")
            return did_run, False

        if not monitor.wait_for("Matter device is now online", timeout=60):
            print("DUT did not come online on Matter after attribute read")
            return did_run, False

        # HIL sketch toggles every 10s (starts lost → first print is detected)
        contact_1, idx = _wait_for_next_contact_serial(monitor, after_index=0, timeout=30)
        if contact_1 is None:
            print("DUT did not print an initial contact state")
            return did_run, False

        ok, matter_1 = matter_otbr_util.matter_read_contact_state(node_id=NODE_ID)
        if not ok or matter_1 is None:
            print("Failed to read initial StateValue attribute")
            return did_run, False
        if not _matter_contact_matches_serial(monitor, contact_1, matter_1):
            return did_run, False

        contact_2, _ = _wait_for_next_contact_serial(monitor, after_index=idx, timeout=20)
        if contact_2 is None:
            print("DUT did not print a second contact state (expected toggle)")
            return did_run, False
        if contact_2 == contact_1:
            print(
                f"Contact did not toggle: stayed "
                f"{'detected' if contact_1 else 'lost'}"
            )
            return did_run, False

        ok, matter_2 = matter_otbr_util.matter_read_contact_state(node_id=NODE_ID)
        if not ok or matter_2 is None:
            print("Failed to read StateValue attribute after toggle")
            return did_run, False
        if not _matter_contact_matches_serial(monitor, contact_2, matter_2):
            return did_run, False

        print(
            f"Contact toggle OK: "
            f"{'detected' if contact_1 else 'lost'} -> "
            f"{'detected' if contact_2 else 'lost'}"
        )
        return did_run, True
    finally:
        if monitor is not None:
            monitor.close()
