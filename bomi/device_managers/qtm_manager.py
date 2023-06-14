import multiprocessing
import time
import bomi.device_managers.analog_streaming_client as AS
from bomi.device_managers.protocols import SupportsGetSensorMetadata, SupportsHasSensors, SupportsStreaming, HasDiscoverDevicesSignal, HasChannelLabels, HasInputKind
from queue import Queue
from typing import Protocol, Iterable
import threading
from threading import Event
from PySide6.QtCore import Signal, QObject
from bomi.device_managers.analog_streaming_client import Channel

def _print(*args):
    print("[QTM]", *args)

class QtmDeviceManager(QObject):
    """
    The wrapper that calls the QTM Client. Responsible for discovering connected channels,
    implementing queue, and starting/stopping the date stream.
    
    """
    discover_devices_signal = Signal()

    CHANNEL_LABELS = [
        Channel.TORQUE,
        Channel.VELOCITY,
        Channel.POSITION,
    ]

    INPUT_KIND = "QTM"

    def __init__(self):
        super().__init__()
        self.qtm_streaming = False
        self.all_channels: SensorList = []
        self.queue = Queue()  #use for debugging with if __name__ == '__main__':
        self.qtm_ip = '10.229.96.105' #connect to QLineEdit input of Biodex Widget
        self.port = 22223
        self.version = '1.22'
        self._done_streaming = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def status(self) -> str:
        """
        Check status of discovered QTM channels
        """
        return (
            f"Discovered {len(self.all_channels)} channels"
        )

    def discover_devices(self):
        """
        Sets the QTM application to remote control. Then iterates through each channel and gets
        their ID's.
        """
        try:
            analog_idx = [[x] for x in AS.get_channel_number(self.qtm_ip, self.port, self.version)]
            self.all_channels = analog_idx #channels from QTM connection
            _print(self.status())
            self.discover_devices_signal.emit()
        except:
            # attempt to connect to QTM one more time, the first connection just opens the recording.
            try:
                time.sleep(6)
                analog_idx = [analog_dict[x] for x in AS.get_channel_number(self.qtm_ip, self.port, self.version)]
                self.all_channels = analog_idx #channels from QTM connection
            except:
                print("Error in connecting to QTM")


    def get_all_sensor_names(self) -> Iterable[str]:
        """
        Returns the names of the sensors added to this device manager
        For QTM, returns a list w/ string "QTM" meaning QTM is the sensor
        """
        return ["QTM"]

    def get_all_sensor_serial(self) -> Iterable[str]:
        """
        Returns the hex serials of the sensors added to this device manager
        "QTM does not have multiple sensors, so also return a list w/ string "QTM"
        """  
        return ["QTM"]

    # def start_stream(self): #for debugging with if __name__ == '__main__':
    def start_stream(self, queue: Queue) -> None:
        """
        Start streaming data to the passed in queue
        """
        if not self.has_sensors():
            _print("No sensors found. Aborting stream")
            return

        if self.qtm_streaming == False:
            _print("Start streaming")
            self._done_streaming.clear()
            self._thread = threading.Thread(target = AS.real_time_stream,
                args=(
                    queue,
                    self._done_streaming,
                    self.qtm_ip, self.port, self.version,),
            )
            self._thread.start()


    def stop_stream(self) -> None:
        """
        Stop streaming data
        """
        if self._thread and not self._done_streaming.is_set():
            _print("Stopping stream")
            self._done_streaming.set()
            self._thread.join()
            self._thread = None
            _print("Stream stopped")

    def has_sensors(self) -> bool:
        """
        Returns True if the device manager has sensors added, QTM is considerd a sensor.
        If channels exist, you are connect to QTM
        """
        return len(self.all_channels) > 0


if __name__ == '__main__':
    """
    Debugging code to test functionality of qtm manager, send internal queue
    """
    elements_to_get = 10

    qtm = QtmDeviceManager()
    qtm.discover_devices()
    print("What devices?", qtm.status())
    qtm.start_stream(qtm.queue)
    for i in range(elements_to_get):
        if i < 5:
            print('i:', i)
            print(qtm.queue.get())
        if i == 5:
           print("Go ahead and stop")
           qtm.stop_stream()
           print("Start again after this")
        if i > 5:
            qtm.start_stream(qtm.queue)
            print('i:', i)
            print(qtm.queue.get())
        if i == 9:
            print("stop again")
            qtm.stop_stream()
print('finished')
