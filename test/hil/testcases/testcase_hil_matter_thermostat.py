import os
import random
import time

import util.hil_util as hil_util
import util.matter_otbr_util as matter_otbr_util

THERMOSTAT_SKETCH = os.path.normpath(os.path.join(
    os.path.dirname(__file__),
    "..", "..", "..",
    "libraries", "Matter", "examples", "matter_thermostat", "matter_thermostat.ino",
))

NODE_ID = matter_otbr_util.DEFAULT_NODE_ID

# MatterThermostat only exposes Off / Heat in the example.
THERMOSTAT_MODE_CHECKS = [
    (matter_otbr_util.THERMOSTAT_MODE_HEAT, "Thermostat mode: HEAT"),
    (matter_otbr_util.THERMOSTAT_MODE_OFF, "Thermostat mode: OFF"),
    (matter_otbr_util.THERMOSTAT_MODE_HEAT, "Thermostat mode: HEAT"),
]

SETPOINT_SAMPLES = 4


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
    # Example: Serial.printf("Thermostat setpoint: %.01f C\\n", ...)
    return f"Thermostat setpoint: {celsius:.1f} C\n"


def testcase_hil_matter_thermostat(current_board, variant, current_board_port):
    """
    Testcase: HIL Matter thermostat
    Description: Flashes the Matter thermostat example, commissions via the Matter
    Hub, toggles SystemMode Off/Heat, writes random OccupiedHeatingSetpoint values
    within Min/MaxHeatSetpointLimit, then writes out-of-range setpoints and checks
    DeviceThermostat clamps them. Serial echoes are verified for mode / setpoint.

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
        current_board, variant, THERMOSTAT_SKETCH, current_board_port
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
                current_board, variant, THERMOSTAT_SKETCH, current_board_port, monitor
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

        # Example sets 23.0 C after going online; accept it if printed
        ok, cursor = _wait_for_serial_after(
            monitor, _setpoint_serial_line(23.0), after_index=cursor, timeout=15
        )
        if not ok:
            print("Note: did not observe initial 23.0 C setpoint Serial (continuing)")

        # System modes Off / Heat
        for mode_value, serial_line in THERMOSTAT_MODE_CHECKS:
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

        # Half-degree steps within [min, max], matching %.01f Serial formatting
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

        last_setpoint_c = None
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
            last_setpoint_c = matter_c

        # Out of range: below min → clamp to min
        below = min_c - 5.0
        print(f"Writing below-min setpoint {below:.1f} C (expect clamp to {min_c:.1f} C)")
        if not matter_otbr_util.matter_write_occupied_heating_setpoint_c(
            below, node_id=NODE_ID
        ):
            print("occupied-heating-setpoint write below min failed")
            return did_run, False
        ok, matter_c = matter_otbr_util.matter_read_occupied_heating_setpoint_c(
            node_id=NODE_ID
        )
        if not ok or matter_c is None:
            print("Failed to read OccupiedHeatingSetpoint after below-min write")
            return did_run, False
        if abs(matter_c - min_c) > 0.05:
            print(
                f"Below-min write not clamped: got {matter_c:.1f} C, expected {min_c:.1f} C"
            )
            return did_run, False
        if last_setpoint_c is None or abs(last_setpoint_c - min_c) > 0.05:
            ok, cursor = _wait_for_serial_after(
                monitor, _setpoint_serial_line(min_c), after_index=cursor, timeout=30
            )
            if not ok:
                print(f"Did not observe Serial clamp echo for {min_c:.1f} C")
                return did_run, False
        last_setpoint_c = min_c

        # Out of range: above max → clamp to max
        above = max_c + 5.0
        print(f"Writing above-max setpoint {above:.1f} C (expect clamp to {max_c:.1f} C)")
        if not matter_otbr_util.matter_write_occupied_heating_setpoint_c(
            above, node_id=NODE_ID
        ):
            print("occupied-heating-setpoint write above max failed")
            return did_run, False
        ok, matter_c = matter_otbr_util.matter_read_occupied_heating_setpoint_c(
            node_id=NODE_ID
        )
        if not ok or matter_c is None:
            print("Failed to read OccupiedHeatingSetpoint after above-max write")
            return did_run, False
        if abs(matter_c - max_c) > 0.05:
            print(
                f"Above-max write not clamped: got {matter_c:.1f} C, expected {max_c:.1f} C"
            )
            return did_run, False
        if abs(last_setpoint_c - max_c) > 0.05:
            ok, cursor = _wait_for_serial_after(
                monitor, _setpoint_serial_line(max_c), after_index=cursor, timeout=30
            )
            if not ok:
                print(f"Did not observe Serial clamp echo for {max_c:.1f} C")
                return did_run, False

        print("Thermostat modes, setpoints, and limit clamping OK")
        return did_run, True
    finally:
        if monitor is not None:
            monitor.close()
