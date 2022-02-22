"""
Communicate directly with a Yost dongle through USB Serial.
This is used solely for wireless streaming through the dongle, which is 
very inefficient through the official threespace_api.
Everything else (device discovery, management, config etc.) should still be
managed through the threespace_api. 
"""
from __future__ import annotations
from typing import Any, Deque, Dict, Final, List, NamedTuple, Optional, Tuple
from timeit import default_timer
import math

import serial
import struct

from bomi.datastructure import Packet

RAD2DEG: Final = 180 / math.pi


def _print(*args):
    print("[Yost custom serial comm]", *args)


def read_dongle_port(port: serial.Serial) -> Tuple[int, int, Optional[bytes]]:
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


# send commands through dongle to sensor with logical id
def write_dongle_port(port: serial.Serial, data: bytes, logical_id: int):
    # _print("Sending to logical_id", logical_id, "data", data)
    data = bytes((logical_id,)) + data
    checksum = sum(data) % 256
    command = bytes((0xF8,)) + data + bytes((checksum,))
    # Send
    port.write(command)


class Cmd(NamedTuple):
    cmd: int  # command value
    out_len: int  # length of response data (bytes)
    out_struct: str | None  # struct of the response data
    in_len: int  # length of request data (bytes)
    in_struct: str | None  # struct of request data
    compat: int

    def __call__(self, *args: Any) -> bytes:
        if self.in_struct:
            b = struct.pack(self.in_struct, *args)
            assert len(b) == self.in_len
            payload = bytes((self.cmd,)) + b
            return payload

        return bytes((self.cmd,))


class Cmds:
    checkLongCommands = Cmd(0x19, 1, ">B", 0, None, 1)
    startStreaming = Cmd(0x55, 0, None, 0, None, 1)
    stopStreaming = Cmd(0x56, 0, None, 0, None, 1)
    updateCurrentTimestamp = Cmd(0x5F, 0, None, 4, ">I", 1)
    setLEDMode = Cmd(0xC4, 0, None, 1, ">B", 1)
    getLEDMode = Cmd(0xC8, 1, ">B", 0, None, 1)
    _setWiredResponseHeaderBitfield = Cmd(0xDD, 0, None, 4, ">I", 1)
    _getWiredResponseHeaderBitfield = Cmd(0xDE, 4, ">I", 0, None, 1)
    getFirmwareVersionString = Cmd(0xDF, 12, ">12s", 0, None, 1)
    commitSettings = Cmd(0xE1, 0, None, 0, None, 1)
    softwareReset = Cmd(0xE2, 0, None, 0, None, 1)
    getHardwareVersionString = Cmd(0xE6, 32, ">32s", 0, None, 1)
    getSerialNumber = Cmd(0xED, 4, ">I", 0, None, 1)
    setLEDColor = Cmd(0xEE, 0, None, 12, ">fff", 1)
    getLEDColor = Cmd(0xEF, 12, ">fff", 0, None, 1)
    setJoystickAndMousePresentRemoved = Cmd(0xFD, 0, None, 2, ">BB", 1)
    getJoystickAndMousePresentRemoved = Cmd(0xFE, 2, ">B", 0, None, 1)
    null = Cmd(0xFF, 0, None, 0, None, 1)

    getTaredOrientationAsQuaternion: Final = Cmd(0x0, 16, ">4f", 0, None, 1)
    getTaredOrientationAsEulerAngles: Final = Cmd(0x1, 12, ">fff", 0, None, 1)
    getTaredOrientationAsRotationMatrix: Final = Cmd(0x2, 36, ">9f", 0, None, 1)
    getTaredOrientationAsAxisAngle: Final = Cmd(0x3, 16, ">4f", 0, None, 1)
    getTaredOrientationAsTwoVector: Final = Cmd(0x4, 24, ">6f", 0, None, 1)
    getDifferenceQuaternion: Final = Cmd(0x5, 16, ">4f", 0, None, 1)
    getUntaredOrientationAsQuaternion: Final = Cmd(0x6, 16, ">4f", 0, None, 1)
    getUntaredOrientationAsEulerAngles: Final = Cmd(0x7, 12, ">fff", 0, None, 1)
    getUntaredOrientationAsRotationMatrix: Final = Cmd(0x8, 36, ">9f", 0, None, 1)
    getUntaredOrientationAsAxisAngle: Final = Cmd(0x9, 16, ">4f", 0, None, 1)
    getUntaredOrientationAsTwoVector: Final = Cmd(0xA, 24, ">6f", 0, None, 1)
    getTaredTwoVectorInSensorFrame: Final = Cmd(0xB, 24, ">6f", 0, None, 1)
    getUntaredTwoVectorInSensorFrame: Final = Cmd(0xC, 24, ">6f", 0, None, 1)
    setEulerAngleDecompositionOrder: Final = Cmd(0x10, 0, None, 1, ">B", 1)
    setMagnetoresistiveThreshold: Final = Cmd(0x11, 0, None, 16, ">fIff", 3)
    setAccelerometerResistanceThreshold: Final = Cmd(0x12, 0, None, 8, ">fI", 3)
    offsetWithCurrentOrientation: Final = Cmd(0x13, 0, None, 0, None, 3)
    resetBaseOffset: Final = Cmd(0x14, 0, None, 0, None, 3)
    offsetWithQuaternion: Final = Cmd(0x15, 0, None, 16, ">4f", 3)
    setBaseOffsetWithCurrentOrientation: Final = Cmd(0x16, 0, None, 0, None, 3)
    getAllNormalizedComponentSensorData: Final = Cmd(0x20, 36, ">9f", 0, None, 1)
    getNormalizedGyroRate: Final = Cmd(0x21, 12, ">fff", 0, None, 1)
    getNormalizedAccelerometerVector: Final = Cmd(0x22, 12, ">fff", 0, None, 1)
    getNormalizedCompassVector: Final = Cmd(0x23, 12, ">fff", 0, None, 1)
    getAllCorrectedComponentSensorData: Final = Cmd(0x25, 36, ">9f", 0, None, 1)
    getCorrectedGyroRate: Final = Cmd(0x26, 12, ">fff", 0, None, 1)
    getCorrectedAccelerometerVector: Final = Cmd(0x27, 12, ">fff", 0, None, 1)
    getCorrectedCompassVector: Final = Cmd(0x28, 12, ">fff", 0, None, 1)
    getCorrectedLinearAccelerationInGlobalSpace: Final = Cmd(
        0x29, 12, ">fff", 0, None, 1
    )
    getTemperatureC: Final = Cmd(0x2B, 4, ">f", 0, None, 1)
    getTemperatureF: Final = Cmd(0x2C, 4, ">f", 0, None, 1)
    getConfidenceFactor: Final = Cmd(0x2D, 4, ">f", 0, None, 1)
    getAllRawComponentSensorData: Final = Cmd(0x40, 36, ">9f", 0, None, 1)
    getRawGyroscopeRate: Final = Cmd(0x41, 12, ">fff", 0, None, 1)
    getRawAccelerometerData: Final = Cmd(0x42, 12, ">fff", 0, None, 1)
    getRawCompassData: Final = Cmd(0x43, 12, ">fff", 0, None, 1)
    _setStreamingSlots: Final = Cmd(0x50, 0, None, 8, ">8B", 1)
    _getStreamingSlots: Final = Cmd(0x51, 8, ">8B", 0, None, 1)
    _setStreamingTiming: Final = Cmd(0x52, 0, None, 12, ">III", 1)
    _getStreamingTiming: Final = Cmd(0x53, 12, ">III", 0, None, 1)
    _getStreamingBatch: Final = Cmd(0x54, 0, None, 0, None, 1)
    tareWithCurrentOrientation: Final = Cmd(0x60, 0, None, 0, None, 1)
    tareWithQuaternion: Final = Cmd(0x61, 0, None, 16, ">4f", 1)
    tareWithRotationMatrix: Final = Cmd(0x62, 0, None, 36, ">9f", 1)
    setStaticAccelerometerTrustValue: Final = Cmd(0x63, 0, None, 4, ">f", 2)
    setConfidenceAccelerometerTrustValues: Final = Cmd(0x64, 0, None, 8, ">ff", 2)
    setStaticCompassTrustValue: Final = Cmd(0x65, 0, None, 4, ">f", 2)
    setConfidenceCompassTrustValues: Final = Cmd(0x66, 0, None, 8, ">ff", 2)
    setDesiredUpdateRate: Final = Cmd(0x67, 0, None, 4, ">I", 1)
    setReferenceVectorMode: Final = Cmd(0x69, 0, None, 1, ">B", 1)
    setOversampleRate: Final = Cmd(0x6A, 0, None, 1, ">B", 1)
    setGyroscopeEnabled: Final = Cmd(0x6B, 0, None, 1, ">B", 1)
    setAccelerometerEnabled: Final = Cmd(0x6C, 0, None, 1, ">B", 1)
    setCompassEnabled: Final = Cmd(0x6D, 0, None, 1, ">B", 1)
    setAxisDirections: Final = Cmd(0x74, 0, None, 1, ">B", 1)
    setRunningAveragePercent: Final = Cmd(0x75, 0, None, 4, ">f", 1)
    setCompassReferenceVector: Final = Cmd(0x76, 0, None, 12, ">fff", 1)
    setAccelerometerReferenceVector: Final = Cmd(0x77, 0, None, 12, ">fff", 1)
    resetKalmanFilter: Final = Cmd(0x78, 0, None, 0, None, 1)
    setAccelerometerRange: Final = Cmd(0x79, 0, None, 1, ">B", 1)
    setFilterMode: Final = Cmd(0x7B, 0, None, 1, ">B", 1)
    setRunningAverageMode: Final = Cmd(0x7C, 0, None, 1, ">B", 1)
    setGyroscopeRange: Final = Cmd(0x7D, 0, None, 1, ">B", 1)
    setCompassRange: Final = Cmd(0x7E, 0, None, 1, ">B", 1)
    getTareAsQuaternion: Final = Cmd(0x80, 16, ">4f", 0, None, 1)
    getTareAsRotationMatrix: Final = Cmd(0x81, 36, ">9f", 0, None, 1)
    getAccelerometerTrustValues: Final = Cmd(0x82, 8, ">ff", 0, None, 2)
    getCompassTrustValues: Final = Cmd(0x83, 8, ">ff", 0, None, 2)
    getCurrentUpdateRate: Final = Cmd(0x84, 4, ">I", 0, None, 1)
    getCompassReferenceVector: Final = Cmd(0x85, 12, ">fff", 0, None, 1)
    getAccelerometerReferenceVector: Final = Cmd(0x86, 12, ">fff", 0, None, 1)
    getGyroscopeEnabledState: Final = Cmd(0x8C, 1, ">B", 0, None, 1)
    getAccelerometerEnabledState: Final = Cmd(0x8D, 1, ">B", 0, None, 1)
    getCompassEnabledState: Final = Cmd(0x8E, 1, ">B", 0, None, 1)
    getAxisDirections: Final = Cmd(0x8F, 1, ">B", 0, None, 1)
    getOversampleRate: Final = Cmd(0x90, 1, ">B", 0, None, 1)
    getRunningAveragePercent: Final = Cmd(0x91, 4, ">f", 0, None, 1)
    getDesiredUpdateRate: Final = Cmd(0x92, 4, ">I", 0, None, 1)
    getAccelerometerRange: Final = Cmd(0x94, 1, ">B", 0, None, 1)
    getFilterMode: Final = Cmd(0x98, 1, ">B", 0, None, 1)
    getRunningAverageMode: Final = Cmd(0x99, 1, ">B", 0, None, 1)
    getGyroscopeRange: Final = Cmd(0x9A, 1, ">B", 0, None, 1)
    getCompassRange: Final = Cmd(0x9B, 1, ">B", 0, None, 1)
    getEulerAngleDecompositionOrder: Final = Cmd(0x9C, 1, ">B", 0, None, 1)
    getMagnetoresistiveThreshold: Final = Cmd(0x9D, 16, ">fIff", 0, None, 3)
    getAccelerometerResistanceThreshold: Final = Cmd(0x9E, 8, ">fI", 0, None, 3)
    getOffsetOrientationAsQuaternion: Final = Cmd(0x9F, 16, ">4f", 0, None, 3)
    setCompassCalibrationCoefficients: Final = Cmd(0xA0, 0, None, 48, ">12f", 1)
    setAccelerometerCalibrationCoefficients: Final = Cmd(0xA1, 0, None, 48, ">12f", 1)
    getCompassCalibrationCoefficients: Final = Cmd(0xA2, 48, ">12f", 0, None, 1)
    getAccelerometerCalibrationCoefficients: Final = Cmd(0xA3, 48, ">12f", 0, None, 1)
    getGyroscopeCalibrationCoefficients: Final = Cmd(0xA4, 48, ">12f", 0, None, 1)
    beginGyroscopeAutoCalibration: Final = Cmd(0xA5, 0, None, 0, None, 1)
    setGyroscopeCalibrationCoefficients: Final = Cmd(0xA6, 0, None, 48, ">12f", 1)
    setCalibrationMode: Final = Cmd(0xA9, 0, None, 1, ">B", 1)
    getCalibrationMode: Final = Cmd(0xAA, 1, ">B", 0, None, 1)
    setOrthoCalibrationDataPointFromCurrentOrientation: Final = Cmd(
        0xAB, 0, None, 0, None, 1
    )
    setOrthoCalibrationDataPointFromVector: Final = Cmd(0xAC, 0, None, 14, ">BBfff", 1)
    getOrthoCalibrationDataPoint: Final = Cmd(0xAD, 12, ">fff", 2, ">BB", 1)
    performOrthoCalibration: Final = Cmd(0xAE, 0, None, 0, None, 1)
    clearOrthoCalibrationData: Final = Cmd(0xAF, 0, None, 0, None, 1)
    setSleepMode: Final = Cmd(0xE3, 0, None, 1, ">B", 1)
    getSleepMode: Final = Cmd(0xE4, 1, ">B", 0, None, 1)
    setJoystickEnabled: Final = Cmd(0xF0, 0, None, 1, ">B", 1)
    setMouseEnabled: Final = Cmd(0xF1, 0, None, 1, ">B", 1)
    getJoystickEnabled: Final = Cmd(0xF2, 1, ">B", 0, None, 1)
    getMouseEnabled: Final = Cmd(0xF3, 1, ">B", 0, None, 1)
    setControlMode: Final = Cmd(0xF4, 0, None, 3, ">BBB", 1)
    setControlData: Final = Cmd(0xF5, 0, None, 7, ">BBBf", 1)
    getControlMode: Final = Cmd(0xF6, 1, ">B", 2, ">BB", 1)
    getControlData: Final = Cmd(0xF7, 4, ">f", 3, ">BBB", 1)
    setMouseAbsoluteRelativeMode: Final = Cmd(0xFB, 0, None, 1, ">B", 1)
    getMouseAbsoluteRelativeMode: Final = Cmd(0xFC, 1, ">B", 0, None, 1)


class WLCmds:
    _getWirelessPanID = Cmd(0xC0, 2, ">H", 0, None, 1)
    _setWirelessPanID = Cmd(0xC1, 0, None, 2, ">H", 1)
    _getWirelessChannel = Cmd(0xC2, 1, ">B", 0, None, 1)
    _setWirelessChannel = Cmd(0xC3, 0, None, 1, ">B", 1)
    commitWirelessSettings = Cmd(0xC5, 0, None, 0, None, 1)
    getWirelessAddress = Cmd(0xC6, 2, ">H", 0, None, 1)
    getBatteryVoltage = Cmd(0xC9, 4, ">f", 0, None, 1)
    getBatteryPercentRemaining = Cmd(0xCA, 1, ">B", 0, None, 1)
    getBatteryStatus = Cmd(0xCB, 1, ">B", 0, None, 1)
    getButtonState = Cmd(0xFA, 1, ">B", 0, None, 1)


class DongleError(Exception):
    pass


class Dongles:
    def __init__(self, port_names: List[str], wl_mps: List[Dict[int, str]]):
        """
        port_name: List of COM port names connected to TSDongles
        wl_mps: List of Dict[logical_id, device_name] that correspond to the dongles
        """
        self.port_names = port_names
        self.wl_mps = wl_mps
        self.ports: List[serial.Serial] = []
        self.logical_ids: List[Tuple[int, ...]] = []

    def __enter__(self) -> Dongles:
        for port_name, wl_mp in zip(self.port_names, self.wl_mps):
            port = serial.Serial(port_name, 115200, timeout=1)
            self.ports.append(port)
            logical_ids = tuple(wl_mp.keys())
            self.logical_ids.append(logical_ids)
            start_dongle_streaming(port, logical_ids)

        return self

    def __call__(self, queue: Deque[Packet]) -> int:
        now = default_timer()
        i = 0
        for port in self.ports:
            failed, logical_id, raw = read_dongle_port(port)
            if failed == 0 and raw and len(raw) == 13:
                b = struct.unpack(">fffB", raw)
                packet = Packet(
                    pitch=b[0] * RAD2DEG,
                    yaw=b[1] * RAD2DEG,
                    roll=b[2] * RAD2DEG,
                    battery=b[3],
                    t=now,
                    name=port.wl_mp[logical_id],
                )
                queue.append(packet)
                i += 1
        return i

    def __exit__(self, exctype, excinst, exctb):
        for port, logical_ids in zip(self.ports, self.logical_ids):
            stop_dongle_streaming(port, logical_ids)


def start_dongle_streaming(
    port: serial.Serial, logical_ids: List[int], interval_us: int
):

    for logical_id in logical_ids:
        # set streaming slots
        write_dongle_port(
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


def stop_dongle_streaming(port: serial.Serial, logical_ids):
    for logical_id in logical_ids:
        write_dongle_port(port, Cmds.stopStreaming(), logical_id=logical_id)
    for _ in logical_ids:
        read_dongle_port(port)
