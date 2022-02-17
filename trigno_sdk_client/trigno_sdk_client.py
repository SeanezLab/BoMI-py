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

from typing import List, Optional
from dataclasses import dataclass
import socket
import select


COMMAND_PORT = 50040  # receives control commands, sends replies to commands
EMG_DATA_PORT = 50043  # sends EMG and primary non-EMG data
AUX_DATA_PORT = 50044  # sends auxiliary data

IP_ADDR = "10.229.96.239"


def _print(*args, **kwargs):
    print("[Delsys]", *args, **kwargs)


def recv(sock: socket.socket) -> bytes:
    ready = select.select([sock], [], [], 1)
    if ready[0]:
        buf = sock.recv(1024)
        return buf.strip()
    return b"No response"


@dataclass
class Channel:
    "A channel on a given sensor"
    gain: float  # gain
    samples: int  # native samples per frame
    rate: float  # native sample rate in Hz
    units: str  # unit of the data


@dataclass
class DSSensor:
    "A Delsys EMG Sensor"
    type: str
    serial: str
    firmware: str
    emg_channels: int
    aux_channels: int

    start_idx: int
    channel_count: int
    channels: List[Channel]


class DelsysClient:
    """
    DelsysClient interfaces with the Delsys SDK server via its TCP sockets.
    Handles device management and data streaming
    """
    def __init__(self, host_ip: str = IP_ADDR):
        self.command_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.command_sock.connect((host_ip, COMMAND_PORT))
        self.command_sock.setblocking(False)

        self.emg_data_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.emg_data_sock.connect((host_ip, EMG_DATA_PORT))
        self.emg_data_sock.setblocking(False)

        self.sensors: List[Optional[DSSensor]] = [None] * 17  # use 1 indexing

        buf = recv(self.command_sock)
        _print(buf.decode())

        self.setup()
        self.query_devices()

    @property
    def n_sensors(self) -> int:
        return sum([1 for s in self.sensors if s])

    def __repr__(self):
        return f"<DelsysClient n_sensors={self.n_sensors}>"

    def setup(self):
        "Called once during init to setup base station"
        # make sure data format is little endian
        resp = self.send_cmd("ENDIAN LITTLE")
        assert resp == b"OK"

    def query_device(self, i: int):
        "Checks for devices connected to the base and updates `self.sensors`"
        resp = self.send_cmd(f"SENSOR {i} PAIRED?")
        if resp == b"NO":
            return

        cmd = lambda _cmd: self.send_cmd(_cmd).decode()

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
                Channel(
                    gain=float(cmd(f"SENSOR {i} CHANNEL {j} GAIN?")),
                    samples=int(cmd(f"SENSOR {i} CHANNEL {j} SAMPLES?")),
                    rate=float(cmd(f"SENSOR {i} CHANNEL {j} RATE?")),
                    units=cmd(f"SENSOR {i} CHANNEL {j} UNITS?"),
                )
            )

        return DSSensor(
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
        # query all 16 devices
        for i in range(1, 17):
            self.sensors[i] = self.query_device(i)

    def send_cmd(self, cmd: str) -> bytes:
        self.command_sock.send(cmd.encode() + b"\r\n\r\n")
        return recv(self.command_sock)

    def send_cmds(self, cmds: List[str]) -> List[bytes]:
        for cmd in cmds:
            self.command_sock.send(cmd.encode() + b"\r\n")
        self.command_sock.send(b"\r\n")
        return [recv(self.command_sock) for _ in cmds]

    def start_stream(self):
        self.send_cmd("START")
        resp = recv(self.command_sock)
        assert resp == b"OK"

    def recv(self):
        buf = recv(self.emg_data_sock)
        return buf

    def close(self):
        self.send_cmd("QUIT")
        self.command_sock.close()
        self.emg_data_sock.close()

    def __del__(self):
        self.close()


if __name__ == "__main__":
    ds = DelsysClient()

    # ds.start_stream()
    # print("Started successfully")
    # for i in range(10):
    #     buf = ds.recv()
    #     print(i, "received", buf)
