"""
Communicate directly to a Yost dongle through USB Serial
This is used solely for wireless streaming through the dongle, which is 
very inefficient through the official threespace_api
"""
from typing import Optional, Tuple
import serial
import struct


def _print(*args):
    print("[Yost custom serial comm]", *args)


def read_dongle_port(port: serial.Serial) -> Tuple[int, int, Optional[bytes]]:
    raw = port.read(2)
    if len(raw) != 2:
        _print("Port has no data")
        return -1, 0, None
    fail, logical_id = struct.unpack(">BB", raw)
    if fail == 0:
        raw = port.read(1)
        if raw:
            length = struct.unpack(">B", raw)[0]
            raw = port.read(length)
            return fail, logical_id, raw

    _print("Read failed")
    return fail, logical_id, None


# send commands through dongle to sensor with logical id
def write_dongle_port(port: serial.Serial, data: str, logical_id: int):
    # _print("Sending to logical_id", logical_id, "data", data)
    data = chr(logical_id) + data
    checksum = sum(ord(v) for v in data) % 256
    # Build command
    command = chr(0xF8) + data + chr(checksum)
    # Send
    port.write(command.encode("latin"))


def start_dongle_streaming(port: serial.Serial, logical_ids):

    for logical_id in logical_ids:
        # Stop previous streaming
        # write_dongle_port(port, chr(86), logical_id=logical_id)
        # read_dongle_port(port)

        # set streaming slots
        write_dongle_port(
            port,
            chr(80)  # set streaming slots
            + chr(1)  # tared orientation as Euler Angle
            + chr(202)  # get battery percentage
            + chr(255)
            + chr(255)
            + chr(255)
            + chr(255)
            + chr(255)
            + chr(255),
            logical_id=logical_id,
        )
        read_dongle_port(port)

        # set timing interval=0 duration=0xFFFFFFFF delay=0
        write_dongle_port(
            port,
            chr(82)  # Set streaming interval
            + chr(0)
            + chr(0)
            + chr(0)
            + chr(0)
            + chr(255)
            + chr(255)
            + chr(255)
            + chr(255)
            + chr(0)
            + chr(0)
            + chr(0)
            + chr(0),
            logical_id=logical_id,
        )
        read_dongle_port(port)

        # start streaming
        write_dongle_port(port, chr(85), logical_id=logical_id)
        read_dongle_port(port)


def stop_dongle_streaming(port: serial.Serial, logical_ids):
    for logical_id in logical_ids:
        write_dongle_port(port, chr(86), logical_id=logical_id)
