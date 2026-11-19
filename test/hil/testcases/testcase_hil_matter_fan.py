import os
import random
import time

import util.hil_util as hil_util
import util.matter_otbr_util as matter_otbr_util

FAN_SKETCH = os.path.normpath(os.path.join(
    os.path.dirname(__file__),
    "..", "..", "..",
    "libraries", "Matter", "examples", "matter_fan", "matter_fan.ino",
))

NODE_ID = matter_otbr_util.DEFAULT_NODE_ID

# Modes in DeviceFan FanModeSequence (Off/Low/Med/High/Auto). Matter 2.9+
# FanControlCluster remaps On→High and Smart→Auto, so those are not distinct.
FAN_MODE_CHECKS = [
    (matter_otbr_util.FAN_MODE_LOW, "Fan mode: Low"),
    (matter_otbr_util.FAN_MODE_MED, "Fan mode: Medium"),
    (matter_otbr_util.FAN_MODE_HIGH, "Fan mode: High"),
    (matter_otbr_util.FAN_MODE_AUTO, "Fan mode: Auto"),
    (matter_otbr_util.FAN_MODE_OFF, "Fan mode: Off"),
]

SPEED_SAMPLES = 5


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


def testcase_hil_matter_fan(current_board, variant, current_board_port):
    """
    Testcase: HIL Matter fan
    Description: Flashes the Matter fan example, commissions via the Matter Hub,
    sets each fan mode the example tracks, then random PercentSetting values, and
    checks Serial echoes for mode / speed.

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
        current_board, variant, FAN_SKETCH, current_board_port
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
                current_board, variant, FAN_SKETCH, current_board_port, monitor
            )
            return ok

        if not matter_otbr_util.commission_with_defaults(
            node_id=NODE_ID, before_retry=_before_commission_retry
        ):
            print("Commissioning via Matter Hub failed")
            return did_run, False

        if not matter_otbr_util.matter_read_fan_mode(node_id=NODE_ID):
            print("fan-mode attribute read failed (needed to mark DUT online)")
            return did_run, False

        ok, cursor = _wait_for_serial_after(
            monitor, "Matter device is now online", after_index=0, timeout=60
        )
        if not ok:
            print("DUT did not come online on Matter after attribute read")
            return did_run, False

        # Fan modes
        for mode_value, serial_line in FAN_MODE_CHECKS:
            if not matter_otbr_util.matter_write_fan_mode(mode_value, node_id=NODE_ID):
                print(f"fan-mode write failed for {serial_line}")
                return did_run, False
            ok, cursor = _wait_for_serial_after(
                monitor, serial_line, after_index=cursor, timeout=30
            )
            if not ok:
                print(f"Did not observe Serial {serial_line!r}")
                return did_run, False

        # Leave Off: put fan in High so percent writes are accepted, then apply speeds
        if not matter_otbr_util.matter_write_fan_mode(
            matter_otbr_util.FAN_MODE_HIGH, node_id=NODE_ID
        ):
            print("fan-mode write to High before speed tests failed")
            return did_run, False
        ok, cursor = _wait_for_serial_after(
            monitor, "Fan mode: High", after_index=cursor, timeout=30
        )
        if not ok:
            print("Did not observe Serial 'Fan mode: High' before speed tests")
            return did_run, False

        # Distinct percents so each Serial line is unique in the monitor buffer
        percents = random.sample(range(1, 101), SPEED_SAMPLES)
        print(f"Testing fan speed percents: {percents}")
        for pct in percents:
            if not matter_otbr_util.matter_write_fan_percent(pct, node_id=NODE_ID):
                print(f"percent-setting write for {pct}% failed")
                return did_run, False
            # Trailing newline avoids 'Fan speed: 5%' matching inside 'Fan speed: 50%'
            expected = f"Fan speed: {pct}%\n"
            ok, cursor = _wait_for_serial_after(
                monitor, expected, after_index=cursor, timeout=30
            )
            if not ok:
                print(f"Did not observe Serial echo for fan speed {pct}%")
                return did_run, False

        print("Fan modes and speed percents OK")
        return did_run, True
    finally:
        if monitor is not None:
            monitor.close()
