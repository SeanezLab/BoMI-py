"""
To use the SDK 

Connect to the Trigno SDK Server via TCP/IP
• Configure the Trigno system hardware (see Section 5)
• Start data acquisition using one of two methods:
    o Send the command “START” over the Command port
    o Arm the system and send a start trigger to the Trigno Base Station (see the Trigno Wireless EMG System User Guide)
• Process the data streams that are being sent over the data ports (see Section 6

All data values are IEEE floats (4 bytes). For synchronization purposes, always process
bytes in segments determined by multiples of the following factor
    (No. of data channels on port) * (4 bytes/sample)

6.2 Packet Structure

Each command is terminated with <CR><LF>. The end of a command packet is terminated by
two consecutive <CR><LF> pairs, and the server will process app commands received
to this point when two <CR><LF> are received

"""

import traceback
from typing import Deque, Dict, Tuple, List, Optional
from pathlib import Path
from dataclasses import dataclass, asdict
import threading
import json
import struct
import socket

from pprint import pprint

from bomi.base_widgets import T

COMMAND_PORT = 50040  # receives control commands, sends replies to commands
EMG_DATA_PORT = 50043  # sends EMG and primary non-EMG data
AUX_DATA_PORT = 50044  # sends auxiliary data

IP_ADDR = "10.229.96.239"


def _print(*args, **kwargs):
    print("[TrignoSDK]", *args, **kwargs)


def recv(sock: socket.socket, maxlen=1024) -> bytes:
    buf = sock.recv(maxlen)
    return buf.strip()


@dataclass
class DSChannel:
    "A channel on a given sensor"
    gain: float  # gain
    samples: int  # native samples per frame
    rate: float  # native sample rate in Hz
    units: str  # unit of the data


@dataclass
class EMGSensor:
    """Delsys EMG Sensor properties queried from the Base Station"""

    type: str
    serial: str
    firmware: str
    emg_channels: int
    aux_channels: int

    start_idx: int
    channel_count: int
    channels: List[DSChannel]


@dataclass
class EMGSensorMeta:
    """Metadata associated with a EMG sensor
    Most importantly sensor placement
    """

    muscle_name: str = ""
    side: str = ""


class TrignoClient:
    """
    DelsysClient interfaces with the Delsys SDK server via its TCP sockets.
    Handles device management and data streaming
    """

    def __init__(self, host_ip: str = IP_ADDR):
        self.connected = False
        self.host_ip = host_ip

        self.command_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.emg_data_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

        self.sensors: List[Optional[EMGSensor]] = [None] * 17  # use 1 indexing
        self.sensor_idx: List[int] = []
        self.n_sensors = 0

        self.sensor_meta: Dict[str, EMGSensorMeta] = {}  # Mapping[serial, meta]

        self.streaming: bool = False
        self.worker_thread: threading.Thread | None = None

    def __call__(self, cmd: str):
        return self.send_cmd(cmd)

    def __repr__(self):
        return f"<DelsysClient n_sensors={self.n_sensors}>"

    def __getitem__(self, idx: int):
        return self.sensors[idx]

    def __len__(self) -> int:
        return 0

    def connect(self) -> bool:
        """Called once during init to setup base station.
        Returns True if connection successful
        """
        if self.connected:
            return True

        try:
            self.command_sock.settimeout(1)
            self.command_sock.connect((self.host_ip, COMMAND_PORT))
            self.command_sock.settimeout(3)
            buf = recv(self.command_sock)
            _print(buf.decode())
            self.emg_data_sock.connect((self.host_ip, EMG_DATA_PORT))
            self.connected = True
        except TimeoutError as e:
            _print("Failed to connect to Base Station", e)
            return False

        cmd = lambda _cmd: self.send_cmd(_cmd).decode()
        assert cmd("ENDIAN LITTLE"), "OK"  # Use little endian

        ### Queries
        self.backwards_compatibility = cmd("BACKWARDS COMPATIBILITY?")
        self.upsampling = cmd("UPSAMPLING?")

        # Trigno System frame interval, which is the length in time between frames
        self.frame_interval = float(cmd("FRAME INTERVAL?"))
        # expected maximum samples per frame for EMG channels. Divide by the frame interval to get expected EMG sample rate
        self.max_samples_emg = float(cmd("MAX SAMPLES EMG?"))
        self.emg_sample_rate = self.max_samples_emg / self.frame_interval

        # expected maximum samples per frame for AUX channels. Divide by the frame interval to get the expected AUX samples rate
        self.max_samples_aux = float(cmd("MAX SAMPLES AUX?"))
        self.aux_sample_rate = self.max_samples_aux / self.frame_interval

        self.endianness = cmd("ENDIANNESS?")
        # firmware version of the connected base station
        self.base_firmware = cmd("BASE FIRMWARE?")
        # firmware version of the connected base station
        self.base_serial = cmd("BASE SERIAL?")

        self.query_devices()
        return True

    def query_device(self, i: int):
        "Checks for devices connected to the base and updates `self.sensors`"
        assert self.connected

        cmd = lambda _cmd: self.send_cmd(_cmd).decode()

        ## Only look at PAIRED and ACTIVE sensors
        if cmd(f"SENSOR {i} PAIRED?") == "NO":
            return

        if cmd(f"SENSOR {i} ACTIVE?") == "NO":
            return

        _type = cmd(f"SENSOR {i} TYPE?")
        _serial = cmd(f"SENSOR {i} SERIAL?")
        firmware = cmd(f"SENSOR {i} FIRMWARE?")
        emg_channels = int(cmd(f"SENSOR {i} EMGCHANNELCOUNT?"))
        aux_channels = int(cmd(f"SENSOR {i} AUXCHANNELCOUNT?"))
        start_idx = int(cmd(f"SENSOR {i} STARTINDEX?"))

        channel_count = int(cmd(f"SENSOR {i} CHANNELCOUNT?"))
        channels = []
        for j in range(1, channel_count + 1):
            channels.append(
                DSChannel(
                    gain=float(cmd(f"SENSOR {i} CHANNEL {j} GAIN?")),
                    samples=int(cmd(f"SENSOR {i} CHANNEL {j} SAMPLES?")),
                    rate=float(cmd(f"SENSOR {i} CHANNEL {j} RATE?")),
                    units=cmd(f"SENSOR {i} CHANNEL {j} UNITS?"),
                )
            )

        return EMGSensor(
            type=_type,
            serial=_serial,
            firmware=firmware,
            emg_channels=emg_channels,
            aux_channels=aux_channels,
            start_idx=start_idx,
            channel_count=channel_count,
            channels=channels,
        )

    def query_devices(self):
        """Query the Base Station for all 16 devices"""
        assert self.connected

        for i in range(1, 17):
            self.sensors[i] = self.query_device(i)

        self.sensor_idx = [i for i, s in enumerate(self.sensors) if s]
        self.n_sensors = sum([1 for s in self.sensors if s])

    def send_cmd(self, cmd: str) -> bytes:
        self.command_sock.send(cmd.encode() + b"\r\n\r\n")
        return recv(self.command_sock)

    def send_cmds(self, cmds: List[str]) -> List[bytes]:
        for cmd in cmds:
            self.command_sock.send(cmd.encode() + b"\r\n")
        self.command_sock.send(b"\r\n")
        return [recv(self.command_sock) for _ in cmds]

    def start_stream(self):
        assert self.connected
        self.send_cmd("START")
        self.streaming = True

    def stop_stream(self):
        self.streaming = False
        self.worker_thread and self.worker_thread.join()
        if self.connected:
            self.send_cmd("STOP")

    def recv_emg(self):
        BYTES_PER = 4 * 16  # 16 devices, 4 byte float
        buf = recv(self.emg_data_sock, BYTES_PER)
        emgs = struct.unpack("<ffffffffffffffff", buf)
        return emgs

    def handle_stream(self, queue: Deque[Tuple[float]]):
        assert self.connected
        self.start_stream()
        self.worker_thread = threading.Thread(target=self.stream_worker, args=(queue,))
        self.worker_thread.start()

    def stream_worker(self, queue: Deque[Tuple[float]]):
        while self.streaming:
            queue.append(self.recv_emg())

    def close(self):
        self.stop_stream()
        if self.connected:
            self.send_cmd("QUIT")
        self.command_sock.close()
        self.emg_data_sock.close()
        self.sensor_idx = []
        self.sensors = []

    def save_meta(self, fpath: Path):
        """Save metadata as JSON to fpath"""
        tmp = {k: asdict(v) for k, v in self.sensor_meta.items()}
        with open(fpath, "w") as fp:
            json.dump(tmp, fp, indent=2)

    def load_meta(self, fpath: Path):
        """Load JSON metadata from fpath"""
        with open(fpath, "r") as fp:
            tmp: Dict = json.load(fp)

        for k, v in tmp.items():
            self.sensor_meta[k] = EMGSensorMeta(**v)

    def __del__(self):
        self.close()


if __name__ == "__main__":
    dm = TrignoClient()
    print(dm)
    breakpoint()

    dm.start_stream()
    while True:
        buf = dm.recv_emg()
        if any(buf):
            print(buf)
