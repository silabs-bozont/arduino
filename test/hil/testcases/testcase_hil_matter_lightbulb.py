import os
import time
import util.hil_util as hil_util
import util.matter_hil_util as matter_hil_util


def testcase_hil_matter_lightbulb(current_board, variant, current_board_port):
    """
    Testcase: HIL Matter Lightbulb (e2e)
    Description: Flashes the built-in matter_lightbulb example, commissions it via
    matter.js + OTBR/RCP Thread network, then toggles On/Off and asserts Serial.
    Requires Matter HIL infra (OTBR + RCP + matter.js controller).
    """
    did_run = False
    if variant != "matter":
        return did_run, True
    else:
        did_run = True

    # Allow skipping cleanly when Matter HIL infra is not provisioned
    if os.environ.get("MATTER_HIL_SKIP", "").lower() in ("1", "true", "yes"):
        print("MATTER_HIL_SKIP set — skipping matter_lightbulb e2e test")
        return False, True

    ready, reason = matter_hil_util.preflight_matter_hil()
    if not ready:
        print(f"Matter HIL infra not ready: {reason}")
        print("Prefer the self-contained runner:")
        print("  python3 test_matter_lightbulb_hil.py <board> <dut_port> <rcp_port>")
        return did_run, False

    print(f"Matter HIL preflight OK: {reason}")

    # Clean fabric so we do not reuse a stale peer from a previous DUT identity
    ok, result = matter_hil_util.run_matter_ctl("reset-fabric", timeout_s=30)
    if not ok:
        print(f"reset-fabric failed: {result}")
        return did_run, False

    # Re-inject Thread credentials after fabric reset
    name, dataset = matter_hil_util.get_thread_credentials()
    if not name or not dataset:
        print("Failed to read Thread credentials from OTBR after reset-fabric")
        return did_run, False
    ok, result = matter_hil_util.run_matter_ctl(
        "ensure-ready", "--network-name", name, "--dataset", dataset, timeout_s=60
    )
    if not ok:
        print(f"ensure-ready failed: {result}")
        return did_run, False

    sketch = matter_hil_util.sketch_path_matter_lightbulb()
    if not os.path.isfile(sketch):
        print(f"matter_lightbulb sketch not found: {sketch}")
        return did_run, False

    success = hil_util.arduino_cli_build_and_flash(
        current_board, variant, sketch, current_board_port
    )
    if not success:
        print(f"Build/upload failed for '{variant}' on '{current_board}'")
        return did_run, False

    # Give the sketch time to boot and print pairing info
    time.sleep(3)
    serial_text = matter_hil_util.read_serial_for(current_board_port, duration_s=4)
    print(serial_text)
    pairing = matter_hil_util.parse_pairing_from_serial(serial_text)

    # If already commissioned from a previous run (bootloader burn should have cleared),
    # wait a bit more / re-read. Prefer manual code, fall back to QR payload.
    if not pairing["manual_code"] and not pairing["qr_payload"]:
        ok_wait, serial_text = matter_hil_util.wait_for_serial_substring(
            current_board_port, "Manual pairing code:", timeout_s=30
        )
        if not ok_wait:
            print("Did not see pairing code on serial")
            return did_run, False
        pairing = matter_hil_util.parse_pairing_from_serial(serial_text)

    pairing_code = pairing["manual_code"] or pairing["qr_payload"]
    if not pairing_code:
        print("Could not parse pairing code from serial")
        return did_run, False
    print(f"Using pairing code: {pairing_code}")

    ok, result = matter_hil_util.run_matter_ctl(
        "commission", pairing_code, timeout_s=300
    )
    if not ok:
        print(f"Commissioning failed: {result}")
        return did_run, False
    print(f"Commissioned node: {result.get('nodeId')}")

    ok_online, _ = matter_hil_util.wait_for_serial_substring(
        current_board_port, "Matter device is now online", timeout_s=180
    )
    if not ok_online:
        print("Device did not report online after commissioning")
        return did_run, False

    # On
    ok, result = matter_hil_util.run_matter_ctl("onoff", "on", timeout_s=90)
    if not ok:
        print(f"onoff on failed: {result}")
        return did_run, False
    ok_on, _ = matter_hil_util.wait_for_serial_substring(
        current_board_port, "Bulb ON", timeout_s=30
    )
    if not ok_on:
        print("Did not see 'Bulb ON' on serial")
        return did_run, False

    # Off
    ok, result = matter_hil_util.run_matter_ctl("onoff", "off", timeout_s=90)
    if not ok:
        print(f"onoff off failed: {result}")
        return did_run, False
    ok_off, _ = matter_hil_util.wait_for_serial_substring(
        current_board_port, "Bulb OFF", timeout_s=30
    )
    if not ok_off:
        print("Did not see 'Bulb OFF' on serial")
        return did_run, False

    # Toggle (on again)
    ok, result = matter_hil_util.run_matter_ctl("onoff", "toggle", timeout_s=90)
    if not ok:
        print(f"onoff toggle failed: {result}")
        return did_run, False
    ok_tog, _ = matter_hil_util.wait_for_serial_substring(
        current_board_port, "Bulb ON", timeout_s=30
    )
    if not ok_tog:
        print("Did not see 'Bulb ON' after toggle on serial")
        return did_run, False

    return did_run, True
