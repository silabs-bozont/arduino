import os
import re
import time

import util.hil_util as hil_util
import util.matter_otbr_util as matter_otbr_util

POWER_SOURCE_SKETCH = os.path.normpath(os.path.join(
    os.path.dirname(__file__),
    "..", "..", "..",
    "libraries", "Matter", "examples", "matter_power_source",
    "matter_power_source.ino",
))

NODE_ID = matter_otbr_util.DEFAULT_NODE_ID

# Example: current_percent_remaining -= 5; wrap 0 -> 100
PERCENT_STEP = 5
# Serial: Battery percent remaining: 100%
#         Battery voltage: 4200 mV
BATTERY_SERIAL_RE = re.compile(
    r"Battery percent remaining: (\d+)%\n"
    r"Battery voltage: (\d+) mV\n"
)


def _expected_voltage_mv(percent):
    """Match matter_power_source.ino: 3000 + percent * 12."""
    return 3000 + int(percent) * 12


def _wait_for_next_battery_serial(monitor, after_index=0, timeout=30):
    """
    Wait for the next battery percent/voltage Serial pair at/after after_index.
    Returns ((percent, voltage_mv), match_end_index) or (None, after_index).
    """
    print("-" * 40)
    print(
        f"Waiting up to {timeout}s for next battery Serial lines "
        f"(after idx {after_index})"
    )
    print("-" * 40)
    deadline = time.time() + timeout
    while time.time() < deadline:
        text = monitor.text()
        for match in BATTERY_SERIAL_RE.finditer(text):
            if match.start() >= after_index:
                percent = int(match.group(1))
                voltage_mv = int(match.group(2))
                print(
                    f"Observed Serial battery: {percent}%, {voltage_mv} mV"
                )
                return (percent, voltage_mv), match.end()
        time.sleep(0.1)
    print("Timed out waiting for battery Serial lines")
    return None, after_index


def _is_one_percent_decrement(previous, current):
    """True if current is previous - 5, or wrap from 0 → 100."""
    if previous == 0:
        return current == 100
    return current == previous - PERCENT_STEP


def testcase_hil_matter_power_source(current_board, variant, current_board_port):
    """
    Testcase: HIL Matter power source
    Description: Flashes the Matter power source example, commissions it via SSH
    chip-tool on a Silicon Labs Matter Hub (Pi), then verifies one battery
    update (~10s, -5% percent / matching voltage) on Serial and via PowerSource
    attributes.

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
        current_board, variant, POWER_SOURCE_SKETCH, current_board_port
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
                current_board, variant, POWER_SOURCE_SKETCH, current_board_port, monitor
            )
            return ok

        if not matter_otbr_util.commission_with_defaults(
            node_id=NODE_ID, before_retry=_before_commission_retry
        ):
            print("Commissioning via Matter Hub failed")
            return did_run, False

        # First attribute read marks the appliance online so setup() can exit into loop()
        ok, _ = matter_otbr_util.matter_read_bat_percent_remaining(node_id=NODE_ID)
        if not ok:
            print("bat-percent-remaining read failed (needed to mark DUT online)")
            return did_run, False

        if not monitor.wait_for("Matter device is now online", timeout=60):
            print("DUT did not come online on Matter after attribute read")
            return did_run, False

        bat_1, idx = _wait_for_next_battery_serial(monitor, after_index=0, timeout=30)
        if bat_1 is None:
            print("DUT did not print an initial battery update")
            return did_run, False

        percent_1, voltage_1 = bat_1
        if voltage_1 != _expected_voltage_mv(percent_1):
            print(
                f"Serial voltage {voltage_1} mV does not match expected "
                f"{_expected_voltage_mv(percent_1)} mV for {percent_1}%"
            )
            return did_run, False

        ok, matter_pct_1 = matter_otbr_util.matter_read_bat_percent_remaining(
            node_id=NODE_ID
        )
        if not ok or matter_pct_1 is None:
            print("Failed to read initial BatPercentRemaining")
            return did_run, False
        if matter_pct_1 != percent_1:
            print(
                f"Matter percent {matter_pct_1}% does not match Serial {percent_1}%"
            )
            return did_run, False

        ok, matter_mv_1 = matter_otbr_util.matter_read_bat_voltage_mv(node_id=NODE_ID)
        if not ok or matter_mv_1 is None:
            print("Failed to read initial BatVoltage")
            return did_run, False
        if matter_mv_1 != voltage_1:
            print(
                f"Matter voltage {matter_mv_1} mV does not match Serial {voltage_1} mV"
            )
            return did_run, False

        # Example publishes every 10s; wait for the next stepped value
        bat_2, _ = _wait_for_next_battery_serial(monitor, after_index=idx, timeout=20)
        if bat_2 is None:
            print("DUT did not print a second battery update (expected -5% step)")
            return did_run, False

        percent_2, voltage_2 = bat_2
        if not _is_one_percent_decrement(percent_1, percent_2):
            print(
                f"Battery percent did not decrement by {PERCENT_STEP}: "
                f"{percent_1}% -> {percent_2}%"
            )
            return did_run, False
        if voltage_2 != _expected_voltage_mv(percent_2):
            print(
                f"Serial voltage {voltage_2} mV does not match expected "
                f"{_expected_voltage_mv(percent_2)} mV for {percent_2}%"
            )
            return did_run, False

        ok, matter_pct_2 = matter_otbr_util.matter_read_bat_percent_remaining(
            node_id=NODE_ID
        )
        if not ok or matter_pct_2 is None:
            print("Failed to read BatPercentRemaining after decrement")
            return did_run, False
        if matter_pct_2 != percent_2:
            print(
                f"Matter percent {matter_pct_2}% does not match Serial {percent_2}% "
                f"after decrement"
            )
            return did_run, False

        ok, matter_mv_2 = matter_otbr_util.matter_read_bat_voltage_mv(node_id=NODE_ID)
        if not ok or matter_mv_2 is None:
            print("Failed to read BatVoltage after decrement")
            return did_run, False
        if matter_mv_2 != voltage_2:
            print(
                f"Matter voltage {matter_mv_2} mV does not match Serial {voltage_2} mV "
                f"after decrement"
            )
            return did_run, False

        print(
            f"Power source update OK: {percent_1}%/{voltage_1} mV -> "
            f"{percent_2}%/{voltage_2} mV"
        )
        return did_run, True
    finally:
        if monitor is not None:
            monitor.close()
