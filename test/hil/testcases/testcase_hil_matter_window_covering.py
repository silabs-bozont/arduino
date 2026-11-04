import os
import random
import time

import util.hil_util as hil_util
import util.matter_otbr_util as matter_otbr_util

WINDOW_COVERING_SKETCH = os.path.normpath(os.path.join(
    os.path.dirname(__file__),
    "..", "..", "..",
    "libraries", "Matter", "examples", "matter_window_covering",
    "matter_window_covering.ino",
))

NODE_ID = matter_otbr_util.DEFAULT_NODE_ID

# Example steps 1% / 100ms → full travel ~10s; leave headroom for Serial / SSH lag
MOVE_TIMEOUT_S = 45


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


def testcase_hil_matter_window_covering(current_board, variant, current_board_port):
    """
    Testcase: HIL Matter window covering
    Description: Flashes the window covering example, commissions via the Matter Hub,
    then verifies fully open/close, go-to percentage moves, and stop-motion.

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
        current_board, variant, WINDOW_COVERING_SKETCH, current_board_port
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

        ok, _ = matter_otbr_util.matter_read_window_covering_position(node_id=NODE_ID)
        if not ok:
            print("window covering attribute read failed (needed to mark DUT online)")
            return did_run, False

        ok, cursor = _wait_for_serial_after(
            monitor, "Matter device is now online", after_index=0, timeout=60
        )
        if not ok:
            print("DUT did not come online on Matter after attribute read")
            return did_run, False

        # Example sets initial position to fully open (100%) right after online
        time.sleep(1)

        # --- Fully close (app 0%) ---
        if not matter_otbr_util.matter_window_covering_down_or_close(node_id=NODE_ID):
            print("down-or-close command failed")
            return did_run, False
        ok, cursor = _wait_for_serial_after(
            monitor, "closing...", after_index=cursor, timeout=30
        )
        if not ok:
            print("Did not observe closing motion on Serial")
            return did_run, False
        ok, cursor = _wait_for_serial_after(
            monitor, "Moved to 0%\n", after_index=cursor, timeout=MOVE_TIMEOUT_S
        )
        if not ok:
            print("Did not observe fully closed (Moved to 0%)")
            return did_run, False

        # --- Fully open (app 100%) ---
        if not matter_otbr_util.matter_window_covering_up_or_open(node_id=NODE_ID):
            print("up-or-open command failed")
            return did_run, False
        ok, cursor = _wait_for_serial_after(
            monitor, "opening...", after_index=cursor, timeout=30
        )
        if not ok:
            print("Did not observe opening motion on Serial")
            return did_run, False
        ok, cursor = _wait_for_serial_after(
            monitor, "Moved to 100%\n", after_index=cursor, timeout=MOVE_TIMEOUT_S
        )
        if not ok:
            print("Did not observe fully open (Moved to 100%)")
            return did_run, False

        # --- Go to set percentages (Arduino app %: 100=open, 0=closed) ---
        targets = random.sample([20, 35, 50, 65, 80], 3)
        print(f"Testing go-to lift percentages: {targets}")
        for pct in targets:
            if not matter_otbr_util.matter_window_covering_go_to_app_percent(
                pct, node_id=NODE_ID
            ):
                print(f"go-to-lift-percentage for {pct}% failed")
                return did_run, False
            ok, cursor = _wait_for_serial_after(
                monitor, f"Moved to {pct}%\n", after_index=cursor, timeout=MOVE_TIMEOUT_S
            )
            if not ok:
                print(f"Did not observe Serial 'Moved to {pct}%'")
                return did_run, False

        # --- Stop while moving: return to open, start closing, stop mid-way ---
        if not matter_otbr_util.matter_window_covering_up_or_open(node_id=NODE_ID):
            print("up-or-open before stop test failed")
            return did_run, False
        ok, cursor = _wait_for_serial_after(
            monitor, "Moved to 100%\n", after_index=cursor, timeout=MOVE_TIMEOUT_S
        )
        if not ok:
            print("Could not reach 100% before stop test")
            return did_run, False

        if not matter_otbr_util.matter_window_covering_down_or_close(node_id=NODE_ID):
            print("down-or-close for stop test failed")
            return did_run, False
        ok, cursor = _wait_for_serial_after(
            monitor, "closing...", after_index=cursor, timeout=30
        )
        if not ok:
            print("Did not observe closing before stop")
            return did_run, False

        # Let the simulated motor move a bit (~1% / 100ms)
        time.sleep(1.5)
        if not matter_otbr_util.matter_window_covering_stop_motion(node_id=NODE_ID):
            print("stop-motion command failed")
            return did_run, False

        ok, cursor = _wait_for_serial_after(
            monitor, "Stop requested", after_index=cursor, timeout=15
        )
        if not ok:
            print("Did not observe 'Stop requested' on Serial after stop-motion")
            return did_run, False

        print("Window covering open/close, go-to percent, and stop OK")
        return did_run, True
    finally:
        if monitor is not None:
            monitor.close()
