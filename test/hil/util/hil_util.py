import serial
import subprocess
import time
import asyncio
import threading
from bleak import BleakScanner


class bcolors:
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKCYAN = '\033[96m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'


def check_serial_port_available(port):
    try:
        ser = serial.Serial(port, baudrate=115200, timeout=10)
        ser.close()
    except serial.SerialException as e:
        print(f"Error opening serial port: {e}")
        return False
    except Exception as e:
        print(f"Error: {e}")
        return False
    return True


def check_serial_response(port, expected_response, outgoing_payload=None, timeout=2):
    print("-"*40)
    print(f"Checking serial response on '{port}'")
    print("-"*40)

    try:
        ser = serial.Serial(port, baudrate=115200, timeout=10)
        if outgoing_payload is not None:
            ser.write(outgoing_payload.encode("utf-8"))
        time.sleep(timeout)
        response = ser.read_all().decode("utf-8", errors="ignore")
        ser.close()

        print(response)

        if expected_response in response:
            print("Serial response is correct!")
            return True
        else:
            print("Serial response is incorrect!")
            return False
    except serial.SerialException as e:
        print(f"Error opening serial port: {e}")
    except Exception as e:
        print(f"Error: {e}")
    return False


def get_serial_response(port, outgoing_payload=None, timeout=2):
    print("-"*40)
    print(f"Getting serial response on '{port}'")
    print("-"*40)

    try:
        ser = serial.Serial(port, baudrate=115200, timeout=10)
        if outgoing_payload is not None:
            ser.write(outgoing_payload.encode("utf-8"))
        time.sleep(timeout)
        response = ser.read_all().decode("utf-8")
        ser.close()
        print(response)
        return response
    except serial.SerialException as e:
        print(f"Error opening serial port: {e}")
        return None


def check_for_ble_device_advertisement(device_advertised_name, timeout=2):
    async def check_for_ble_device_advertisement(device_advertised_name, timeout):
        print("-"*40)
        print(f"Checking for advertising BLE device '{device_advertised_name}'")
        print("-"*40)

        devices = await BleakScanner.discover(return_adv=True, timeout=timeout)

        found = False
        for d, a in devices.values():
            if a.local_name == device_advertised_name:
                found = True
                print(f"{bcolors.OKGREEN}")
            print()
            print(d)
            print(a)
            if found:
                print(f"{bcolors.ENDC}")

        print()
        if found:
            print(f"Found BLE device: '{device_advertised_name}'")
            return True

        print(f"BLE device '{device_advertised_name}' not found")
        return False

    loop = asyncio.get_event_loop()
    result = loop.run_until_complete(check_for_ble_device_advertisement(device_advertised_name, timeout))
    return result


def arduino_cli_build_and_flash(board, protocol_stack, sketch_path, port=None):
    """
    Builds the specified sketch for the specified variant with Arduino CLI
    """
    fqbn = "SiliconLabs:silabs:" + board + ":protocol_stack=" + protocol_stack
    print("-"*40)
    print(f"Building '{sketch_path}' for '{fqbn}'")
    print("-"*40)
    build_start_time = time.time()
    build_process = subprocess.Popen(
        ["arduino-cli", "compile", sketch_path, "-b", fqbn, "--warnings", "all"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )
    stdout, stderr = build_process.communicate(timeout=300)
    print(stderr.decode("utf-8"))
    print(stdout.decode("utf-8"))

    build_end_time = time.time()
    total_build_time = int(build_end_time - build_start_time)
    if build_process.returncode != 0:
        print("Build failed!")
        return False

    print("Build successful!")
    print(f"Build time: {total_build_time // 60}m {total_build_time % 60}s")

    if port is None:
        return True

    print("-"*40)
    print(f"Uploading '{sketch_path}' to '{board}' ({protocol_stack}) on '{port}'")
    print("-"*40)

    upload_start_time = time.time()
    upload_process = subprocess.Popen(
        ["arduino-cli", "upload", sketch_path, "-b", fqbn, "-p", port],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )
    stdout, stderr = upload_process.communicate(timeout=300)
    print(stderr.decode("utf-8"))
    print(stdout.decode("utf-8"))

    if upload_process.returncode != 0:
        print("Upload failed!")
        return False

    upload_end_time = time.time()
    total_upload_time = int(upload_end_time - upload_start_time)

    print("Upload successful!")
    print(f"Upload time: {total_upload_time // 60}m {total_upload_time % 60}s")
    return True


def arduino_cli_burn_bootloader(board, port):
    """
    Burns the bootloader for the specified board with Arduino CLI
    """
    fqbn = "SiliconLabs:silabs:" + board
    print("-"*40)
    print(f"Burning bootloader for '{board}'")
    print("-"*40)

    programmer = "commander"
    if board == "nano_matter":
        programmer = "openocd"

    burn_start_time = time.time()
    burn_process = subprocess.Popen(
        ["arduino-cli", "burn-bootloader", "--fqbn", fqbn, "-P", programmer, "-p", port],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )
    stdout, stderr = burn_process.communicate(timeout=300)
    print(stderr.decode("utf-8"))
    print(stdout.decode("utf-8"))

    burn_end_time = time.time()
    total_burn_time = int(burn_end_time - burn_start_time)
    if burn_process.returncode != 0:
        print("Bootloader burn failed!")
        return False

    print("Bootloader burn successful!")
    print(f"Time: {total_burn_time // 60}m {total_burn_time % 60}s")
    return True


class SerialMonitor:
    """
    Background serial reader so DUT output is not missed while SSH/commissioning runs.
    """

    def __init__(self, port, baudrate=115200):
        self.port = port
        self.buf = ""
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._ser = serial.Serial(port, baudrate=baudrate, timeout=0.5)
        self._thread = threading.Thread(target=self._read_loop, daemon=True)
        self._thread.start()
        print(f"Serial Monitor started on '{port}'")

    def _read_loop(self):
        while not self._stop.is_set():
            try:
                chunk = self._ser.read(4096).decode("utf-8", errors="ignore")
            except Exception:
                break
            if chunk:
                print(chunk, end="", flush=True)
                with self._lock:
                    self.buf += chunk

    def text(self):
        with self._lock:
            return self.buf

    def wait_for(self, expected_response, timeout=60):
        print("-"*40)
        print(f"Serial Monitor waiting up to {timeout}s for: {expected_response!r}")
        print("-"*40)
        deadline = time.time() + timeout
        while time.time() < deadline:
            with self._lock:
                if expected_response in self.buf:
                    print("Serial response matched!")
                    return True
            time.sleep(0.1)
        print(f"Timed out waiting for: {expected_response!r}")
        return False

    def close(self):
        self._stop.set()
        self._thread.join(timeout=2)
        try:
            self._ser.close()
        except Exception:
            pass
        print(f"Serial Monitor closed on '{self.port}'")
