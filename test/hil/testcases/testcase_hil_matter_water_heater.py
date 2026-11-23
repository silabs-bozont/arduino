import os
import random
import time

import util.hil_util as hil_util
import util.matter_otbr_util as matter_otbr_util

WATER_HEATER_SKETCH = os.path.normpath(os.path.join(
    os.path.dirname(__file__),
    "..", "..", "..",
    "libraries", "Matter", "examples", "matter_water_heater",
    "matter_water_heater.ino",
))

NODE_ID = matter_otbr_util.DEFAULT_NODE_ID

# Same Off/Heat values as MatterWaterHeater::water_heater_mode_t / Thermostat SystemMode
WATER_HEATER_MODE_CHECKS = [
    (matter_otbr_util.THERMOSTAT_MODE_HEAT, "Water heater mode: HEAT"),
    (matter_otbr_util.THERMOSTAT_MODE_OFF, "Water heater mode: OFF"),
    (matter_otbr_util.THERMOSTAT_MODE_HEAT, "Water heater mode: HEAT"),
]

SETPOINT_SAMPLES = 3


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


def _setpoint_serial_line(celsius):
    # Example: Serial.printf("Water heater setpoint: %.01f C\\n", ...)
    return f"Water heater setpoint: {celsius:.1f} C\n"


def testcase_hil_matter_water_heater(current_board, variant, current_board_port):
    """
    Testcase: HIL Matter water heater
    Description: Flashes the Matter water heater example, commissions via the
    Matter Hub, toggles SystemMode Off/Heat, writes a few heating setpoints,
    and exercises Boost / CancelBoost. Tank percentage is not tested.

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
        current_board, variant, WATER_HEATER_SKETCH, current_board_port
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
                current_board, variant, WATER_HEATER_SKETCH, current_board_port, monitor
            )
            return ok

        if not matter_otbr_util.commission_with_defaults(
            node_id=NODE_ID, before_retry=_before_commission_retry
        ):
            print("Commissioning via Matter Hub failed")
            return did_run, False

        ok, _ = matter_otbr_util.matter_read_thermostat_system_mode(node_id=NODE_ID)
        if not ok:
            print("system-mode attribute read failed (needed to mark DUT online)")
            return did_run, False

        ok, cursor = _wait_for_serial_after(
            monitor, "Matter device is now online", after_index=0, timeout=60
        )
        if not ok:
            print("DUT did not come online on Matter after attribute read")
            return did_run, False

        # Example sets 55.0 C after going online
        ok, cursor = _wait_for_serial_after(
            monitor, _setpoint_serial_line(55.0), after_index=cursor, timeout=15
        )
        if not ok:
            print("Note: did not observe initial 55.0 C setpoint Serial (continuing)")

        for mode_value, serial_line in WATER_HEATER_MODE_CHECKS:
            if not matter_otbr_util.matter_write_thermostat_system_mode(
                mode_value, node_id=NODE_ID
            ):
                print(f"system-mode write failed for {serial_line}")
                return did_run, False
            ok, cursor = _wait_for_serial_after(
                monitor, serial_line, after_index=cursor, timeout=30
            )
            if not ok:
                print(f"Did not observe Serial {serial_line!r}")
                return did_run, False

        ok, min_c = matter_otbr_util.matter_read_min_heat_setpoint_limit_c(node_id=NODE_ID)
        ok2, max_c = matter_otbr_util.matter_read_max_heat_setpoint_limit_c(node_id=NODE_ID)
        if not ok or not ok2 or min_c is None or max_c is None:
            print("Failed to read heating setpoint limits")
            return did_run, False
        if min_c >= max_c:
            print(f"Invalid heating setpoint limits: min={min_c} max={max_c}")
            return did_run, False

        min_raw = matter_otbr_util.celsius_to_matter_temp_raw(min_c)
        max_raw = matter_otbr_util.celsius_to_matter_temp_raw(max_c)
        candidates = list(range(min_raw, max_raw + 1, 50))
        if len(candidates) < SETPOINT_SAMPLES:
            print(f"Not enough setpoint candidates in [{min_c}, {max_c}]")
            return did_run, False
        setpoints_c = [
            matter_otbr_util.matter_temp_raw_to_celsius(raw)
            for raw in random.sample(candidates, SETPOINT_SAMPLES)
        ]
        print(f"Testing heating setpoints (C): {setpoints_c}")

        for celsius in setpoints_c:
            if not matter_otbr_util.matter_write_occupied_heating_setpoint_c(
                celsius, node_id=NODE_ID
            ):
                print(f"occupied-heating-setpoint write for {celsius:.1f} C failed")
                return did_run, False

            expected = _setpoint_serial_line(celsius)
            ok, cursor = _wait_for_serial_after(
                monitor, expected, after_index=cursor, timeout=30
            )
            if not ok:
                print(f"Did not observe Serial echo for setpoint {celsius:.1f} C")
                return did_run, False

            ok, matter_c = matter_otbr_util.matter_read_occupied_heating_setpoint_c(
                node_id=NODE_ID
            )
            if not ok or matter_c is None:
                print(f"Failed to read OccupiedHeatingSetpoint after writing {celsius:.1f} C")
                return did_run, False
            if abs(matter_c - celsius) > 0.05:
                print(
                    f"Matter setpoint {matter_c:.1f} C does not match written {celsius:.1f} C"
                )
                return did_run, False

        if not matter_otbr_util.matter_water_heater_boost(duration_s=60, node_id=NODE_ID):
            print("water-heater Boost command failed")
            return did_run, False
        ok, cursor = _wait_for_serial_after(
            monitor, "Water heater boost state: ACTIVE", after_index=cursor, timeout=30
        )
        if not ok:
            print("Did not observe boost ACTIVE on Serial")
            return did_run, False
        ok, boost = matter_otbr_util.matter_read_water_heater_boost_state(node_id=NODE_ID)
        if not ok or boost != matter_otbr_util.WATER_HEATER_BOOST_ACTIVE:
            print(f"Expected BoostState ACTIVE (1), got {boost}")
            return did_run, False

        if not matter_otbr_util.matter_water_heater_cancel_boost(node_id=NODE_ID):
            print("water-heater CancelBoost command failed")
            return did_run, False
        ok, cursor = _wait_for_serial_after(
            monitor, "Water heater boost state: INACTIVE", after_index=cursor, timeout=30
        )
        if not ok:
            print("Did not observe boost INACTIVE on Serial")
            return did_run, False
        ok, boost = matter_otbr_util.matter_read_water_heater_boost_state(node_id=NODE_ID)
        if not ok or boost != matter_otbr_util.WATER_HEATER_BOOST_INACTIVE:
            print(f"Expected BoostState INACTIVE (0), got {boost}")
            return did_run, False

        print("Water heater modes, setpoints, and boost OK")
        return did_run, True
    finally:
        if monitor is not None:
            monitor.close()
