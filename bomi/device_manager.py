from typing import List, Tuple
import time
from serial.serialutil import SerialException

import threespace_api as ts_api

# 1. Import API Module
# 2. Scan for available 3-space hardware
# 3. Construct interface class instances

DeviceList = List[ts_api._TSSensor]


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


class DeviceManager:
    """
    Manage the discovery, initialization, and data acquisition of all yost body sensors.
    """

    def __init__(self):
        self._all_list: DeviceList = []
        self._sensor_list: DeviceList = []

    def discover_devices(self):
        self._close_devices()
        all_list, sensor_list = discover_all_devices()
        print(f"Discovered {len(all_list)} devices, {len(sensor_list)} sensors")
        self._all_list: DeviceList = all_list
        self._sensor_list: DeviceList = sensor_list

    def _setup_devices(self):
        """Setup devices"""
        sensor_list = self._sensor_list
        ts_api.global_broadcaster.setStreamingTiming(
            interval=0,
            duration=110_000_000,
            delay=1_000_000,
            delay_offset=12_000,
            filter=sensor_list,
        )
        ts_api.global_broadcaster.setStreamingSlots(
            slot0="getTaredOrientationAsQuaternion",
            slot1="getAllRawComponentSensorData",
            slot2="getButtonState",
            filter=sensor_list,
        )

        ### Stream data
        ts_api.global_broadcaster.startStreaming(filter=sensor_list)
        ts_api.global_broadcaster.startRecordingData(filter=sensor_list)
        time.sleep(5)
        ts_api.global_broadcaster.stopRecordingData(filter=sensor_list)
        ts_api.global_broadcaster.stopStreaming(filter=sensor_list)
        for sensor in sensor_list:
            sensor.getStreamingBatch
            print(
                "Sensor({0}) stream_data len={1}".format(
                    sensor.serial_number_hex, len(sensor.stream_data)
                )
            )

    def _close_devices(self):
        # close all ports
        for device in self._all_list:
            device.close()

    def __del__(self):
        self._close_devices()


if __name__ == "__main__":
    dm = DeviceManager()
