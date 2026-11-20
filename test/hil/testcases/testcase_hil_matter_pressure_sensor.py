import os
import re
import time

import util.hil_util as hil_util
import util.matter_otbr_util as matter_otbr_util

PRESSURE_SENSOR_SKETCH = os.path.normpath(os.path.join(
    os.path.dirname(__file__),
    "..", "..", "..",
    "libraries", "Matter", "examples", "matter_pressure_sensor",
    "matter_pressure_sensor.ino",
))

NODE_ID = matter_otbr_util.DEFAULT_NODE_ID

# Example: starts at 970.0; += 5.0f; if > 1050.0f wrap to 970.0f
PRESSURE_STEP_HPA = 5.0
PRESSURE_SERIAL_RE = re.compile(r"Current pressure: (\d+\.\d) hPa\n")


def _wait_for_next_pressure_serial(monitor, after_index=0, timeout=30):
    """
    Wait for the next 'Current pressure: X.Y hPa' line at/after after_index.
    Returns (hpa, match_end_index) or (None, after_index).
    """
    print("-" * 40)
    print(f"Waiting up to {timeout}s for next pressure Serial line (after idx {after_index})")
    print("-" * 40)
    deadline = time.time() + timeout
    while time.time() < deadline:
        text = monitor.text()
        for match in PRESSURE_SERIAL_RE.finditer(text):
            if match.start() >= after_index:
                hpa = float(match.group(1))
                print(f"Observed Serial pressure: {hpa:.1f} hPa")
                return hpa, match.end()
        time.sleep(0.1)
    print("Timed out waiting for pressure Serial line")
    return None, after_index


def _is_one_pressure_increment(previous, current):
    """True if current is previous + 5 hPa, or wrap from >1050 → 970.0."""
    expected = previous + PRESSURE_STEP_HPA
    if expected > 1050.0:
        return current == 970.0
    return abs(current - expected) < 0.05


def testcase_hil_matter_pressure_sensor(current_board, variant, current_board_port):
    """
    Testcase: HIL Matter pressure sensor
    Description: Flashes the Matter pressure sensor example, commissions it via
    SSH chip-tool on a Silicon Labs Matter Hub (Pi), then verifies one pressure
    increment (+5 hPa, wrapping >1050 -> 970) on Serial and via MeasuredValue.

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
        current_board, variant, PRESSURE_SENSOR_SKETCH, current_board_port
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
                current_board, variant, PRESSURE_SENSOR_SKETCH, current_board_port, monitor
            )
            return ok

        if not matter_otbr_util.commission_with_defaults(
            node_id=NODE_ID, before_retry=_before_commission_retry
        ):
            print("Commissioning via Matter Hub failed")
            return did_run, False

        # First attribute read marks the appliance online so setup() can exit into loop()
        ok, _ = matter_otbr_util.matter_read_pressure_hpa(node_id=NODE_ID)
        if not ok:
            print("pressure attribute read failed (needed to mark DUT online)")
            return did_run, False

        if not monitor.wait_for("Matter device is now online", timeout=60):
            print("DUT did not come online on Matter after attribute read")
            return did_run, False

        pressure_1, idx = _wait_for_next_pressure_serial(monitor, after_index=0, timeout=30)
        if pressure_1 is None:
            print("DUT did not print an initial pressure value")
            return did_run, False

        ok, matter_1 = matter_otbr_util.matter_read_pressure_hpa(node_id=NODE_ID)
        if not ok or matter_1 is None:
            print("Failed to read initial pressure MeasuredValue")
            return did_run, False
        if not matter_otbr_util.matter_matches_monitor_serial_or_steps_ahead(
            monitor, PRESSURE_SERIAL_RE, matter_1, PRESSURE_STEP_HPA,
            fallback_serial=pressure_1, wrap_above=1050.0, wrap_to=970.0, tol=0.5,
        ):
            print(
                f"Matter pressure {matter_1:.1f} hPa is not Serial {pressure_1:.1f} hPa "
                f"or up to 2 steps ahead"
            )
            return did_run, False

        # Example publishes every 10s; wait for the next stepped value
        pressure_2, _ = _wait_for_next_pressure_serial(monitor, after_index=idx, timeout=20)
        if pressure_2 is None:
            print("DUT did not print a second pressure value (expected +5 hPa step)")
            return did_run, False

        if not _is_one_pressure_increment(pressure_1, pressure_2):
            print(
                f"Pressure did not increment by {PRESSURE_STEP_HPA}: "
                f"{pressure_1:.1f} hPa -> {pressure_2:.1f} hPa"
            )
            return did_run, False

        ok, matter_2 = matter_otbr_util.matter_read_pressure_hpa(node_id=NODE_ID)
        if not ok or matter_2 is None:
            print("Failed to read pressure MeasuredValue after increment")
            return did_run, False
        if not matter_otbr_util.matter_matches_monitor_serial_or_steps_ahead(
            monitor, PRESSURE_SERIAL_RE, matter_2, PRESSURE_STEP_HPA,
            fallback_serial=pressure_2, wrap_above=1050.0, wrap_to=970.0, tol=0.5,
        ):
            print(
                f"Matter pressure {matter_2:.1f} hPa is not Serial {pressure_2:.1f} hPa "
                f"or up to 2 steps ahead after increment"
            )
            return did_run, False

        print(f"Pressure increment OK: {pressure_1:.1f} hPa -> {pressure_2:.1f} hPa")
        return did_run, True
    finally:
        if monitor is not None:
            monitor.close()
