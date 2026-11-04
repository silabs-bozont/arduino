import os
import time

import util.hil_util as hil_util
import util.matter_otbr_util as matter_otbr_util

TEMP_SENSOR_SKETCH = os.path.normpath(os.path.join(
    os.path.dirname(__file__),
    "..", "..", "..",
    "libraries", "Matter", "examples", "matter_temp_sensor", "matter_temp_sensor.ino",
))

NODE_ID = matter_otbr_util.DEFAULT_NODE_ID

# Plausible CPU temperature after the example starts publishing getCPUTemp().
# Exactly 0.0 C is the default / unset MeasuredValue and must fail.
TEMP_MIN_C = 0.0
TEMP_MAX_C = 60.0


def testcase_hil_matter_temp_sensor(current_board, variant, current_board_port):
    """
    Testcase: HIL Matter temperature sensor
    Description: Flashes the Matter temperature sensor example, commissions it via
    SSH chip-tool on a Silicon Labs Matter Hub (Pi), then reads MeasuredValue and
    checks it is a plausible non-zero CPU temperature.

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
        current_board, variant, TEMP_SENSOR_SKETCH, current_board_port
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

        if not matter_otbr_util.commission_with_defaults(node_id=NODE_ID):
            print("Commissioning via Matter Hub failed")
            return did_run, False

        # First attribute read marks the appliance online so setup() can exit into loop()
        ok, _ = matter_otbr_util.matter_read_temperature_celsius(node_id=NODE_ID)
        if not ok:
            print("temperature attribute read failed (needed to mark DUT online)")
            return did_run, False

        if not monitor.wait_for("Matter device is now online", timeout=60):
            print("DUT did not come online on Matter after attribute read")
            return did_run, False

        # loop() publishes getCPUTemp() every 2s; wait until at least one update ran
        if not monitor.wait_for("Current CPU temperature:", timeout=30):
            print("DUT did not print a CPU temperature update")
            return did_run, False
        time.sleep(1)

        ok, temp_c = matter_otbr_util.matter_read_temperature_celsius(node_id=NODE_ID)
        if not ok or temp_c is None:
            print("Failed to read temperature MeasuredValue after DUT started publishing")
            return did_run, False

        if not (TEMP_MIN_C < temp_c <= TEMP_MAX_C):
            print(
                f"Implausible CPU temperature {temp_c:.2f} C "
                f"(expected {TEMP_MIN_C} < temp <= {TEMP_MAX_C}; 0.0 is the unset default)"
            )
            return did_run, False

        print(f"CPU temperature reading OK: {temp_c:.2f} C")
        return did_run, True
    finally:
        if monitor is not None:
            monitor.close()
