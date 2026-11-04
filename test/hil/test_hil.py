# HIL tests for the Silabs Arduino Core

import signal
import sys
import time
import util.hil_util as hil_util
import util.matter_otbr_util as matter_otbr_util
from util.hil_util import bcolors as bcolors
from testcases.testcase_hil_basic_smoke import testcase_hil_basic_smoke
from testcases.testcase_hil_serial_echo import testcase_hil_serial_echo
from testcases.testcase_hil_eeprom import testcase_hil_eeprom
from testcases.testcase_hil_watchdog import testcase_hil_watchdog
from testcases.testcase_hil_adc import testcase_hil_adc
from testcases.testcase_hil_thingplus_battery import testcase_hil_thingplus_battery
from testcases.testcase_hil_imu_spi import testcase_hil_imu_spi
from testcases.testcase_hil_si7021_wire import testcase_hil_si7021_wire
from testcases.testcase_hil_ble_silabs_advertise import testcase_hil_ble_silabs_advertise
from testcases.testcase_hil_ble_arduino_advertise import testcase_hil_ble_arduino_advertise
from testcases.testcase_hil_matter_smoke import testcase_hil_matter_smoke
from testcases.testcase_hil_matter_lightbulb import testcase_hil_matter_lightbulb
from testcases.testcase_hil_matter_lightbulb_dimmable import testcase_hil_matter_lightbulb_dimmable
from testcases.testcase_hil_matter_temp_sensor import testcase_hil_matter_temp_sensor
from testcases.testcase_hil_matter_humidity_sensor import testcase_hil_matter_humidity_sensor
from testcases.testcase_hil_matter_window_covering import testcase_hil_matter_window_covering
from testcases.testcase_hil_zigbee_smoke import testcase_hil_zigbee_smoke

all_variants = [
    ["nano_matter", "none"],
    ["nano_matter", "ble_arduino"],
    ["nano_matter", "ble_silabs"],
    ["nano_matter", "zigbee"],
    ["nano_matter", "matter"],
    ["thingplusmatter", "none"],
    ["thingplusmatter", "ble_arduino"],
    ["thingplusmatter", "ble_silabs"],
    ["thingplusmatter", "zigbee"],
    ["thingplusmatter", "matter"],
    ["xg24explorerkit", "none"],
    ["xg24explorerkit", "ble_arduino"],
    ["xg24explorerkit", "ble_silabs"],
    ["xg24explorerkit", "zigbee"],
    ["xg24explorerkit", "matter"],
    ["xg24devkit", "none"],
    ["xg24devkit", "ble_arduino"],
    ["xg24devkit", "ble_silabs"],
    ["xg24devkit", "matter"],
    ["xg27devkit", "none"],
    ["xg27devkit", "ble_arduino"],
    ["xg27devkit", "ble_silabs"],
    ["bgm220explorerkit", "none"],
    ["bgm220explorerkit", "ble_silabs"],
    ["lyra24p20", "none"],
    ["lyra24p20", "ble_arduino"],
    ["lyra24p20", "ble_silabs"],
    ["xiao_mg24", "none"],
    ["xiao_mg24", "ble_arduino"],
    ["xiao_mg24", "ble_silabs"],
    ["xiao_mg24", "zigbee"],
    ["xiao_mg24", "matter"],
]


testcase_list = {
    "basic_smoke": testcase_hil_basic_smoke,
    "serial_echo": testcase_hil_serial_echo,
    "watchdog": testcase_hil_watchdog,
    "eeprom": testcase_hil_eeprom,
    "adc": testcase_hil_adc,
    "thingplus_battery": testcase_hil_thingplus_battery,
    "imu_spi": testcase_hil_imu_spi,
    "si7021_wire": testcase_hil_si7021_wire,
    "ble_silabs_advertise": testcase_hil_ble_silabs_advertise,
    "ble_arduino_advertise": testcase_hil_ble_arduino_advertise,
    "matter_smoke": testcase_hil_matter_smoke,
    "matter_lightbulb": testcase_hil_matter_lightbulb,
    "matter_lightbulb_dimmable": testcase_hil_matter_lightbulb_dimmable,
    "matter_temp_sensor": testcase_hil_matter_temp_sensor,
    "matter_humidity_sensor": testcase_hil_matter_humidity_sensor,
    "matter_window_covering": testcase_hil_matter_window_covering,
    "zigbee_smoke": testcase_hil_zigbee_smoke,
}

# Matter Hub (Pi) HIL cases — used by --matter-otbr-only
matter_otbr_testcase_list = {
    "matter_lightbulb": testcase_hil_matter_lightbulb,
    "matter_lightbulb_dimmable": testcase_hil_matter_lightbulb_dimmable,
    "matter_temp_sensor": testcase_hil_matter_temp_sensor,
    "matter_humidity_sensor": testcase_hil_matter_humidity_sensor,
    "matter_window_covering": testcase_hil_matter_window_covering,
}

# Set by CLI flags
matter_otbr_only = False


def active_testcase_list():
    if matter_otbr_only:
        return matter_otbr_testcase_list
    return testcase_list


def main():
    signal.signal(signal.SIGINT, sigint_handler)
    print(f"{bcolors.HEADER}Silabs Arduino Core HIL test{bcolors.ENDC}")
    parse_optional_cli_arguments()
    current_board, current_board_port, config_file = get_board_and_port_and_cfg_file_from_arguments()

    completed_tests = 0
    successful_tests = 0
    failing_tests = []
    start_time = time.time()

    if config_file is None:
        total_number_of_tests = count_number_of_tests([current_board])
        completed_tests, successful_tests, failing_tests = run_tests(current_board, current_board_port, total_number_of_tests, completed_tests)
    else:
        boards, ports = get_boards_and_ports_from_config_file(config_file)
        total_number_of_tests = count_number_of_tests(boards)
        print(f"Using config file: '{config_file}'")
        print(f"Total number of tests: {total_number_of_tests}")
        for i in range(len(boards)):
            completed, successful, failing_tests = run_tests(boards[i], ports[i], total_number_of_tests, completed_tests)
            completed_tests += completed
            successful_tests += successful

    total_time = int(time.time() - start_time)
    failed_tests = completed_tests - successful_tests
    print("")
    print("-"*40)
    print(f"Total tests: {completed_tests}")
    print(f"Successful tests: {successful_tests}")
    print(f"Failed tests: {failed_tests}")
    if len(failing_tests) > 0:
        print("Failing tests:")
        for test in failing_tests:
            print(f"\t{test}")
    print(f"Total time: {total_time // 60}m {total_time % 60}s")
    print("-"*40)
    if completed_tests == successful_tests:
        print(f"{bcolors.OKGREEN}All tests were successful!{bcolors.ENDC}")
    else:
        print(f"{bcolors.FAIL}{failed_tests} testcases failed!{bcolors.ENDC}")


def board_variants_for(current_board):
    board_variants = []
    for variant in all_variants:
        if variant[0] != current_board:
            continue
        # Matter Pi HIL only needs the matter protocol stack variant
        if matter_otbr_only and variant[1] != "matter":
            continue
        board_variants.append(variant[1])
    return board_variants


def run_tests(current_board, current_board_port, global_total_tests=0, global_completed_tests=0):
    """
    Runs all available tests for a specified board
    """
    board_variants = board_variants_for(current_board)
    cases = active_testcase_list()

    print("")
    print(f"Board: '{current_board}'")
    print(f"Port: '{current_board_port}'")
    print(f"Variants: {board_variants}")
    if matter_otbr_only:
        print(f"Matter OTBR specific test cases: {list(cases.keys())}")

    testcase_count = len(cases) * len(board_variants)
    completed_tests = 0
    successful_tests = 0
    failing_tests = []

    if not board_variants:
        print(f"{bcolors.FAIL}No matching variants for '{current_board}' (matter-only requires a matter-capable board){bcolors.ENDC}")
        failing_tests.append(f"ALL TESTS ON '{current_board}'")
        return max(testcase_count, 1), successful_tests, failing_tests

    # Check if the serial port is available
    if not hil_util.check_serial_port_available(current_board_port):
        failing_tests.append(f"ALL TESTS ON '{current_board}'")
        return testcase_count, successful_tests, failing_tests

    # Burn bootloader
    if not hil_util.arduino_cli_burn_bootloader(current_board, current_board_port):
        failing_tests.append(f"ALL TESTS ON '{current_board}'")
        return testcase_count, successful_tests, failing_tests

    # Run tests for each variant
    for variant in board_variants:
        for test_name, test_function in cases.items():
            current_percent = int(((global_completed_tests + completed_tests + 1) / (global_total_tests)) * 100)
            print(f"{bcolors.OKGREEN}")
            print("-"*40)
            print(f"[{global_completed_tests + completed_tests + 1}/{global_total_tests}] ({current_percent}%): running '{test_name}' on '{current_board} ({variant})'")
            print("-"*40)
            print(f"{bcolors.ENDC}")

            did_run, success = test_function(current_board, variant, current_board_port)
            completed_tests += 1
            if not did_run:
                print(f"{bcolors.WARNING}")
                print(f"Testcase '{test_name}' skipped on '{current_board} ({variant})'")
                print(f"{bcolors.ENDC}")
                successful_tests += 1
                continue
            if success:
                print(f"{bcolors.OKGREEN}")
                print(f"Testcase '{test_name}' successful on '{current_board} ({variant})'")
                print(f"{bcolors.ENDC}")
                successful_tests += 1
            else:
                print(f"{bcolors.FAIL}")
                print(f"Testcase '{test_name}' failed on '{current_board} ({variant})'")
                print(f"{bcolors.ENDC}")
                failing_tests.append(f"'{test_name}' on '{current_board} ({variant})'")

    return completed_tests, successful_tests, failing_tests


def get_boards_and_ports_from_config_file(config_file):
    """
    Config file is a space separated file with the following format:
    <board_name> <port>
    For example:
    nano_matter /dev/tty.usbmodem6C9B9E713
    thingplusmatter /dev/tty.usbmodem0004490504431
    """
    with open(config_file, "r") as f:
        lines = f.readlines()
        boards = []
        ports = []
        for line in lines:
            if line.startswith("#"):
                continue
            board = line.split(" ")[0].strip()
            port = line.split(" ")[1].strip()
            boards.append(board)
            ports.append(port)
    return boards, ports


def count_number_of_tests(boards):
    total_tests = 0
    cases = active_testcase_list()
    for board in boards:
        total_tests += len(board_variants_for(board))
    return total_tests * len(cases)


def print_available_board_configs():
    board_names = []
    for board, _variant in all_variants:
        if board not in board_names:
            board_names.append(board)

    print("Supported boards:")
    for board in board_names:
        print(f"  {board}")


def parse_optional_cli_arguments():
    """
    Optional flags (stripped from sys.argv before positional board/port parsing):
      --matter-otbr <pi-ip>  Enable Matter Hub (Pi) HIL and prompt for SSH password
      --matter-only          Run only Matter Pi tests (implies needing --matter-otbr)
    """
    global matter_otbr_only

    args = sys.argv[1:]
    filtered = []
    i = 0
    host = None
    otbr_only = False
    while i < len(args):
        if args[i] == "--matter-otbr":
            if i + 1 >= len(args):
                print("Please provide the Matter Hub (Pi) IP after --matter-otbr")
                exit(-1)
            host = args[i + 1]
            i += 2
        elif args[i] == "--matter-otbr-only":
            otbr_only = True
            i += 1
        else:
            filtered.append(args[i])
            i += 1

    sys.argv = [sys.argv[0]] + filtered
    matter_otbr_only = otbr_only
    matter_otbr_util.otbr_host = host

    if otbr_only and not host:
        print("--matter-otbr-only requires --matter-otbr <pi-ip>")
        exit(-1)

    if host:
        print(f"Matter Hub (OTBR) address: {host}")
        if otbr_only:
            print("Matter OTBR only mode: running just the Matter Pi HIL tests")
        matter_otbr_util.ensure_ssh_password()
    else:
        print("Matter Hub (OTBR) not specified; Matter OTBR specific tests will be skipped")


def get_board_and_port_and_cfg_file_from_arguments():
    try:
        input_board_name = sys.argv[1]
    except Exception:
        print("Please provide a target board name or config file path in the first argument!")
        print("Optional: --matter-otbr <pi-ip> [--matter-only]")
        print_available_board_configs()
        exit(-1)

    # Check if we have been provided with a config file
    if input_board_name.endswith(".cfg"):
        return None, None, input_board_name

    try:
        upload_port = sys.argv[2]
    except Exception:
        print("Please provide an upload port in the second argument!")
        exit(-1)

    # Parse the board name and upload port
    found = False
    for variant in all_variants:
        if variant[0] == input_board_name:
            found = True
            break
    if not found:
        print(f"Board with the name '{input_board_name}' not found!")
        print_available_board_configs()
        exit(-1)

    return input_board_name, upload_port, None


def sigint_handler(sig, frame):
    print("\nExiting...")
    sys.exit(100)


if __name__ == "__main__":
    main()
