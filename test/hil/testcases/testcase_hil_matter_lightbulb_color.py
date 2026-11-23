import os
import random
import re
import time

import util.hil_util as hil_util
import util.matter_otbr_util as matter_otbr_util

COLOR_SKETCH = os.path.normpath(os.path.join(
    os.path.dirname(__file__),
    "..", "..", "..",
    "libraries", "Matter", "examples", "nano_matter_lightbulb_color",
    "nano_matter_lightbulb_color.ino",
))

NODE_ID = matter_otbr_util.DEFAULT_NODE_ID
# Boards with onboard RGB LEDs used by the nano color example
COLOR_BOARDS = ("nano_matter", "xg24devkit")
# Matches matter_color_bulb.boost_saturation(51) in the example
SATURATION_BOOST = 51
BRIGHTNESS_SAMPLES = 5
COLOR_SAMPLES = 5
RGB_SERIAL_RE = re.compile(
    r"Setting bulb color to > r: (\d+)  g: (\d+)  b: (\d+)\n"
)


def _wait_for_rgb_serial(monitor, expected_rgb, after_index=0, timeout=30, tol=1):
    """
    Wait for a Serial RGB line at/after after_index that matches expected_rgb
    within tol per channel. Returns match_end_index or None.
    """
    er, eg, eb = expected_rgb
    print("-" * 40)
    print(
        f"Waiting up to {timeout}s for Serial RGB ~({er}, {eg}, {eb}) "
        f"(tol={tol}, after idx {after_index})"
    )
    print("-" * 40)
    deadline = time.time() + timeout
    while time.time() < deadline:
        text = monitor.text()
        for match in RGB_SERIAL_RE.finditer(text):
            if match.start() < after_index:
                continue
            r, g, b = int(match.group(1)), int(match.group(2)), int(match.group(3))
            if abs(r - er) <= tol and abs(g - eg) <= tol and abs(b - eb) <= tol:
                print(f"Observed Serial RGB: ({r}, {g}, {b})")
                return match.end()
        time.sleep(0.1)
    print(f"Timed out waiting for Serial RGB ~({er}, {eg}, {eb})")
    return None


def testcase_hil_matter_lightbulb_color(current_board, variant, current_board_port):
    """
    Testcase: HIL Matter color lightbulb
    Description: Flashes the Nano Matter color lightbulb example (onboard RGB),
    commissions via the Matter Hub, toggles on/off, sets random brightness %,
    then sets random hue/saturation and checks Serial RGB against the library
    HSV→RGB conversion (including the example saturation boost).

    Only runs on nano_matter and xg24devkit (onboard color LEDs).
    Opt-in only: requires test_hil.py --matter-otbr <pi-ip>.
    """
    did_run = False
    if current_board not in COLOR_BOARDS:
        return did_run, True
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
        current_board, variant, COLOR_SKETCH, current_board_port
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
                current_board, variant, COLOR_SKETCH, current_board_port, monitor
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

        if not matter_otbr_util.matter_onoff(True, node_id=NODE_ID):
            print("matter on command failed")
            return did_run, False

        if not monitor.wait_for("\nBulb ON\n", timeout=30):
            print("Did not observe 'Bulb ON' on serial")
            return did_run, False

        # Device defaults: hue=0, sat=0, level=254; example boosts sat by 51
        hue = 0
        sat = 0
        serial_idx = len(monitor.text())

        # Exclude 100 so the full-bright step below always produces a new Serial line
        percents = random.sample(range(1, 100), BRIGHTNESS_SAMPLES)
        print(f"Testing brightness percents: {percents}")
        for pct in percents:
            if not matter_otbr_util.matter_set_brightness_percent(pct, node_id=NODE_ID):
                print(f"move-to-level for {pct}% failed")
                return did_run, False

            level = matter_otbr_util.percent_to_matter_level(pct)
            expected = matter_otbr_util.matter_color_hsv_to_rgb(
                hue, sat, level, saturation_boost=SATURATION_BOOST
            )
            end = _wait_for_rgb_serial(monitor, expected, after_index=serial_idx)
            if end is None:
                print(f"Did not observe matching Serial RGB for brightness {pct}%")
                return did_run, False
            serial_idx = end

        # Stable full brightness before color sweeps
        if not matter_otbr_util.matter_set_brightness_percent(100, node_id=NODE_ID):
            print("move-to-level for 100% failed")
            return did_run, False
        level = matter_otbr_util.percent_to_matter_level(100)
        expected = matter_otbr_util.matter_color_hsv_to_rgb(
            hue, sat, level, saturation_boost=SATURATION_BOOST
        )
        end = _wait_for_rgb_serial(monitor, expected, after_index=serial_idx)
        if end is None:
            print("Did not observe matching Serial RGB for brightness 100%")
            return did_run, False
        serial_idx = end

        # Avoid hue=254 (HSV edge) and keep colors distinct with sat >= 64
        colors = []
        while len(colors) < COLOR_SAMPLES:
            candidate = (random.randint(0, 253), random.randint(64, 254))
            if candidate not in colors:
                colors.append(candidate)
        print(f"Testing hue/sat pairs: {colors}")

        for hue, sat in colors:
            if not matter_otbr_util.matter_move_to_hue_and_saturation(
                hue, sat, node_id=NODE_ID
            ):
                print(f"move-to-hue-and-saturation hue={hue} sat={sat} failed")
                return did_run, False

            ok, matter_hue = matter_otbr_util.matter_read_current_hue(node_id=NODE_ID)
            if not ok or matter_hue != hue:
                print(f"CurrentHue {matter_hue} does not match set hue {hue}")
                return did_run, False

            ok, matter_sat = matter_otbr_util.matter_read_current_saturation(
                node_id=NODE_ID
            )
            if not ok or matter_sat != sat:
                print(
                    f"CurrentSaturation {matter_sat} does not match set sat {sat}"
                )
                return did_run, False

            expected = matter_otbr_util.matter_color_hsv_to_rgb(
                hue, sat, level, saturation_boost=SATURATION_BOOST
            )
            end = _wait_for_rgb_serial(monitor, expected, after_index=serial_idx)
            if end is None:
                print(
                    f"Did not observe matching Serial RGB for hue={hue} sat={sat} "
                    f"(expected {expected})"
                )
                return did_run, False
            serial_idx = end

        if not matter_otbr_util.matter_onoff(False, node_id=NODE_ID):
            print("matter off command failed")
            return did_run, False

        if not monitor.wait_for("\nBulb OFF\n", timeout=30):
            print("Did not observe 'Bulb OFF' on serial")
            return did_run, False

        return did_run, True
    finally:
        if monitor is not None:
            monitor.close()
