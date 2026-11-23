import os
import time

import util.hil_util as hil_util
import util.matter_otbr_util as matter_otbr_util

DOOR_LOCK_SKETCH = os.path.normpath(os.path.join(
    os.path.dirname(__file__),
    "..", "..", "..",
    "libraries", "Matter", "examples", "matter_door_lock", "matter_door_lock.ino",
))

NODE_ID = matter_otbr_util.DEFAULT_NODE_ID


def testcase_hil_matter_door_lock(current_board, variant, current_board_port):
    """
    Testcase: HIL Matter door lock
    Description: Flashes the Matter door lock example, commissions it via SSH
    chip-tool on a Silicon Labs Matter Hub (Pi), then lock-door / unlock-door
    and checks DUT Serial for Locked / Unlocked.

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
        current_board, variant, DOOR_LOCK_SKETCH, current_board_port
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
                current_board, variant, DOOR_LOCK_SKETCH, current_board_port, monitor
            )
            return ok

        if not matter_otbr_util.commission_with_defaults(
            node_id=NODE_ID, before_retry=_before_commission_retry
        ):
            print("Commissioning via Matter Hub failed")
            return did_run, False

        # is_online() becomes true only after a controller attribute read
        if not matter_otbr_util.matter_read_lock_state(node_id=NODE_ID):
            print("lock-state attribute read failed (needed to mark DUT online)")
            return did_run, False

        if not monitor.wait_for("Matter device is now online", timeout=60):
            print("DUT did not come online on Matter after attribute read")
            return did_run, False

        # Device starts unlocked; lock then unlock and check Serial transitions.
        # Use "\nLocked\n" so it does not match as a substring of "Unlocked".
        if not matter_otbr_util.matter_door_lock(node_id=NODE_ID):
            print("matter lock-door command failed")
            return did_run, False

        if not monitor.wait_for("\nLocked\n", timeout=30):
            print("Did not observe 'Locked' on serial")
            return did_run, False

        if not matter_otbr_util.matter_door_unlock(node_id=NODE_ID):
            print("matter unlock-door command failed")
            return did_run, False

        if not monitor.wait_for("\nUnlocked\n", timeout=30):
            print("Did not observe 'Unlocked' on serial")
            return did_run, False

        return did_run, True
    finally:
        if monitor is not None:
            monitor.close()
