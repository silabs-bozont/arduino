import os
import re
import time

import util.hil_util as hil_util
import util.matter_otbr_util as matter_otbr_util

TIME_SYNC_SKETCH = os.path.normpath(os.path.join(
    os.path.dirname(__file__),
    "..", "..", "..",
    "libraries", "Matter", "examples", "matter_time_sync",
    "matter_time_sync.ino",
))

NODE_ID = matter_otbr_util.DEFAULT_NODE_ID

# Test timezone: UTC+1, no DST contribution
TZ_OFFSET_S = 3600
# Allow command / Serial / clock skew across host ↔ Pi ↔ DUT
UTC_TOLERANCE_S = 60

# setup() prints this once; loop() prints Local or UTC every second.
# chip-tool pairing often SetUTCTime during commission, so setup may finish
# before our explicit SetUTCTime — do not require the setup() sync line after it.
MATTER_TIME_UPDATED_RE = re.compile(r"Matter time updated\n")
MATTER_TZ_UPDATED_RE = re.compile(r"Matter timezone updated\n")
LOOP_UNIX_RE = re.compile(r"(Local|UTC) Unix time: (\d+) \|")


def _wait_for_regex(monitor, pattern, after_index=0, timeout=60, label="Serial match"):
    """
    Wait for the next regex match at/after after_index.
    Returns (match, match_end_index) or (None, after_index).
    """
    print("-" * 40)
    print(f"Waiting up to {timeout}s for {label} (after idx {after_index})")
    print("-" * 40)
    deadline = time.time() + timeout
    while time.time() < deadline:
        text = monitor.text()
        for match in pattern.finditer(text):
            if match.start() >= after_index:
                return match, match.end()
        time.sleep(0.1)
    print(f"Timed out waiting for {label}")
    return None, after_index


def _time_close(actual, expected, tolerance=UTC_TOLERANCE_S):
    return abs(int(actual) - int(expected)) <= int(tolerance)


def testcase_hil_matter_time_sync(current_board, variant, current_board_port):
    """
    Testcase: HIL Matter time synchronization
    Description: Flashes the Matter time sync example, commissions it via SSH
    chip-tool on a Silicon Labs Matter Hub (Pi), marks the temp sensor online,
    then SetUTCTime / SetTimeZone / SetDSTOffset and verifies Serial timestamps
    against the Pi clock.

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
        current_board, variant, TIME_SYNC_SKETCH, current_board_port
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
                current_board, variant, TIME_SYNC_SKETCH, current_board_port, monitor
            )
            return ok

        if not matter_otbr_util.commission_with_defaults(
            node_id=NODE_ID, before_retry=_before_commission_retry
        ):
            print("Commissioning via Matter Hub failed")
            return did_run, False

        # Temp sensor attribute read marks the appliance online so setup() continues
        ok, _ = matter_otbr_util.matter_read_temperature_celsius(node_id=NODE_ID)
        if not ok:
            print("temperature attribute read failed (needed to mark DUT online)")
            return did_run, False

        if not monitor.wait_for("Matter device is now online", timeout=60):
            print("DUT did not come online on Matter after attribute read")
            return did_run, False

        # Commissioning may already have injected UTC (and TZ). Either we are still
        # waiting in setup(), or loop() is already printing timestamps.
        text = monitor.text()
        already_synced = (
            "Time synchronized - Unix UTC:" in text
            or "Local Unix time:" in text
            or "UTC Unix time:" in text
        )
        if not already_synced:
            if not monitor.wait_for(
                "Waiting for Matter controller time synchronization...", timeout=30
            ):
                print("DUT did not enter time-sync wait and has no time yet")
                return did_run, False

        # Explicit controller SetUTCTime — prove chip-tool sync path works even if
        # commissioning already set the clock.
        after_before_utc = len(monitor.text())
        ok, set_unix = matter_otbr_util.matter_set_utc_time(node_id=NODE_ID)
        if not ok or set_unix is None:
            print("SetUTCTime via Matter Hub failed")
            return did_run, False

        match, idx = _wait_for_regex(
            monitor,
            MATTER_TIME_UPDATED_RE,
            after_index=after_before_utc,
            timeout=60,
            label="'Matter time updated' after SetUTCTime",
        )
        if match is None:
            print("DUT did not report Matter time updated after SetUTCTime")
            return did_run, False

        match, idx = _wait_for_regex(
            monitor,
            LOOP_UNIX_RE,
            after_index=idx,
            timeout=15,
            label="Unix time Serial line after SetUTCTime",
        )
        if match is None:
            print("DUT did not print a Unix time line after SetUTCTime")
            return did_run, False

        kind = match.group(1)
        dut_unix = int(match.group(2))
        # Local = UTC + TZ. Commissioning may have left TZ at 0 or another offset;
        # accept near SetUTCTime or near SetUTCTime+our test TZ.
        utc_ok = _time_close(dut_unix, set_unix)
        local_ok = _time_close(dut_unix, set_unix + TZ_OFFSET_S)
        print(
            f"After SetUTCTime: Serial {kind} Unix={dut_unix}, "
            f"set_unix={set_unix}, match_utc={utc_ok}, match_tz+{TZ_OFFSET_S}={local_ok}"
        )
        if not (utc_ok or local_ok):
            print(
                f"DUT time {dut_unix} not within {UTC_TOLERANCE_S}s of "
                f"{set_unix} or {set_unix + TZ_OFFSET_S}"
            )
            return did_run, False

        # TimeZone feature is enabled; database is None → also supply DST (0)
        after_before_tz = len(monitor.text())
        if not matter_otbr_util.matter_set_timezone(
            TZ_OFFSET_S, node_id=NODE_ID, name="Test/UTC+1"
        ):
            print("SetTimeZone via Matter Hub failed")
            return did_run, False

        if not matter_otbr_util.matter_set_dst_offset(0, node_id=NODE_ID):
            print("SetDSTOffset via Matter Hub failed")
            return did_run, False

        match, idx = _wait_for_regex(
            monitor,
            MATTER_TZ_UPDATED_RE,
            after_index=after_before_tz,
            timeout=60,
            label="'Matter timezone updated' after SetTimeZone",
        )
        if match is None:
            print("DUT did not report Matter timezone updated")
            return did_run, False

        match, _ = _wait_for_regex(
            monitor,
            re.compile(r"Local Unix time: (\d+) \|"),
            after_index=idx,
            timeout=30,
            label="Local Unix time Serial line after timezone",
        )
        if match is None:
            print("DUT did not print Local Unix time after timezone set")
            return did_run, False

        local_unix = int(match.group(1))
        pi_now = matter_otbr_util.get_pi_unix_time()
        if pi_now is None:
            print("Failed to read Matter Hub time for local-offset check")
            return did_run, False

        expected_local = pi_now + TZ_OFFSET_S
        local_delta = abs(local_unix - expected_local)
        print(
            f"DUT Local Unix={local_unix}, expected~{expected_local} "
            f"(Pi UTC {pi_now} + {TZ_OFFSET_S}s), |delta|={local_delta}s"
        )
        if local_delta > UTC_TOLERANCE_S:
            print(
                f"DUT local time differs from Pi+TZ by {local_delta}s "
                f"(tolerance {UTC_TOLERANCE_S}s)"
            )
            return did_run, False

        print(
            f"Time sync OK: SetUTCTime + TZ +{TZ_OFFSET_S}s "
            f"(local delta {local_delta}s)"
        )
        return did_run, True
    finally:
        if monitor is not None:
            monitor.close()
