from typing import List, NamedTuple, Optional, Tuple
from queue import Queue
from timeit import default_timer
import struct
import threading
from serial.serialutil import SerialException
import serial

import threespace_api as ts_api
from bomi.yost_serial_comm import (
    read_dongle_port,
    start_dongle_streaming,
    stop_dongle_streaming,
)

get_time = default_timer
DeviceT = ts_api.TSDongle | ts_api._TSSensor
DeviceList = List[DeviceT]
DongleList = List[ts_api.TSDongle]
SensorList = List[ts_api._TSSensor]


def _print(*args):
    print("[Device Manager]", *args)


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
            if device_type != "DNG":
                all_sensors.append(device)
                wired_sensors.append(device)
            else:
                dongles.append(device)
                for i in range(4):  # check logical indexes of dongle for WL device
                    sens = device[i]
                    if sens is not None:
                        all_sensors.append(sens)
                        wireless_sensors.append(sens)

    return dongles, all_sensors, wired_sensors, wireless_sensors


class Packet(NamedTuple):
    roll: float
    pitch: float
    yaw: float
    battery: int
    t: float  # time
    name: str  # device name


class DeviceManager:
    """
    Manage the discovery, initialization, and data acquisition of all yost body sensors.
    Should only be instantiated once and used as a singleton, though this is not enforced.
    """

    def __init__(self):
        self.dongles: DongleList = []
        self.all_sensors: SensorList = []
        self.wired_sensors: SensorList = []
        self.wireless_sensors: SensorList = []

        self._streaming: bool = False
        self._save_file: Optional[str] = None

    def __del__(self):
        self.stop_stream()

    def status(self) -> str:
        return (
            f"Discovered {len(self.dongles)} dongles, {len(self.all_sensors)} sensors"
        )

    def discover_devices(self):
        "Walk COM ports to discover Yost devices"
        self.close_devices()

        dongles, all_sensors, wired_sensors, wireless_sensors = discover_all_devices()
        self.dongles = dongles
        self.all_sensors = all_sensors
        self.wired_sensors = wired_sensors
        self.wireless_sensors = wireless_sensors

        _print(self.status())

    def start_stream(self, queue: Queue, save_file: Optional[str] = None):
        if len(self.all_sensors) == 0:
            return
        _print("Setting up stream")
        self._queue = queue

        ### We use the threespace_api to setup/read/stop streaming for wired sensors
        ### For wireless sensors + dongles, we communicate with the dongle serial port directly

        ### Setup streaming for wireless sensors
        # As a workaround, destroy the TSDongle objects and create our own serial port
        # In the end of the streaming loop, recreate the TSDongle object
        def recreate_dongle_obj(port_name: str):
            dongle = ts_api.TSDongle(com_port=port_name)
            self.dongles.append(dongle)

        port_names = []
        ports = []
        wl_ids = [s.serial_number for s in self.wireless_sensors]
        for dongle in self.dongles:
            wl_mp = {}
            for wl_id in wl_ids:
                if wl_id in dongle.wireless_table:
                    idx = dongle.wireless_table.index(wl_id)
                    wl_mp[idx] = wl_id

            port_name = dongle.serial_port.name
            port_names.append(port_name)
            self.close_device(dongle)
            del dongle
            port = serial.Serial(port_name, 115200, timeout=1)
            port.wl_mp = wl_mp
            ports.append(port)

            logical_ids = list(wl_mp.keys())
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

        def handle_stream():
            # args = (True,)
            i = 0
            start_time = default_timer()

            try:
                while self._streaming:
                    res = []
                    now = default_timer()

                    for sensor in self.wired_sensors:
                        b = sensor.getStreamingBatch()
                        packet = Packet(
                            roll=b[0],
                            pitch=b[1],
                            yaw=b[2],
                            battery=b[3],
                            t=now,
                            name=sensor.serial_number_hex,
                        )
                        res.append(packet)

                    for port in ports:
                        failed, logical_id, raw = read_dongle_port(port)
                        if failed == 0 and len(raw) == 13:
                            b = struct.unpack(">fffB", raw)
                            packet = Packet(
                                roll=b[0],
                                pitch=b[1],
                                yaw=b[2],
                                battery=b[3],
                                t=now,
                                name=hex(port.wl_mp[logical_id]),
                            )
                            res.append(packet)

                    if res:
                        queue.put(res)
                        i += len(res)
                        if i % 1000 == 0:
                            fps = i / (now - start_time)
                            start_time, i = now, 0
                            _print("Data rate:", fps)
            except Exception as e:
                _print("[Streaming loop exception]", e)
            finally:
                _print("Streaming loop ended")
                # stop wired sensor streaming
                ts_api.global_broadcaster.stopStreaming(filter=self.wired_sensors)

                # stop dongle streaming
                stop_dongle_streaming(port, logical_ids)
                [port.close() for port in ports]

                # recreate dongles
                [recreate_dongle_obj(name) for name in port_names]

        self._thread = threading.Thread(target=handle_stream)
        self._streaming = True
        self._thread.start()

    def stop_stream(self):
        _print("Stopping stream")
        if self._streaming:
            self._streaming = False
            self._thread.join(timeout=1)
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
            if device in d:
                del d[device]

        rm_from_dict(ts_api.global_sensorlist)
        rm_from_dict(ts_api.global_donglist)

    def close_devices(self):
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
        self.close_devices()


if __name__ == "__main__":
    dm = DeviceManager()
