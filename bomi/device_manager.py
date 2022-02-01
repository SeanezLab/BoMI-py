import struct
import math
import threading
import time
from pathlib import Path
from queue import Queue
from timeit import default_timer
from typing import Dict, Final, List, Optional, Tuple

import serial
import threespace_api as ts_api
from serial.serialutil import SerialException

from bomi.datastructure import Packet
from bomi.yost_serial_comm import (
    read_dongle_port,
    start_dongle_streaming,
    stop_dongle_streaming,
)


def _print(*args):
    print("[Yost Device Manager]", *args)


HEX: Final = "{0:08X}"
RAD2DEG: Final = 180 / math.pi

get_time = default_timer
DeviceT = ts_api.TSDongle | ts_api._TSSensor
DeviceList = List[DeviceT]
DongleList = List[ts_api.TSDongle]
SensorList = List[ts_api._TSSensor]


def discover_all_devices() -> Tuple[DeviceList, SensorList, SensorList, SensorList]:
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
        device: ts_api._TSSensor | ts_api.TSDongle = None

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
                for i in range(4):  # check logical indexes of dongle for WL device
                    sens = device[i]
                    if sens is not None:
                        wireless_sensors.append(sens)
                        all_sensors.append(sens)

    return dongles, all_sensors, wired_sensors, wireless_sensors


class YostDeviceManager:
    """
    Manage the discovery, initialization, and data acquisition of all yost body sensors.
    Should only be instantiated once and used as a singleton, though this is not enforced.
    """

    def __init__(self, data_dir: str | Path = "data"):
        self.dongles: DongleList = []
        self.all_sensors: SensorList = []
        self.wired_sensors: SensorList = []
        self.wireless_sensors: SensorList = []

        self._streaming: bool = False
        self._data_dir: Path = Path(data_dir)
        self._thread: Optional[threading.Thread] = None

        # Mapping[serial_number_hex, nickname]. Nickname defaults to serial_number_hex
        self._names: Dict[str, str] = {}

    def __del__(self):
        self.stop_stream()

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
        for dev in dongles + all_sensors:
            if not dev.serial_number_hex in self._names:
                self._names[dev.serial_number_hex] = dev.serial_number_hex

        _print(self.status())

        # Disable all compass (magnetometer) - not accurate
        for sensor in self.all_sensors:
            sensor.setCompassEnabled(False)
        self.tare_all_devices()

    def get_all_sensor_serial(self) -> List[str]:
        "Get serial_number_hex of all sensors"
        return [s.serial_number_hex for s in self.all_sensors]

    def get_all_sensor_names(self) -> List[str]:
        "Get nickname of all sensors"
        return [self._names[s.serial_number_hex] for s in self.all_sensors]

    def get_device_name(self, serial_number_hex: str) -> str | None:
        "Get the nickname of a device"
        return self._names.get(serial_number_hex)

    def set_device_name(self, serial_number_hex: str, name: str):
        "Set the nickname of a device"
        _print(f"{serial_number_hex} nicknamed {name}")
        self._names[serial_number_hex] = name

    def start_stream(self, queue: Queue, fname: Optional[str] = None):
        if not self.has_sensors():
            _print("No sensors found. Aborting stream")
            return

        _print("Setting up stream")

        ### We use the threespace_api to setup/read/stop streaming for wired sensors
        ### For wireless sensors + dongles, we communicate with the dongle serial port directly

        ### Setup streaming for wireless sensors
        # As a workaround, destroy the TSDongle objects and create our own serial port
        # In the end of the streaming loop, recreate the TSDongle object by rediscovering devices
        port_names: List[str] = []
        ports: List[serial.Serial] = []
        wl_ids = [s.serial_number for s in self.wireless_sensors]  # List[serial_number]

        while self.dongles:
            dongle = self.dongles.pop()
            wl_mp: Dict[int, str] = {}  # Dict[logical_id, device_name]
            for wl_id in wl_ids:
                if wl_id in dongle.wireless_table:
                    idx = dongle.wireless_table.index(wl_id)
                    wl_mp[idx] = self.get_device_name(HEX.format(wl_id))

            port_name = dongle.serial_port.name
            port_names.append(port_name)
            self.close_device(dongle)
            del dongle
            port = serial.Serial(port_name, 115200, timeout=1)
            port.wl_mp = wl_mp
            ports.append(port)

            logical_ids = list(wl_mp.keys())
            # Check the source to see which slots are setup
            start_dongle_streaming(port, logical_ids)

        ### Setup streaming for wired sensors
        broadcaster = ts_api.global_broadcaster
        broadcaster.setStreamingTiming(
            interval=0,  # output data as quickly as possible
            duration=0xFFFFFFFF,  # run indefinitely until stop command is issued
            delay=1_000_000,  # session starts after 1s delay
            delay_offset=0,  # delay between devices
            filter=self.wired_sensors,
        )
        broadcaster.setStreamingSlots(
            slot0="getTaredOrientationAsEulerAngles",
            slot1="getBatteryPercentRemaining",
            filter=self.wired_sensors,
        )
        broadcaster.startStreaming(filter=self.wired_sensors)

        _print("Start streaming")

        # Orientation in Euler angles given in (pitch, yaw, roll)

        def handle_stream():
            """
            Handle reading batch data from sensors and putting them into the queue
            Should execute in a new thread
            """
            i = 0
            start_time = default_timer()

            try:
                while self._streaming:
                    now = default_timer()

                    # read streaming batch from wired sensors
                    for sensor in self.wired_sensors:
                        b = sensor.getStreamingBatch()
                        packet = Packet(
                            pitch=b[0] * RAD2DEG,
                            yaw=b[1] * RAD2DEG,
                            roll=b[2] * RAD2DEG,
                            battery=b[3],
                            t=now,
                            name=self._names[sensor.serial_number_hex],
                        )
                        queue.put(packet)
                        i += 1

                    # read streaming batch from wireless sensors through
                    # a dongle's serial port
                    for port in ports:
                        failed, logical_id, raw = read_dongle_port(port)
                        if failed == 0 and len(raw) == 13:
                            b = struct.unpack(">fffB", raw)
                            packet = Packet(
                                pitch=b[0] * RAD2DEG,
                                yaw=b[1] * RAD2DEG,
                                roll=b[2] * RAD2DEG,
                                battery=b[3],
                                t=now,
                                name=port.wl_mp[logical_id],
                            )
                            queue.put(packet)
                            i += 1

                    if i % 2000 == 0:
                        fps = i / (now - start_time)
                        start_time, i = now, 0
                        _print(f"Throughput: {fps:.2f} packets/sec")
            except Exception as e:
                _print("[Streaming loop exception]", e)
            except KeyboardInterrupt as e:
                pass
            finally:
                _print("Streaming loop ended")
                # stop wired sensor streaming
                ts_api.global_broadcaster.stopStreaming(filter=self.wired_sensors)

                # stop dongle streaming
                for port in ports:
                    stop_dongle_streaming(port, logical_ids)
                    port.close()
                    del port

                time.sleep(0.5)
                self.discover_devices()

        self._streaming = True
        self._thread = threading.Thread(target=handle_stream)
        self._thread.start()

    def stop_stream(self):
        _print("Stopping stream")
        if self._thread and self._streaming:
            self._streaming = False
            self._thread.join()
            self._thread = None
        _print("Stream stopped")

    def tare_all_devices(self):
        for dev in self.all_sensors:
            success = dev.tareWithCurrentOrientation()
            _print(dev.serial_number_hex, "Tared:", success)

    def get_battery(self) -> List[int]:
        b = [d.getBatteryPercentRemaining() for d in self.all_sensors]
        return b

    def has_sensors(self) -> bool:
        return len(self.all_sensors) > 0

    def close_device(self, device):
        device.close()

        def rm_from_lst(l: list):
            if device in l:
                l.remove(device)

        rm_from_lst(self.dongles)
        rm_from_lst(self.all_sensors)
        rm_from_lst(self.wired_sensors)
        rm_from_lst(self.wireless_sensors)

        def rm_from_dict(d):
            if device.serial_number in d:
                del d[device.serial_number]

        rm_from_dict(ts_api.global_sensorlist)
        rm_from_dict(ts_api.global_donglist)

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
        self.close_all_devices()


if __name__ == "__main__":
    dm = YostDeviceManager()
