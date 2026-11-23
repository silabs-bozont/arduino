import os
import time

import util.hil_util as hil_util
import util.matter_otbr_util as matter_otbr_util

DECOMMISSION_SKETCH = os.path.normpath(os.path.join(
    os.path.dirname(__file__),
    "..", "sketches", "hil_matter_decommission",
    "hil_matter_decommission.ino",
))

NODE_ID = matter_otbr_util.DEFAULT_NODE_ID


def testcase_hil_matter_decommission(current_board, variant, current_board_port):
    """
    Testcase: HIL Matter decommission
    Description: Flashes a Serial-triggered decommission HIL sketch, commissions
    it via SSH chip-tool on a Silicon Labs Matter Hub (Pi), sends 'decommission'
    over Serial, then verifies the DUT reboots into an uncommissioned state.

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
        current_board, variant, DECOMMISSION_SKETCH, current_board_port
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
                current_board, variant, DECOMMISSION_SKETCH, current_board_port, monitor
            )
            return ok

        if not matter_otbr_util.commission_with_defaults(
            node_id=NODE_ID, before_retry=_before_commission_retry
        ):
            print("Commissioning via Matter Hub failed")
            return did_run, False

        if not matter_otbr_util.matter_read_onoff(node_id=NODE_ID):
            print("onoff attribute read failed (needed to mark DUT online)")
            return did_run, False

        if not monitor.wait_for("Matter device is now online", timeout=60):
            print("DUT did not come online on Matter after attribute read")
            return did_run, False

        if not monitor.wait_for("HIL decommission ready", timeout=30):
            print("DUT did not report HIL decommission ready")
            return did_run, False

        monitor.write("decommission\n")

        decommission_msg = "Starting decommissioning process, device will reboot..."
        if not monitor.wait_for(decommission_msg, timeout=30):
            print("Did not observe decommission start on Serial")
            return did_run, False

        # MCU reboots; Ignore pre-commission boot lines by searching after this point
        after = monitor.text().rfind(decommission_msg) + len(decommission_msg)

        if not monitor.wait_for("Matter decommission HIL", timeout=90, after_index=after):
            print("DUT did not reprint HIL banner after reboot")
            return did_run, False

        if not monitor.wait_for(
            "Matter device is not commissioned", timeout=60, after_index=after
        ):
            print("DUT did not report uncommissioned state after reboot")
            return did_run, False

        if not monitor.wait_for("Manual pairing code:", timeout=30, after_index=after):
            print("DUT did not print pairing code after decommission")
            return did_run, False

        print("Decommission + reboot into uncommissioned state OK")
        return did_run, True
    finally:
        if monitor is not None:
            monitor.close()
