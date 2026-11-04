import os
import time

import util.hil_util as hil_util
import util.matter_otbr_util as matter_otbr_util

LIGHTBULB_SKETCH = os.path.normpath(os.path.join(
    os.path.dirname(__file__),
    "..", "..", "..",
    "libraries", "Matter", "examples", "matter_lightbulb", "matter_lightbulb.ino",
))

NODE_ID = matter_otbr_util.DEFAULT_NODE_ID


def testcase_hil_matter_lightbulb(current_board, variant, current_board_port):
    """
    Testcase: HIL Matter lightbulb (on/off)
    Description: Flashes the Matter on/off lightbulb example, commissions it via
    SSH chip-tool on a Silicon Labs Matter Hub (Pi) using the default development
    pairing code, then toggles on/off and checks DUT Serial for Bulb ON / Bulb OFF.

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

    success = hil_util.arduino_cli_build_and_flash(
        current_board, variant, LIGHTBULB_SKETCH, current_board_port
    )
    if not success:
        print(f"Build/upload failed for '{variant}' on '{current_board}'")
        return did_run, False

    # Open serial before commissioning so Thread/online/on/off lines are not missed.
    # Pairing codes are printed at boot and are easy to miss after upload; Arduino
    # Matter examples use the CHIP defaults, so we do not read them from Serial.
    time.sleep(2)
    try:
        monitor = hil_util.SerialMonitor(current_board_port)
    except Exception as e:
        print(f"Failed to open serial monitor: {e}")
        return did_run, False

    try:
        # Give the Matter stack a moment to start BLE advertising after reset
        time.sleep(5)

        if not matter_otbr_util.commission_with_defaults(node_id=NODE_ID):
            print("Commissioning via Matter Hub failed")
            return did_run, False

        # is_online() becomes true only after a controller attribute read
        if not matter_otbr_util.matter_read_onoff(node_id=NODE_ID):
            print("onoff attribute read failed (needed to mark DUT online)")
            return did_run, False

        if not monitor.wait_for("Matter device is now online", timeout=60):
            print("DUT did not come online on Matter after attribute read")
            return did_run, False

        if not matter_otbr_util.matter_onoff(True, node_id=NODE_ID):
            print("matter on command failed")
            return did_run, False

        if not monitor.wait_for("Bulb ON", timeout=30):
            print("Did not observe 'Bulb ON' on serial")
            return did_run, False

        if not matter_otbr_util.matter_onoff(False, node_id=NODE_ID):
            print("matter off command failed")
            return did_run, False

        if not monitor.wait_for("Bulb OFF", timeout=30):
            print("Did not observe 'Bulb OFF' on serial")
            return did_run, False

        return did_run, True
    finally:
        if monitor is not None:
            monitor.close()
