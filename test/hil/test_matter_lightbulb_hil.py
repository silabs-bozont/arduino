#!/usr/bin/env python3
"""
Self-contained Matter lightbulb HIL runner.

Starts OTBR (RCP + Docker), runs the matter_lightbulb e2e testcase, then tears
OTBR down.

Usage:
  python3 test_matter_lightbulb_hil.py <board> <dut_port> <rcp_port>

Example:
  python3 test_matter_lightbulb_hil.py nano_matter \\
      /dev/tty.usbmodem202C8AE63 /dev/tty.usbmodem0004490513501
"""

import signal
import sys
import time

import util.hil_util as hil_util
import util.matter_hil_util as matter_hil_util
from util.hil_util import bcolors
from testcases.testcase_hil_matter_lightbulb import testcase_hil_matter_lightbulb

SUPPORTED_BOARDS = (
    "nano_matter",
    "thingplusmatter",
    "xg24explorerkit",
    "xg24devkit",
    "xiao_mg24",
)


def usage(exit_code=1):
    print("Usage: python3 test_matter_lightbulb_hil.py <board> <dut_port> <rcp_port>")
    print("")
    print("Arguments:")
    print("  board      DUT board name (e.g. nano_matter, thingplusmatter)")
    print("  dut_port   Serial port of the device under test")
    print("  rcp_port   Serial port of the OpenThread RCP board")
    print("")
    print("Supported boards:")
    for board in SUPPORTED_BOARDS:
        print(f"  {board}")
    print("")
    print("Example:")
    print("  python3 test_matter_lightbulb_hil.py nano_matter \\")
    print("      /dev/tty.usbmodemDUT /dev/tty.usbmodemRCP")
    sys.exit(exit_code)


def parse_args():
    if len(sys.argv) >= 2 and sys.argv[1] in ("-h", "--help"):
        usage(0)
    if len(sys.argv) != 4:
        usage(1)

    board = sys.argv[1]
    dut_port = sys.argv[2]
    rcp_port = sys.argv[3]

    if board not in SUPPORTED_BOARDS:
        print(f"Unsupported board '{board}'")
        usage(1)
    return board, dut_port, rcp_port


def main():
    signal.signal(signal.SIGINT, lambda *_: sys.exit(130))
    board, dut_port, rcp_port = parse_args()

    print(f"{bcolors.HEADER}Matter lightbulb HIL (self-contained){bcolors.ENDC}")
    print(f"Board:    {board}")
    print(f"DUT port: {dut_port}")
    print(f"RCP port: {rcp_port}")

    start_time = time.time()
    otbr_started = False
    success = False

    try:
        if not hil_util.check_serial_port_available(dut_port):
            print(f"{bcolors.FAIL}DUT serial port not available: {dut_port}{bcolors.ENDC}")
            return 1

        ok, info = matter_hil_util.start_otbr(rcp_port)
        if not ok:
            print(f"{bcolors.FAIL}Failed to start OTBR: {info}{bcolors.ENDC}")
            return 1
        otbr_started = True
        print(f"{bcolors.OKGREEN}{info}{bcolors.ENDC}")

        # Chip erase via bootloader burn so Matter credentials start clean
        if not hil_util.arduino_cli_burn_bootloader(board, dut_port):
            print(f"{bcolors.FAIL}Bootloader burn failed on DUT{bcolors.ENDC}")
            return 1

        did_run, success = testcase_hil_matter_lightbulb(board, "matter", dut_port)
        if not did_run:
            print(f"{bcolors.WARNING}Testcase did not run{bcolors.ENDC}")
            success = False
    finally:
        if otbr_started:
            ok, info = matter_hil_util.stop_otbr(rcp_port)
            if ok:
                print(f"{bcolors.OKGREEN}{info}{bcolors.ENDC}")
            else:
                print(f"{bcolors.WARNING}OTBR teardown: {info}{bcolors.ENDC}")

    elapsed = int(time.time() - start_time)
    print("-" * 40)
    print(f"Time: {elapsed // 60}m {elapsed % 60}s")
    if success:
        print(f"{bcolors.OKGREEN}Matter lightbulb HIL successful{bcolors.ENDC}")
        return 0

    print(f"{bcolors.FAIL}Matter lightbulb HIL failed{bcolors.ENDC}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
