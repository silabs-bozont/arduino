#!/usr/bin/env python3
"""Bridge a local USB RCP serial port to TCP for Colima/Docker OTBR (macOS)."""
import argparse
import select
import socket
import sys
import time

import serial


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--serial", required=True)
    parser.add_argument("--port", type=int, default=9999)
    parser.add_argument("--baud", type=int, default=460800)
    args = parser.parse_args()

    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("0.0.0.0", args.port))
    srv.listen(1)
    print(f"listening on 0.0.0.0:{args.port} -> {args.serial} @ {args.baud}", flush=True)

    while True:
        conn, addr = srv.accept()
        print(f"client connected: {addr}", flush=True)
        ser = None
        try:
            ser = serial.Serial(
                port=args.serial,
                baudrate=args.baud,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                timeout=0,
                write_timeout=1,
                xonxoff=False,
                rtscts=False,
                dsrdtr=False,
            )
            conn.setblocking(False)
            while True:
                r, _, _ = select.select([conn, ser], [], [], 1.0)
                if conn in r:
                    data = conn.recv(4096)
                    if not data:
                        raise ConnectionError("tcp closed")
                    ser.write(data)
                    ser.flush()
                if ser in r:
                    data = ser.read(4096)
                    if data:
                        conn.sendall(data)
        except Exception as e:
            print(f"session ended: {e}", flush=True)
        finally:
            try:
                conn.close()
            except Exception:
                pass
            if ser is not None:
                try:
                    ser.close()
                except Exception:
                    pass
            time.sleep(0.2)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(0)
