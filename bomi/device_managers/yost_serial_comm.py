"""
Communicate directly with Yost dongles and sensors through USB Serial.

This is currently used solely for handling streaming, which is VERY inefficient through 
the official threespace_api, especially for the dongle.

Everything else (device discovery, management, config etc.) should still be
managed through the threespace_api, although this module is a great starting point
to reimplement the full API.
"""
from __future__ import annotations
from typing import Dict, List, Optional, Tuple
from queue import Queue
from timeit import default_timer
import math
from enum import Enum

from serial import Serial
import struct

from .yost_cmds import Cmd, Cmds, WLCmds
from bomi.datastructure import Packet

RAD2DEG = 180 / math.pi


def _print(*args):
    print("[Yost custom serial comm]", *args)


class PacketField(str, Enum):
    PITCH = "Pitch"
    YAW = "Yaw"
    ROLL = "Roll"
    BATTERY = "Battery"
    TIME = "Time"
    NAME = "Name"

    def __str__(self):
        return self.value


class Dongles:
    """
    Manages streaming with Yost wireless Dongles

    Must be used as a context manager

    ```
    with Dongles(port_names, wl_mps, 0) as dongles:
        packets_read += dongles.recv(queue)
    ```
    """

    # Use __slots__ for faster attribute lookup. https://docs.python.org/3/reference/datamodel.html#slots
    __slots__ = (
        "port_names",
        "wl_mps",
        "interval_us",
        "streaming_slots",
        "out_sz",
        "out_struct",
        "ports",
        "logical_ids",
    )

    def __init__(
        self,
        port_names: List[str],
        wl_mps: List[Dict[int, str]],
        interval_us=0,
        streaming_slots: List[Cmd] = [
            Cmds.getTaredOrientationAsEulerAngles,
            WLCmds.getBatteryPercentRemaining,
        ],
    ):
        """
        port_name: List of COM port names connected to TSDongles
        wl_mps: List of Dict[logical_id, device_name] that correspond to the dongles
        """
        self.port_names = port_names
        self.wl_mps = wl_mps
        self.interval_us = interval_us
        self.streaming_slots = streaming_slots

        self.out_sz = sum(slot.out_len for slot in streaming_slots)
        self.out_struct = ">" + "".join([slot.out_struct[1:] for slot in streaming_slots])  # type: ignore

        # used in context manager
        self.ports: List[Serial] = []
        self.logical_ids: List[List[int]] = []

    def __enter__(self) -> Dongles:
        for port_name, wl_mp in zip(self.port_names, self.wl_mps):
            port = Serial(port_name, 115200, timeout=1)
            self.ports.append(port)
            logical_ids = list(wl_mp.keys())
            self.logical_ids.append(logical_ids)
            start_dongle_streaming(
                port, logical_ids, self.interval_us, self.streaming_slots
            )

        return self

    def __exit__(self, exctype, excinst, exctb):
        for port, logical_ids in zip(self.ports, self.logical_ids):
            stop_dongle_streaming(port, logical_ids)
            port.close()
        self.ports = []
        self.logical_ids = []

    def recv(self, queue: Queue[Packet]) -> int:
        """
        Read all available packets into queue.
        Returns the number of packets read.
        """
        now = default_timer()
        i = 0
        for port, wl_mp in zip(self.ports, self.wl_mps):
            failed, logical_id, raw = read_dongle_port(port)
            if failed == 0 and raw and len(raw) == self.out_sz:
                b = struct.unpack(self.out_struct, raw)
                channel_readings = {
                    PacketField.PITCH: b[0] * RAD2DEG,
                    PacketField.YAW: b[1] * RAD2DEG,
                    PacketField.ROLL: b[2] * RAD2DEG,
                    PacketField.BATTERY: b[3],
                }
                queue.put(Packet(now, wl_mp[logical_id], channel_readings))
                i += 1
        return i


class WiredSensors:
    """
    Manages streaming with Yost sensors plugged in through USB

    Must be used as a context manager

    ```
    with WiredSensors(port_names, 0) as wired_sensors:
        packets_read += wired_sensors.recv(queue)
    ```
    """

    # Use __slots__ for faster attribute lookup. https://docs.python.org/3/reference/datamodel.html#slots
    __slots__ = (
        "port_names",
        "names",
        "interval_us",
        "streaming_slots",
        "out_sz",
        "out_struct",
        "ports",
        "logical_ids",
    )

    def __init__(
        self,
        port_names: List[str],
        names: List[str],
        interval_us=0,
        streaming_slots: List[Cmd] = [
            Cmds.getTaredOrientationAsEulerAngles,
            WLCmds.getBatteryPercentRemaining,
        ],
    ):
        """
        port_name: List of COM port names connected to TSDongles
        wl_mps: List of Dict[logical_id, device_name] that correspond to the dongles
        """
        self.port_names = port_names
        self.names: List[str] = names
        self.interval_us = interval_us
        self.streaming_slots = streaming_slots

        self.out_sz = sum(slot.out_len for slot in streaming_slots)
        self.out_struct = ">" + "".join([slot.out_struct[1:] for slot in streaming_slots])  # type: ignore

        self.ports: List[Serial] = []

    def __enter__(self) -> WiredSensors:
        for port_name in self.port_names:
            port = Serial(port_name, 115200, timeout=1)
            self.ports.append(port)
            start_wired_streaming(port, self.interval_us)

        return self

    def __exit__(self, exctype, excinst, exctb):
        for port in self.ports:
            stop_wired_streaming(port)
            port.close()
        self.ports = []

    def recv(self, queue: Queue[Packet]) -> int:
        """
        Read all available packets into queue.
        Returns the number of packets read.
        """
        now = default_timer()
        i = 0
        for port, name in zip(self.ports, self.names):
            raw = port.read(self.out_sz)
            b = struct.unpack(self.out_struct, raw)
            channel_readings = {
                PacketField.PITCH: b[0] * RAD2DEG,
                PacketField.YAW: b[1] * RAD2DEG,
                PacketField.ROLL: b[2] * RAD2DEG,
                PacketField.BATTERY: b[3],
            }
            queue.put(Packet(now, name, channel_readings))
            i += 1
        return i


def start_dongle_streaming(
    port: Serial, logical_ids: List[int], interval_us: int, slots: List[Cmd]
):
    """
    Configure and start wireless streaming through a dongle.

    Parameters
    ----------
    port: Serial port of the dongle
    logical_ids: Logical ids of the wireless sensors configured on the dongle
    interval_us: interval between each sample
    slots: Streaming slots
    """
    assert len(slots) <= 8, "Must use 8 or less slots"
    cmds = [slot.cmd for slot in slots] + [0xFF] * (8 - len(slots))

    for logical_id in logical_ids:
        # set streaming slots
        write_dongle_port(
            port,
            Cmds._setStreamingSlots(*cmds),
            logical_id=logical_id,
        )
        read_dongle_port(port)

        # set timing interval, duration=0xFFFFFFFF delay=0
        write_dongle_port(
            port,
            Cmds._setStreamingTiming(interval_us, 0xFFFFFFFF, 500_000),
            logical_id=logical_id,
        )
        read_dongle_port(port)

    # start streaming
    for logical_id in logical_ids:
        write_dongle_port(port, Cmds.startStreaming(), logical_id=logical_id)

    for _ in logical_ids:
        read_dongle_port(port)


def stop_dongle_streaming(port: Serial, logical_ids):
    for logical_id in logical_ids:
        write_dongle_port(port, Cmds.stopStreaming(), logical_id=logical_id)
    for _ in logical_ids:
        read_dongle_port(port)


def start_wired_streaming(port: Serial, interval_us: int):
    # set streaming slots
    write_port(
        port,
        Cmds._setStreamingSlots(
            Cmds.getTaredOrientationAsEulerAngles.cmd,
            WLCmds.getBatteryPercentRemaining.cmd,
            0xFF,
            0xFF,
            0xFF,
            0xFF,
            0xFF,
            0xFF,
        ),
    )

    # set timing interval, duration=0xFFFFFFFF delay=0
    write_port(
        port,
        Cmds._setStreamingTiming(interval_us, 0xFFFFFFFF, 500_000),
    )

    # start streaming
    write_port(port, Cmds.startStreaming())


def stop_wired_streaming(port: Serial):
    write_port(port, Cmds.stopStreaming())


def read_dongle_port(port: Serial) -> Tuple[int, int, Optional[bytes]]:
    """
    Implements 3-Space User Manual, Section 4.3.3 Binary Command Response

    Returns: (failed, logical_id, response data)
    """
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


def write_dongle_port(port: Serial, data: bytes, logical_id: int):
    "send commands through dongle to sensor with logical id"
    # _print("Sending to logical_id", logical_id, "data", data)
    data = bytes((logical_id,)) + data
    checksum = sum(data) % 256
    command = bytes((0xF8,)) + data + bytes((checksum,))
    # Send
    port.write(command)


def write_port(port: Serial, data: bytes):
    """
    Implements 3-Space User Manual, Section 4.2.1 Binary Packet Format

    Send commands to wired sensor

    There isn't an equivalent `read_port` for wired sensors because there's no packet structure,
    simply the return data in raw bytes. Hence, `port.read` would suffice.
    """
    checksum = sum(data) % 256
    command = bytes((0xF7,)) + data + bytes((checksum,))
    # Send
    port.write(command)
