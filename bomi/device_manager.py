from typing import Dict, List, NamedTuple, Optional, Tuple
from queue import Queue
from timeit import default_timer
import threading
from serial.serialutil import SerialException

import threespace_api as ts_api

get_time = default_timer
DeviceT = ts_api.TSDongle | ts_api._TSSensor
DeviceList = List[DeviceT]
SensorList = List[ts_api._TSSensor]


def _print(*args):
    print("[Device Manager]", *args)


def discover_all_devices() -> Tuple[DeviceList, SensorList]:
    """
    Discover all Yost sensors and dongles by checking all COM ports.

    Returns
    -------
    all_list: List of all devices (sensors + dongles)
    sensor_list: List of all sensors (all wired + wireless sensors)
    """
    ports = ts_api.getComPorts()
    all_list: SensorList = []
    sensor_list: SensorList = []
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
            all_list.append(device)
            if device_type != "DNG":
                sensor_list.append(device)
            else:
                for i in range(4):  # check logical indexes of dongle for WL device
                    sens = device[i]
                    if sens is not None:
                        sensor_list.append(sens)

    return all_list, sensor_list


class Packet:
    device_name: str
    timestamp: int
    data: list

    
class Packet(NamedTuple):
    roll: float
    pitch: float
    yaw: float
    t: float

class DeviceManager:
    """
    Manage the discovery, initialization, and data acquisition of all yost body sensors.
    Should only be instantiated once and used as a singleton, though this is not enforced.
    """

    def __init__(self):
        self.all_list: DeviceList = []  # all wired devices (sensors + dongles)
        self.sensor_list: SensorList = [] # all sensors (wired + wireless)
        self._streaming: bool = False
        self._save_file: Optional[str] = None

    def __del__(self):
        self.stop_stream()

    def status(self) -> str:
        n_dongles = sum([1 for d in self.all_list if d.device_type == "DNG"])
        return (
            f"Discovered {n_dongles} dongles, {len(self.sensor_list)} sensors"
        )

    def discover_devices(self):
        "Walk COM ports to discover Yost devices"
        self.close_devices()
        self.all_list, self.sensor_list = discover_all_devices()
        _print(self.status())

    def start_stream(self, queue: Queue, save_file: Optional[str] = None):
        if len(self.sensor_list) == 0:
            return
        _print("Setting up stream")
        self._queue = queue
        sensor_list = self.sensor_list
        [d.broadcastSynchronizationPulse() for d in self.all_list if d.device_type == "DNG"]
        broadcaster = ts_api.global_broadcaster
        broadcaster.setStreamingTiming(
            interval=0,  # output data as quickly as possible
            duration=0xFFFFFFFF,  # run indefinitely until stop command is issued
            delay=1_000_000,  # session starts after 1s delay
            delay_offset=0,  # delay between devices
            filter=sensor_list,
        )
        broadcaster.setStreamingSlots(
            slot0="getTaredOrientationAsEulerAngles",
            filter=sensor_list,
        )

        _print("Start streaming")
        broadcaster.startStreaming(filter=sensor_list)

        def handle_stream():
            args = (True,)
            i = 0
            start_time = default_timer()
            while self._streaming:
                b: Dict[ts_api._TSSensor, list] = broadcaster.broadcastMethod(
                    "getStreamingBatch", args=args
                )
                # returned batch has the type
                # List[Tuple[euler_angles, timestamp]]
                res = [b[s] for s in sensor_list]
                # print([r[1] for r in res])
                queue.put(res)
                i += 1
                if i % 100 == 0:
                    now = default_timer()
                    fps = i / (now - start_time)
                    start_time = now
                    i = 0
                    print("fps", fps)

        self._thread = threading.Thread(target=handle_stream)
        self._streaming = True
        self._thread.start()

    def stop_stream(self):
        _print("Stopping stream")
        if self._streaming:
            self._streaming = False
            ts_api.global_broadcaster.stopStreaming(filter=self.sensor_list)
            self._thread.join(timeout=1)
        _print("Stream stopped")

    def tare_all_devices(self):
        for dev in self.sensor_list:
            success = dev.tareWithCurrentOrientation()
            _print(dev.serial_number_hex, "Tared:", success)

    def get_battery(self) -> List[int]:
        b = [d.getBatteryPercentRemaining() for d in self.sensor_list]
        return b

    def has_sensors(self) -> bool:
        return len(self.sensor_list) > 0

    def close_devices(self):
        "close all ports"
        for device in self.all_list:
            device.close()

    def __del__(self):
        self.close_devices()


if __name__ == "__main__":
    dm = DeviceManager()
