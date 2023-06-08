import multiprocessing
import time
import bomi.device_managers.analog_streaming_client as AS

def _print(*args):
    print("[QTM]", *args)

class QtmDeviceManager:
    """
    The wrapper that calls the QTM Client. Responsible for discovering connected channels,
    implementing the multiprocessing queue, and starting/stopping the date stream.
    
    """
    # def __init__(self, data_dir: str | Path = "data", sampling_frequency: float = 100):
    def __init__(self):
        #self._data_dir: Path = Path(data_dir)
        #self._fs = sampling_frequency
        self.qtm_streaming = False

        self.all_channels: SensorList = []
        # create the queue
        self.QTM_queue = multiprocessing.Queue()
        self.analog_frame_queue = multiprocessing.Queue()
        self.qtm_ip = '10.229.96.105' #connect to QLineEdit input of Biodex Widget
        self.port = 22223
        self.version = '1.22'

        # Not sure what analog we'll use for this... look up later
        # self._done_streaming = threading.Event()
        # self._thread: Optional[threading.Thread] = None

        # Mapping[serial_number_hex, nickname]. Nickname defaults to serial_number_hex
        self._names: Dict[str, str] = {}

    #DONE
    def status(self) -> str:
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
            self.all_channels = analog_idx
            _print(self.status())
        except:
            # attempt to connect to QTM one more time, the first connection just opens the recording.
            try:
                time.sleep(6)
                analog_idx = [analog_dict[x] for x in AS.get_channel_number(self.qtm_ip, self.port, self.version)]
            except:
                print("Error in connecting to QTM")

        


    # def get_all_sensor_serial(self) -> List[str]:
    #     "Get serial_number_hex of all sensors"
    #     return [s.serial_number_hex for s in self.all_sensors]

    # def get_all_sensor_names(self) -> List[str]:
    #     "Get nickname of all sensors"
    #     return [self._names[s.serial_number_hex] for s in self.all_sensors]

    # def get_device_name(self, serial_number_hex: str) -> str:
    #     "Get the nickname of a device"
    #     return self._names.get(serial_number_hex, "")

    # def set_device_name(self, serial_number_hex: str, name: str):
    #     "Set the nickname of a device"
    #     _print(f"{serial_number_hex} nicknamed {name}")
    #     self._names[serial_number_hex] = name

    #Checked
    # def start_stream(self, queue: Queue[Packet]):
    #need to pass in multiprocessing queue
    def start_stream(self):
        if not self.has_sensors():
            _print("No sensors found. Aborting stream")
            return

        if self.qtm_streaming == False:
            #print("here")
            self.p1 = multiprocessing.Process(target = AS.real_time_stream, args=(self.QTM_queue,self.analog_frame_queue, self.qtm_ip, self.port, self.version))
            #replacing self.QTM_queue, self.analog_frame_queue
            self.p1.daemon = True
            self.p1.start()
            self.qtm_streaming = True

    # Checked
    def stop_stream(self):
        if self.qtm_streaming == True:
            try:
                _print("Stopping stream")
                self.p1.terminate()
                self.qtm_streaming = False
                _print("Stream stopped")
            except:
                print("Failed to close QTM client thread")

    # Unnecessary?
    # def tare_all_devices(self):
    #     for dev in self.all_sensors:
    #         success = dev.tareWithCurrentOrientation()
    #         _print(dev.serial_number_hex, "Tared:", success)

    # Checked
    def has_sensors(self) -> bool:
        return len(self.all_channels) > 0


    def close_device(self, device):
        self.stop_stream()


        # We don't need this, only implement if necessary downstream
        # device.close()

    
        # def rm_from_lst(l: list):
        #     if device in l:
        #         l.remove(device)

        # rm_from_lst(self.dongles)
        # rm_from_lst(self.all_sensors)
        # rm_from_lst(self.wired_sensors)
        # rm_from_lst(self.wireless_sensors)

        # def rm_from_dict(d):
        #     if device.serial_number in d:
        #         del d[device.serial_number]

        # rm_from_dict(ts_api.global_sensorlist)
        # rm_from_dict(ts_api.global_donglist)


    # Don't need for QTM...
    # def close_all_devices(self):
    #     "close all ports"
    #     for device in self.all_sensors:
    #         device.close()
    #     for device in self.dongles:
    #         device.close()
    #     self.dongles = []
    #     self.wired_sensors = []
    #     self.wireless_sensors = []
    #     self.all_sensors = []
    #     ts_api.global_donglist = {}
    #     ts_api.global_sensorlist = {}

    def __del__(self):
        self.stop_stream()

if __name__ == '__main__':
    """
    Debugging code to test functionality
    """
    elements_to_get = 100

    qtm = QtmDeviceManager()
    qtm.discover_devices()
    qtm.start_stream()
    for i in range(elements_to_get):
        if i < 50:
            print(qtm.QTM_queue.get())
        if i == 50:
            qtm.stop_stream()
        if i == 51:
            qtm.start_stream()
        if i > 51:
            print(qtm.QTM_queue.get())
    print("Finished!")