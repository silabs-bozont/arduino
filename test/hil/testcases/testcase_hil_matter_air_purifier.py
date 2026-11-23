import os
import random
import re
import time

import util.hil_util as hil_util
import util.matter_otbr_util as matter_otbr_util

AIR_PURIFIER_SKETCH = os.path.normpath(os.path.join(
    os.path.dirname(__file__),
    "..", "sketches", "hil_matter_air_purifier",
    "hil_matter_air_purifier.ino",
))

NODE_ID = matter_otbr_util.DEFAULT_NODE_ID

# DeviceAirPurifier FanModeSequence is Off/High only. Sketch only prints on
# transitions, so tests always drive Off → On (never High while already On).
SPEED_SAMPLES = 5

AIR_QUALITY_CYCLE = [
    "good",
    "fair",
    "moderate",
    "poor",
    "very poor",
    "extremely poor",
]
AIR_QUALITY_SERIAL_RE = re.compile(
    r"Current air quality: (good|fair|moderate|poor|very poor|extremely poor)\n"
)


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


def _wait_for_next_air_quality_serial(monitor, after_index=0, timeout=30):
    print("-" * 40)
    print(
        f"Waiting up to {timeout}s for next air quality Serial line "
        f"(after idx {after_index})"
    )
    print("-" * 40)
    deadline = time.time() + timeout
    while time.time() < deadline:
        text = monitor.text()
        for match in AIR_QUALITY_SERIAL_RE.finditer(text):
            if match.start() >= after_index:
                label = match.group(1)
                print(f"Observed Serial air quality: {label}")
                return label, match.end()
        time.sleep(0.1)
    print("Timed out waiting for air quality Serial line")
    return None, after_index


def _latest_air_quality_serial(monitor):
    last = None
    for match in AIR_QUALITY_SERIAL_RE.finditer(monitor.text()):
        last = match.group(1)
    return last


def _next_air_quality(label):
    idx = AIR_QUALITY_CYCLE.index(label)
    return AIR_QUALITY_CYCLE[(idx + 1) % len(AIR_QUALITY_CYCLE)]


def _is_one_air_quality_step(previous, current):
    return current == _next_air_quality(previous)


def _matter_air_quality_matches_serial(monitor, captured_label, matter_value):
    serial_label = _latest_air_quality_serial(monitor)
    if serial_label is None:
        serial_label = captured_label
    elif serial_label != captured_label:
        print(
            f"Serial baseline refreshed for Matter compare: "
            f"{captured_label} -> {serial_label}"
        )

    matter_label = matter_otbr_util.AIR_QUALITY_LABELS.get(matter_value)
    if matter_label is None:
        print(f"Matter air quality raw={matter_value} is not a HIL cycle value")
        return False

    label = serial_label
    for _ in range(3):
        if label == matter_label:
            return True
        label = _next_air_quality(label)

    print(
        f"Matter air quality {matter_label} is not Serial {serial_label} "
        f"or up to 2 steps ahead"
    )
    return False


def testcase_hil_matter_air_purifier(current_board, variant, current_board_port):
    """
    Testcase: HIL Matter air purifier
    Description: Flashes hil_matter_air_purifier (AQ cycle + fan echoes),
    commissions via the Matter Hub, verifies one air-quality step, then Off/High
    fan modes and random PercentSetting values (FanModeSequence is Off/High).

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

    if not hil_util.arduino_cli_burn_bootloader(current_board, current_board_port):
        print(f"Bootloader burn failed for '{current_board}'")
        return did_run, False

    success = hil_util.arduino_cli_build_and_flash(
        current_board, variant, AIR_PURIFIER_SKETCH, current_board_port
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
                current_board, variant, AIR_PURIFIER_SKETCH, current_board_port, monitor
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

        # --- Air quality cycle step ---
        aq_1, aq_idx = _wait_for_next_air_quality_serial(
            monitor, after_index=cursor, timeout=30
        )
        if aq_1 is None:
            print("DUT did not print an initial air quality value")
            return did_run, False

        ok, matter_1 = matter_otbr_util.matter_read_air_quality(node_id=NODE_ID)
        if not ok or matter_1 is None:
            print("Failed to read initial AirQuality attribute")
            return did_run, False
        if not _matter_air_quality_matches_serial(monitor, aq_1, matter_1):
            return did_run, False

        aq_2, aq_idx = _wait_for_next_air_quality_serial(
            monitor, after_index=aq_idx, timeout=20
        )
        if aq_2 is None:
            print("DUT did not print a second air quality value (expected cycle step)")
            return did_run, False
        if not _is_one_air_quality_step(aq_1, aq_2):
            print(f"Air quality did not advance one step: {aq_1} -> {aq_2}")
            return did_run, False

        ok, matter_2 = matter_otbr_util.matter_read_air_quality(node_id=NODE_ID)
        if not ok or matter_2 is None:
            print("Failed to read AirQuality attribute after step")
            return did_run, False
        if not _matter_air_quality_matches_serial(monitor, aq_2, matter_2):
            return did_run, False

        cursor = max(cursor, aq_idx)
        print(f"Air quality step OK: {aq_1} -> {aq_2}")

        # --- Fan Off/High + percent (sequence is Off/High only) ---
        # Force Off first (Serial may already be Off — do not require an echo).
        if not matter_otbr_util.matter_write_fan_mode(
            matter_otbr_util.FAN_MODE_OFF, node_id=NODE_ID
        ):
            print("fan-mode write to Off (precondition) failed")
            return did_run, False
        ok, cursor = _wait_for_serial_after(
            monitor, "Fan OFF", after_index=cursor, timeout=5
        )
        if ok:
            print("Fan was On; observed transition to Off")
        else:
            print("No Fan OFF echo (likely already Off); continuing")

        if not matter_otbr_util.matter_write_fan_mode(
            matter_otbr_util.FAN_MODE_HIGH, node_id=NODE_ID
        ):
            print("fan-mode write to High failed")
            return did_run, False
        ok, cursor = _wait_for_serial_after(
            monitor, "Fan ON", after_index=cursor, timeout=30
        )
        if not ok:
            print("Did not observe Serial 'Fan ON'")
            return did_run, False

        if not matter_otbr_util.matter_write_fan_mode(
            matter_otbr_util.FAN_MODE_OFF, node_id=NODE_ID
        ):
            print("fan-mode write to Off failed")
            return did_run, False
        ok, cursor = _wait_for_serial_after(
            monitor, "Fan OFF", after_index=cursor, timeout=30
        )
        if not ok:
            print("Did not observe Serial 'Fan OFF'")
            return did_run, False

        if not matter_otbr_util.matter_write_fan_mode(
            matter_otbr_util.FAN_MODE_HIGH, node_id=NODE_ID
        ):
            print("fan-mode write to High before speed tests failed")
            return did_run, False
        ok, cursor = _wait_for_serial_after(
            monitor, "Fan ON", after_index=cursor, timeout=30
        )
        if not ok:
            print("Did not observe Serial 'Fan ON' before speed tests")
            return did_run, False

        percents = random.sample(range(1, 101), SPEED_SAMPLES)
        print(f"Testing air purifier fan speed percents: {percents}")
        for pct in percents:
            if not matter_otbr_util.matter_write_fan_percent(pct, node_id=NODE_ID):
                print(f"percent-setting write for {pct}% failed")
                return did_run, False
            expected = f"Fan speed: {pct}%\n"
            ok, cursor = _wait_for_serial_after(
                monitor, expected, after_index=cursor, timeout=30
            )
            if not ok:
                print(f"Did not observe Serial echo for fan speed {pct}%")
                return did_run, False

        print("Air purifier air-quality step + fan modes/speeds OK")
        return did_run, True
    finally:
        if monitor is not None:
            monitor.close()
