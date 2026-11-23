import os
import time

import util.hil_util as hil_util
import util.matter_otbr_util as matter_otbr_util

SWITCH_SKETCH = os.path.normpath(os.path.join(
    os.path.dirname(__file__),
    "..", "sketches", "hil_matter_switch",
    "hil_matter_switch.ino",
))

NODE_ID = matter_otbr_util.DEFAULT_NODE_ID


def testcase_hil_matter_switch(current_board, variant, current_board_port):
    """
    Testcase: HIL Matter switch
    Description: Flashes a Serial-driven Matter switch HIL sketch, commissions
    it via SSH chip-tool, simulates press/release over Serial, and checks
    Switch CurrentPosition (1 pressed / 0 released) plus DUT Serial echoes.

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
        current_board, variant, SWITCH_SKETCH, current_board_port
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
                current_board, variant, SWITCH_SKETCH, current_board_port, monitor
            )
            return ok

        if not matter_otbr_util.commission_with_defaults(
            node_id=NODE_ID, before_retry=_before_commission_retry
        ):
            print("Commissioning via Matter Hub failed")
            return did_run, False

        # First attribute read marks the appliance online so setup() can exit into loop()
        ok, pos = matter_otbr_util.matter_read_switch_current_position(node_id=NODE_ID)
        if not ok or pos is None:
            print("CurrentPosition read failed (needed to mark DUT online)")
            return did_run, False

        if not monitor.wait_for("Matter device is now online", timeout=60):
            print("DUT did not come online on Matter after attribute read")
            return did_run, False

        if not monitor.wait_for("HIL switch ready", timeout=30):
            print("DUT did not report HIL switch ready")
            return did_run, False

        if pos != 0:
            print(f"Expected initial CurrentPosition 0 (released), got {pos}")
            return did_run, False

        monitor.write("press\n")
        if not monitor.wait_for("\nSwitch pressed\n", timeout=30):
            print("Did not observe 'Switch pressed' on serial")
            return did_run, False

        ok, pos = matter_otbr_util.matter_read_switch_current_position(node_id=NODE_ID)
        if not ok or pos != 1:
            print(f"Expected CurrentPosition 1 after press, got {pos}")
            return did_run, False

        monitor.write("release\n")
        if not monitor.wait_for("\nSwitch released\n", timeout=30):
            print("Did not observe 'Switch released' on serial")
            return did_run, False

        ok, pos = matter_otbr_util.matter_read_switch_current_position(node_id=NODE_ID)
        if not ok or pos != 0:
            print(f"Expected CurrentPosition 0 after release, got {pos}")
            return did_run, False

        print("Switch press/release CurrentPosition OK")
        return did_run, True
    finally:
        if monitor is not None:
            monitor.close()
