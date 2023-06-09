from __future__ import annotations
from pathlib import Path
from queue import Queue
from serial import SerialException
from timeit import default_timer
from typing import Dict, Final, List, Optional, Tuple
import math
import threading
import time

import threespace_api as ts_api
from bomi.datastructure import Packet
from bomi.device_managers.yost_serial_comm import (
    Dongles,
    WiredSensors,
    PacketField
)
from bomi.device_managers.protocols import (
    SupportsStreaming,
    SupportsHasSensors,
    SupportsGetSensorMetadata,
    HasChannelLabels
)

from PySide6.QtCore import Signal, QObject


def _print(*args):
    print("[Yost Device Manager]", *args)


HEX: Final = "{0:08X}"
RAD2DEG: Final = 180 / math.pi

DeviceT = ts_api.TSDongle | ts_api._TSSensor
DongleList = List[ts_api.TSDongle]
SensorList = List[ts_api._TSSensor]


def discover_all_devices() -> Tuple[DongleList, SensorList, SensorList, SensorList]:
    """
    Discover all Yost sensors and dongles by checking all COM ports.

    Returns
    -------
    all_list: List of all devices (sensors + dongles)
    sensor_list: List of all sensors (all wired + wireless sensors)
    """
    ports = ts_api.getComPorts()

    dongles: DongleList = []
    all_sensors: SensorList = []
    wired_sensors: SensorList = []
    wireless_sensors: SensorList = []

    for device_port in ports:
        com_port, _, device_type = device_port
        device = None

        try:
            if device_type == "USB":
                device = ts_api.TSUSBSensor(com_port=com_port)
            elif device_type == "DNG":
                device = ts_api.TSDongle(com_port=com_port)
            elif device_type == "WL":
                device = ts_api.TSWLSensor(com_port=com_port)
            elif device_type == "EM":
                device = ts_api.TSEMSensor(com_port=com_port)
            elif device_type == "DL":
                device = ts_api.TSDLSensor(com_port=com_port)
            elif device_type == "BT" or device_type == "MBT":
                device = ts_api.TSBTSensor(com_port=com_port)
            elif device_type == "LX":
                device = ts_api.TSLXSensor(com_port=com_port)
            elif device_type == "NANO":
                device = ts_api.TSNANOSensor(com_port=com_port)

        except SerialException as e:
            print("[WARNING]", e)

        if device is not None:
            if not isinstance(device, ts_api.TSDongle):
                # if device_type != "DNG":
                wired_sensors.append(device)
                all_sensors.append(device)
            else:
                dongles.append(device)
                for i in range(15):  # check logical indexes of dongle for WL device
                    sens = device[i]
                    if sens is not None:
                        wireless_sensors.append(sens)
                        all_sensors.append(sens)

    return dongles, all_sensors, wired_sensors, wireless_sensors


class YostDeviceManager(QObject):
    """
    Manage the discovery, initialization, and data acquisition of all yost body sensors.
    Should only be instantiated once and used as a singleton, though this is not enforced.
    """
    discover_devices_signal = Signal()

    CHANNEL_LABELS = [
        PacketField.ROLL,
        PacketField.PITCH,
        PacketField.YAW,
    ]

    def __init__(self, data_dir: str | Path = "data", sampling_frequency: float = 100):
        super().__init__()
        self._data_dir: Path = Path(data_dir)
        self._fs = sampling_frequency

        self.dongles: DongleList = []
        self.all_sensors: SensorList = []
        self.wired_sensors: SensorList = []
        self.wireless_sensors: SensorList = []

        self._done_streaming = threading.Event()
        self._thread: Optional[threading.Thread] = None

        # Mapping[serial_number_hex, nickname]. Nickname defaults to serial_number_hex
        self._names: Dict[str, str] = {}

    def status(self) -> str:
        return (
            f"Discovered {len(self.dongles)} dongles, {len(self.all_sensors)} sensors"
        )

    def discover_devices(self):
        "Walk COM ports to discover Yost devices"
        self.close_all_devices()

        dongles, all_sensors, wired_sensors, wireless_sensors = discover_all_devices()
        self.dongles = dongles
        self.all_sensors = all_sensors
        self.wired_sensors = wired_sensors
        self.wireless_sensors = wireless_sensors
        for dev in (*dongles, *all_sensors):
            if dev.serial_number_hex not in self._names:
                self._names[dev.serial_number_hex] = dev.serial_number_hex

        _print(self.status())

        # Disable all compass (magnetometer) - not accurate
        for sensor in self.all_sensors:
            sensor.setCompassEnabled(False)
        self.tare_all_devices()

        self.discover_devices_signal.emit()

    def get_all_sensor_serial(self) -> List[str]:
        "Get serial_number_hex of all sensors"
        return [s.serial_number_hex for s in self.all_sensors]

    def get_all_sensor_names(self) -> List[str]:
        "Get nickname of all sensors"
        return [self._names[s.serial_number_hex] for s in self.all_sensors]

    def get_device_name(self, serial_number_hex: str) -> str:
        "Get the nickname of a device"
        return self._names.get(serial_number_hex, "")

    def set_device_name(self, serial_number_hex: str, name: str):
        "Set the nickname of a device"
        _print(f"{serial_number_hex} nicknamed {name}")
        self._names[serial_number_hex] = name

    def start_stream(self, queue: Queue[Packet]):
        if not self.has_sensors():
            _print("No sensors found. Aborting stream")
            return

        ### We use the threespace_api to setup/read/stop streaming for wired sensors
        ### For wireless sensors + dongles, we communicate with the dongle serial port directly
        ### Setup streaming for wireless sensors
        # As a workaround, destroy the TSDongle objects and create our own serial port
        # In the end of the streaming loop, recreate the TSDongle object by rediscovering devices
        wl_ids: List[int] = [s.serial_number for s in self.wireless_sensors]  # type: ignore

        dongle_port_names: List[str] = []  # port name, e.g. "COM3"
        wl_mps: List[Dict[int, str]] = []  # mapping from logical ID to device name

        while self.dongles:
            dongle = self.dongles.pop()
            wl_mp: Dict[int, str] = {}  # Dict[logical_id, device_name]
            for wl_id in wl_ids:
                if wl_id in dongle.wireless_table:
                    idx = dongle.wireless_table.index(wl_id)
                    wl_mp[idx] = self.get_device_name(HEX.format(wl_id))

            port_name: str = dongle.port_name  # type: ignore
            self.close_device(dongle)
            del dongle

            dongle_port_names.append(port_name)
            wl_mps.append(wl_mp)

        sensor_port_names: List[str] = []
        sensor_names: List[str] = []
        while self.wired_sensors:
            sensor = self.wired_sensors.pop()
            port_name: str = sensor.port_name  # type: ignore
            name: str = self._names[sensor.serial_number_hex]
            self.close_device(sensor)
            del sensor

            sensor_port_names.append(port_name)
            sensor_names.append(name)

        _print("Start streaming")
        self._done_streaming.clear()
        self._thread = threading.Thread(
            target=_handle_stream,
            args=(
                queue,
                self._done_streaming,
                self._fs,
                sensor_port_names,
                sensor_names,
                dongle_port_names,
                wl_mps,
            ),
        )
        self._thread.start()

    def stop_stream(self):
        if self._thread and not self._done_streaming.is_set():
            _print("Stopping stream")
            self._done_streaming.set()
            self._thread.join()
            self._thread = None
            self.discover_devices()
            _print("Stream stopped")

    def tare_all_devices(self):
        for dev in self.all_sensors:
            success = dev.tareWithCurrentOrientation()
            _print(dev.serial_number_hex, "Tared:", success)

    def has_sensors(self) -> bool:
        return len(self.all_sensors) > 0

    def close_device(self, device):
        device.close()

        for devices_list in [self.dongles, self.all_sensors, self.wired_sensors, self.wireless_sensors]:
            if device in devices_list:
                devices_list.remove(device)

        for devices_dict in [ts_api.global_sensorlist, ts_api.global_donglist]:
            if device.serial_number in devices_dict:
                del devices_dict[device.serial_number]

    def close_all_devices(self):
        "close all ports"
        for device in self.all_sensors:
            device.close()
        for device in self.dongles:
            device.close()
        self.dongles = []
        self.wired_sensors = []
        self.wireless_sensors = []
        self.all_sensors = []
        ts_api.global_donglist = {}
        ts_api.global_sensorlist = {}

    def __del__(self):
        self.stop_stream()
        self.close_all_devices()


def _handle_stream(
    queue: Queue[Packet],
    done: threading.Event,
    fs: int,
    sensor_port_names: List[str],
    sensor_names: List[str],
    dongle_port_names: List[str],
    wl_mps: List[Dict[int, str]],
):
    """
    Handle reading batch data from sensors and putting them into the queue
    Should execute in a new thread
    """
    fps_packet_counter = 0
    fps_start_time = default_timer()

    interval_us = int(1/fs * 1000)

    with (
        Dongles(dongle_port_names, wl_mps, interval_us=interval_us) as dongles,
        WiredSensors(sensor_port_names, sensor_names, interval_us=interval_us) as sensors,
    ):
        while not done.is_set():
            now = default_timer()

            # Read streaming batch wired sensors
            fps_packet_counter += sensors.recv(queue)

            # Read streaming batch from wireless sensors through Dongle
            fps_packet_counter += dongles.recv(queue)

            # Update FPS
            if fps_packet_counter % 1000 == 0:
                fps = fps_packet_counter / (now - fps_start_time)
                fps_start_time = now
                fps_packet_counter = 0
                _print(f"Throughput: {fps:.2f} packets/sec")

    time.sleep(0.2)


if __name__ == "__main__":
    dm = YostDeviceManager()
