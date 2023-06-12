import multiprocessing
import time
import bomi.device_managers.analog_streaming_client as AS
from bomi.device_managers.protocols import SupportsGetSensorMetadata, SupportsHasSensors, SupportsStreaming
from queue import Queue
from typing import Protocol, Iterable
import threading
from threading import Event

def _print(*args):
    print("[QTM]", *args)

class QtmDeviceManager(SupportsGetSensorMetadata, SupportsHasSensors, SupportsStreaming):
    """
    The wrapper that calls the QTM Client. Responsible for discovering connected channels,
    implementing queue, and starting/stopping the date stream.
    
    """
    def __init__(self):
        self.qtm_streaming = False
        self.all_channels: SensorList = []
        #self.queue = Queue()  #use for debugging with if __name__ == '__main__':
        
        self.dummyQueue = multiprocessing.Queue() #dummy queue because we probably do not need seperate information for frame rate for 100 Hz
            #analog streaming was developed to handle 50000 Hz, needs analog_frame_queue

        self.qtm_ip = '10.229.96.105' #connect to QLineEdit input of Biodex Widget
        self.port = 22223
        self.version = '1.22'

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

    #def start_stream(self): #for debugging with if __name__ == '__main__':
    def start_stream(self, queue: Queue) -> None:
        """
        Start streaming data to the passed in queue
        """
        if not self.has_sensors():
            _print("No sensors found. Aborting stream")
            return

        if self.qtm_streaming == False:
            #self.p1 = threading.Thread(target = AS.real_time_stream, args=(self.queue, self.dummyQueue, self.qtm_ip, self.port, self.version), daemon=True) #cebugging
            self.p1 = threading.Thread(target = AS.real_time_stream, args=(queue, self.dummyQueue, self.qtm_ip, self.port, self.version), daemon=True)
            #self.p1 = multiprocessing.Process(target = AS.real_time_stream, args=(self.QTM_queue, self.dummyQueue, self.qtm_ip, self.port, self.version))
            self.p1.start() #starting the thread
            self.qtm_streaming = True #check for stopping
            #print("Am I alive?", self.p1.is_alive())

    def stop_stream(self) -> None:
        """
        Stop streaming data
        """
        if self.qtm_streaming == True:
            try:
                _print("Stopping stream")
                self.p1.join()
                _print("Am I alive? ", self.p1.is_alive())
                _print("Stream stopped")
            except:
                print("Failed to close QTM client thread")

    def has_sensors(self) -> bool:
        """
        Returns True if the device manager has sensors added, QTM is considerd a sensor.
        If channels exist, you are connect to QTM
        """
        return len(self.all_channels) > 0


# if __name__ == '__main__':
#     """
#     Debugging code to test functionality of qtm manager, send internal queue
#     """
#     elements_to_get = 10

#     qtm = QtmDeviceManager()
#     qtm.discover_devices()
#     print("What devices?", qtm.status())
#     qtm.start_stream()
#     for i in range(elements_to_get):
#         if i < 5:
#             print('i:', i)
#             print(qtm.queue.get())
#         if i == 5:
#            print("Go ahead and stop")
#            qtm.stop_stream()
#            print("Start again after this")
#         if i > 5:
#             qtm.start_stream()
#             print('i:', i)
#             print(qtm.queue.get())
#         if i == 9:
#             print("stop again")
#             qtm.stop_stream()
# print('finished')
