from email.policy import default
from typing import List, Optional, Tuple
from queue import Queue
from timeit import default_timer
import threading
from serial.serialutil import SerialException

import threespace_api as ts_api

get_time = default_timer
DeviceList = List[ts_api._TSSensor]


def _print(*args):
    print("[Device Manager]", *args)


def discover_all_devices() -> Tuple[DeviceList, DeviceList]:
    """
    Discover all Yost sensors and dongles by checking all COM ports.

    Returns
    -------
    all_list: List of all devices (sensors + dongles)
    sensor_list: List of all sensors (all wired + wireless sensors)
    """
    device_list = ts_api.getComPorts()
    all_list: DeviceList = []
    sensor_list: DeviceList = []
    for device_port in device_list:
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
                for i in range(14):  # check all 14 logical indexes
                    sens = device[i]
                    if sens is not None:
                        sensor_list.append(sens)

    return all_list, sensor_list


class DeviceStatus:
    battery: int


class Packet:
    device_name: str
    timestamp: int
    data: list


class DeviceManager:
    """
    Manage the discovery, initialization, and data acquisition of all yost body sensors.
    """

    def __init__(self):
        self._all_list: DeviceList = []
        self._sensor_list: DeviceList = []
        self._streaming: bool = False
        self._save_file: Optional[str] = None

    def __del__(self):
        self.stop_stream()

    def status(self) -> str:
        return f"Discovered {len(self._all_list)} devices, {len(self._sensor_list)} sensors"

    def discover_devices(self):
        "Walk COM ports to discover Yost devices"
        self._close_devices()
        all_list, sensor_list = discover_all_devices()
        self._all_list = all_list
        self._sensor_list = sensor_list

    def start_stream(self, queue: Queue, save_file: Optional[str] = None):
        if len(self._sensor_list) == 0:
            return
        _print("Setting up stream")
        self._queue = queue
        sensor_list = self._sensor_list
        broadcaster = ts_api.global_broadcaster

        broadcaster.setStreamingTiming(
            interval=0,
            duration=0xFFFFFFFF,
            delay=1_000_000,
            delay_offset=2_000,
            filter=sensor_list,
        )

        broadcaster.setStreamingSlots(
            slot0="getTaredOrientationAsAxisAngle",
            filter=sensor_list,
        )

        # Setup streaming
        sensor_list = self._sensor_list
        broadcaster = ts_api.global_broadcaster
        broadcaster.setStreamingTiming(
            interval=0,
            duration=0xFFFFFFFF,  # run indefinitely
            delay=1_000_000,
            delay_offset=0,
            filter=sensor_list,
        )
        broadcaster.setStreamingSlots(
            slot0="getTaredOrientationAsAxisAngle",
            filter=sensor_list,
        )

        _print("Start streaming")
        broadcaster.startStreaming(filter=sensor_list)
        
        sensor = self._sensor_list[0]
        sensor.getStreamingBatch()

        def handle_stream():
            args = (True,)
            # i = 0
            # n = 100
            # last_time = default_timer()
            while self._streaming:
                b = broadcaster.broadcastMethod("getStreamingBatch", args=args)
                queue.put([b[d] for d in sensor_list])
                # i+= 1
                # if i % n:
                #     t = default_timer()
                #     d = t - last_time
                #     fps = n / d
                #     # _print("fps: ", fps)
                #     last_time = t

        self._thread = threading.Thread(target=handle_stream)
        self._streaming = True
        self._thread.start()

    def stop_stream(self):
        _print("Stopping stream")
        if self._streaming:
            self._streaming = False
            ts_api.global_broadcaster.stopStreaming(filter=self._sensor_list)
            self._thread.join(timeout=1)
        _print("Stream stopped")

    def get_battery(self):
        b = [d.getBatteryPercentRemaining() for d in self._sensor_list]
        return b

    def has_sensors(self) -> bool:
        return len(self._sensor_list) > 0

    def _close_devices(self):
        # close all ports
        for device in self._all_list:
            device.close()

    def __del__(self):
        self._close_devices()


if __name__ == "__main__":
    dm = DeviceManager()
