import os
import re
import time

import util.hil_util as hil_util
import util.matter_otbr_util as matter_otbr_util

RAIN_SENSOR_SKETCH = os.path.normpath(os.path.join(
    os.path.dirname(__file__),
    "..", "sketches", "hil_matter_rain_sensor",
    "hil_matter_rain_sensor.ino",
))

NODE_ID = matter_otbr_util.DEFAULT_NODE_ID

RAIN_SERIAL_RE = re.compile(
    r"Current rain sensor state: (raining|dry)\n"
)


def _wait_for_next_rain_serial(monitor, after_index=0, timeout=30):
    """
    Wait for the next rain Serial line at/after after_index.
    Returns (raining_bool, match_end_index) or (None, after_index).
    """
    print("-" * 40)
    print(
        f"Waiting up to {timeout}s for next rain Serial line "
        f"(after idx {after_index})"
    )
    print("-" * 40)
    deadline = time.time() + timeout
    while time.time() < deadline:
        text = monitor.text()
        for match in RAIN_SERIAL_RE.finditer(text):
            if match.start() >= after_index:
                raining = match.group(1) == "raining"
                print(
                    f"Observed Serial rain: "
                    f"{'raining' if raining else 'dry'}"
                )
                return raining, match.end()
        time.sleep(0.1)
    print("Timed out waiting for rain Serial line")
    return None, after_index


def _latest_rain_serial(monitor):
    """Return the last Serial rain bool, or None."""
    last = None
    for match in RAIN_SERIAL_RE.finditer(monitor.text()):
        last = match.group(1) == "raining"
    return last


def _matter_rain_matches_serial(monitor, captured_raining, matter_raining):
    """
    Compare Matter StateValue to Serial, rebasing to the latest Serial line.
    chip-tool retries can span several 10s toggles.
    """
    serial_raining = _latest_rain_serial(monitor)
    if serial_raining is None:
        serial_raining = captured_raining
    elif serial_raining != captured_raining:
        print(
            "Serial baseline refreshed for Matter compare: "
            f"{'raining' if captured_raining else 'dry'} -> "
            f"{'raining' if serial_raining else 'dry'}"
        )
    if matter_raining != serial_raining:
        print(
            f"Matter rain {matter_raining} does not match Serial "
            f"{'raining' if serial_raining else 'dry'}"
        )
        return False
    return True


def testcase_hil_matter_rain_sensor(current_board, variant, current_board_port):
    """
    Testcase: HIL Matter rain sensor
    Description: Flashes a timed-toggle HIL rain sensor sketch, commissions it
    via SSH chip-tool on a Silicon Labs Matter Hub (Pi), then verifies one rain
    toggle (~10s) on Serial and via BooleanState StateValue.

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
        current_board, variant, RAIN_SENSOR_SKETCH, current_board_port
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
                current_board, variant, RAIN_SENSOR_SKETCH, current_board_port, monitor
            )
            return ok

        if not matter_otbr_util.commission_with_defaults(
            node_id=NODE_ID, before_retry=_before_commission_retry
        ):
            print("Commissioning via Matter Hub failed")
            return did_run, False

        # First attribute read marks the appliance online so setup() can exit into loop()
        ok, _ = matter_otbr_util.matter_read_rain_state(node_id=NODE_ID)
        if not ok:
            print("rain StateValue read failed (needed to mark DUT online)")
            return did_run, False

        if not monitor.wait_for("Matter device is now online", timeout=60):
            print("DUT did not come online on Matter after attribute read")
            return did_run, False

        # HIL sketch toggles every 10s (starts dry → first print is raining)
        rain_1, idx = _wait_for_next_rain_serial(monitor, after_index=0, timeout=30)
        if rain_1 is None:
            print("DUT did not print an initial rain state")
            return did_run, False

        ok, matter_1 = matter_otbr_util.matter_read_rain_state(node_id=NODE_ID)
        if not ok or matter_1 is None:
            print("Failed to read initial StateValue attribute")
            return did_run, False
        if not _matter_rain_matches_serial(monitor, rain_1, matter_1):
            return did_run, False

        rain_2, _ = _wait_for_next_rain_serial(monitor, after_index=idx, timeout=20)
        if rain_2 is None:
            print("DUT did not print a second rain state (expected toggle)")
            return did_run, False
        if rain_2 == rain_1:
            print(
                f"Rain did not toggle: stayed "
                f"{'raining' if rain_1 else 'dry'}"
            )
            return did_run, False

        ok, matter_2 = matter_otbr_util.matter_read_rain_state(node_id=NODE_ID)
        if not ok or matter_2 is None:
            print("Failed to read StateValue attribute after toggle")
            return did_run, False
        if not _matter_rain_matches_serial(monitor, rain_2, matter_2):
            return did_run, False

        print(
            f"Rain toggle OK: "
            f"{'raining' if rain_1 else 'dry'} -> "
            f"{'raining' if rain_2 else 'dry'}"
        )
        return did_run, True
    finally:
        if monitor is not None:
            monitor.close()
