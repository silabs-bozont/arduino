import os
import random
import time

import util.hil_util as hil_util
import util.matter_otbr_util as matter_otbr_util

SENSOR_AND_BULB_SKETCH = os.path.normpath(os.path.join(
    os.path.dirname(__file__),
    "..", "..", "..",
    "libraries", "Matter", "examples", "matter_sensor_and_bulb",
    "matter_sensor_and_bulb.ino",
))

NODE_ID = matter_otbr_util.DEFAULT_NODE_ID
# begin() order: dimmable bulb then temperature sensor
BULB_ENDPOINT = matter_otbr_util.DEFAULT_ENDPOINT  # 3
TEMP_ENDPOINT = matter_otbr_util.DEFAULT_ENDPOINT + 1  # 4
BRIGHTNESS_SAMPLES = 5
TEMP_MIN_C = 0.0
TEMP_MAX_C = 60.0


def testcase_hil_matter_sensor_and_bulb(current_board, variant, current_board_port):
    """
    Testcase: HIL Matter sensor and bulb (multi-endpoint)
    Description: Flashes the Matter sensor_and_bulb example (dimmable bulb +
    temperature sensor on separate dynamic endpoints), commissions via the
    Matter Hub, then exercises the bulb like matter_lightbulb_dimmable and the
    temp sensor like matter_temp_sensor.

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
        current_board, variant, SENSOR_AND_BULB_SKETCH, current_board_port
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
                current_board, variant, SENSOR_AND_BULB_SKETCH, current_board_port, monitor
            )
            return ok

        if not matter_otbr_util.commission_with_defaults(
            node_id=NODE_ID, before_retry=_before_commission_retry
        ):
            print("Commissioning via Matter Hub failed")
            return did_run, False

        # Both appliances must see an attribute read before setup() exits
        if not matter_otbr_util.matter_read_onoff(
            node_id=NODE_ID, endpoint=BULB_ENDPOINT
        ):
            print(
                f"onoff attribute read failed on endpoint {BULB_ENDPOINT} "
                "(needed to mark bulb online)"
            )
            return did_run, False

        ok, _ = matter_otbr_util.matter_read_temperature_celsius(
            node_id=NODE_ID, endpoint=TEMP_ENDPOINT
        )
        if not ok:
            print(
                f"temperature attribute read failed on endpoint {TEMP_ENDPOINT} "
                "(needed to mark temp sensor online)"
            )
            return did_run, False

        if not monitor.wait_for("Matter devices are now online", timeout=60):
            print("DUT did not report both devices online after attribute reads")
            return did_run, False

        # --- Dimmable bulb (endpoint 3), same as matter_lightbulb_dimmable ---
        if not matter_otbr_util.matter_onoff(
            True, node_id=NODE_ID, endpoint=BULB_ENDPOINT
        ):
            print("matter on command failed")
            return did_run, False

        if not monitor.wait_for("Bulb ON,", timeout=30):
            print("Did not observe 'Bulb ON' on serial")
            return did_run, False

        percents = random.sample(range(1, 101), BRIGHTNESS_SAMPLES)
        print(f"Testing brightness percents: {percents}")

        for pct in percents:
            if not matter_otbr_util.matter_set_brightness_percent(
                pct, node_id=NODE_ID, endpoint=BULB_ENDPOINT
            ):
                print(f"move-to-level for {pct}% failed")
                return did_run, False

            expected = f"Bulb brightness changed to {pct}%\n"
            if not monitor.wait_for(expected, timeout=30):
                print(f"Did not observe Serial echo for brightness {pct}%")
                return did_run, False

        if not matter_otbr_util.matter_onoff(
            False, node_id=NODE_ID, endpoint=BULB_ENDPOINT
        ):
            print("matter off command failed")
            return did_run, False

        if not monitor.wait_for("Bulb OFF", timeout=30):
            print("Did not observe 'Bulb OFF' on serial")
            return did_run, False

        # --- Temperature sensor (endpoint 4), same as matter_temp_sensor ---
        # Example publishes getCPUTemp() every 10s
        if not monitor.wait_for("Current CPU temperature:", timeout=30):
            print("DUT did not print a CPU temperature update")
            return did_run, False
        time.sleep(1)

        ok, temp_c = matter_otbr_util.matter_read_temperature_celsius(
            node_id=NODE_ID, endpoint=TEMP_ENDPOINT
        )
        if not ok or temp_c is None:
            print("Failed to read temperature MeasuredValue after DUT started publishing")
            return did_run, False

        if not (TEMP_MIN_C < temp_c <= TEMP_MAX_C):
            print(
                f"Implausible CPU temperature {temp_c:.2f} C "
                f"(expected {TEMP_MIN_C} < temp <= {TEMP_MAX_C}; 0.0 is the unset default)"
            )
            return did_run, False

        print(
            f"Multi-endpoint OK: bulb ep{BULB_ENDPOINT}, "
            f"temp ep{TEMP_ENDPOINT} = {temp_c:.2f} C"
        )
        return did_run, True
    finally:
        if monitor is not None:
            monitor.close()
