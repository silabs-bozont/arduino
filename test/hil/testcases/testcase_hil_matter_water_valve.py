import os
import time

import util.hil_util as hil_util
import util.matter_otbr_util as matter_otbr_util

WATER_VALVE_SKETCH = os.path.normpath(os.path.join(
    os.path.dirname(__file__),
    "..", "..", "..",
    "libraries", "Matter", "examples", "matter_water_valve",
    "matter_water_valve.ino",
))

NODE_ID = matter_otbr_util.DEFAULT_NODE_ID

# Long enough that RemainingDuration is still non-null after a chip-tool CASE
# round-trip (~1–2s each). Auto-close wait stays bounded by this value.
TIMED_OPEN_DURATION_S = 20


def _wait_for_serial_after(monitor, needle, after_index=0, timeout=30):
    """
    Wait for needle to appear in SerialMonitor text at/after after_index.
    Returns (success, index_just_after_match).
    """
    print("-" * 40)
    print(f"Waiting up to {timeout}s for {needle!r} (after idx {after_index})")
    print("-" * 40)
    deadline = time.time() + timeout
    while time.time() < deadline:
        text = monitor.text()
        idx = text.find(needle, after_index)
        if idx >= 0:
            print(f"Serial matched {needle!r}")
            return True, idx + len(needle)
        time.sleep(0.1)
    print(f"Timed out waiting for {needle!r}")
    return False, after_index


def _expect_valve_state(node_id, expected_state, label):
    ok, state = matter_otbr_util.matter_read_water_valve_current_state(node_id=node_id)
    if not ok or state is None:
        print(f"Failed to read CurrentState ({label})")
        return False
    if state != expected_state:
        print(f"Expected CurrentState={expected_state} ({label}), got {state}")
        return False
    return True


def testcase_hil_matter_water_valve(current_board, variant, current_board_port):
    """
    Testcase: HIL Matter water valve
    Description: Flashes the Matter water valve example, commissions via the
    Matter Hub, opens/closes the valve, then does a timed open and waits for
    auto-close. Serial echoes and CurrentState are checked.

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
        current_board, variant, WATER_VALVE_SKETCH, current_board_port
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
                current_board, variant, WATER_VALVE_SKETCH, current_board_port, monitor
            )
            return ok

        if not matter_otbr_util.commission_with_defaults(
            node_id=NODE_ID, before_retry=_before_commission_retry
        ):
            print("Commissioning via Matter Hub failed")
            return did_run, False

        ok, _ = matter_otbr_util.matter_read_water_valve_current_state(node_id=NODE_ID)
        if not ok:
            print("current-state attribute read failed (needed to mark DUT online)")
            return did_run, False

        ok, cursor = _wait_for_serial_after(
            monitor, "Matter device is now online", after_index=0, timeout=60
        )
        if not ok:
            print("DUT did not come online on Matter after attribute read")
            return did_run, False

        # --- Indefinite open / close ---
        if not matter_otbr_util.matter_water_valve_open(duration_s=None, node_id=NODE_ID):
            print("water-valve Open (indefinite) failed")
            return did_run, False
        ok, cursor = _wait_for_serial_after(
            monitor, "Water valve state: OPEN", after_index=cursor, timeout=30
        )
        if not ok:
            print("Did not observe valve OPEN on Serial after Open")
            return did_run, False
        if not _expect_valve_state(
            NODE_ID, matter_otbr_util.WATER_VALVE_STATE_OPEN, "after Open"
        ):
            return did_run, False

        if not matter_otbr_util.matter_water_valve_close(node_id=NODE_ID):
            print("water-valve Close failed")
            return did_run, False
        ok, cursor = _wait_for_serial_after(
            monitor, "Water valve state: CLOSED", after_index=cursor, timeout=30
        )
        if not ok:
            print("Did not observe valve CLOSED on Serial after Close")
            return did_run, False
        if not _expect_valve_state(
            NODE_ID, matter_otbr_util.WATER_VALVE_STATE_CLOSED, "after Close"
        ):
            return did_run, False

        # --- Timed open → countdown → auto-close ---
        # Read RemainingDuration before CurrentState: each chip-tool invoke is a
        # fresh CASE session (~1–2s), and a short timer can expire between reads.
        if not matter_otbr_util.matter_water_valve_open(
            duration_s=TIMED_OPEN_DURATION_S, node_id=NODE_ID
        ):
            print(f"water-valve Open (timed {TIMED_OPEN_DURATION_S}s) failed")
            return did_run, False
        ok, cursor = _wait_for_serial_after(
            monitor, "Water valve state: OPEN", after_index=cursor, timeout=30
        )
        if not ok:
            print("Did not observe valve OPEN on Serial after timed Open")
            return did_run, False

        ok, remaining = matter_otbr_util.matter_read_water_valve_remaining_duration(
            node_id=NODE_ID
        )
        if not ok:
            print("Failed to read RemainingDuration after timed Open")
            return did_run, False
        if remaining is None or remaining < 1 or remaining > TIMED_OPEN_DURATION_S:
            print(
                f"RemainingDuration {remaining} not in 1..{TIMED_OPEN_DURATION_S} "
                f"after timed Open"
            )
            return did_run, False

        if not _expect_valve_state(
            NODE_ID, matter_otbr_util.WATER_VALVE_STATE_OPEN, "after timed Open"
        ):
            return did_run, False

        ok, cursor = _wait_for_serial_after(
            monitor,
            "Water valve remaining duration:",
            after_index=cursor,
            timeout=remaining + 5,
        )
        if not ok:
            print("Did not observe remaining-duration countdown on Serial")
            return did_run, False

        ok, cursor = _wait_for_serial_after(
            monitor,
            "Water valve state: CLOSED",
            after_index=cursor,
            timeout=remaining + 15,
        )
        if not ok:
            print("Did not observe valve CLOSED on Serial after timed Open elapsed")
            return did_run, False
        if not _expect_valve_state(
            NODE_ID, matter_otbr_util.WATER_VALVE_STATE_CLOSED, "after timed Open elapsed"
        ):
            return did_run, False

        print("Water valve open/close and timed open OK")
        return did_run, True
    finally:
        if monitor is not None:
            monitor.close()
