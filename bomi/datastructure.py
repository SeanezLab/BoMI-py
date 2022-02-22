from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

from timeit import default_timer
from typing import ClassVar, NamedTuple, TextIO, Tuple, List

import numpy as np


class Packet(NamedTuple):
    """Packet represents one streaming batch from one Yost sensor"""

    pitch: float
    yaw: float
    roll: float
    battery: int
    t: float  # time
    name: str  # device nickname


DATA_ROOT = Path.home() / "Documents" / "BoMI Data"
DATA_ROOT.mkdir(exist_ok=True)


def get_savedir(task_name: str) -> Path:
    datestr = datetime.now().strftime("%Y-%m-%d %H-%M-%S-%f")
    savedir = DATA_ROOT / "_".join((datestr, task_name))
    savedir.mkdir()
    return savedir


@dataclass
class Metadata:
    subject_id: str = "unknown"
    joint: str = "unknown"
    max_rom: int = -1

    def dict(self):
        return asdict(self)

    def to_disk(self, savedir: Path):
        "Write metadata to `savedir`"
        with (savedir / "meta.json").open("w") as fp:
            json.dump(asdict(self), fp)


class _Buffer:
    """Managed buffer"""

    LABELS: ClassVar = ("Roll", "Pitch", "Yaw", "abs(roll) + abs(pitch)")
    NAME_TEMPLATE = "sensor_{name}.csv"

    def __init__(self, bufsize: int, savedir: Path, name: str):
        self.bufsize = bufsize
        # 1D array of timestamps
        self.timestamp: np.ndarray = np.zeros(bufsize)
        # 2D array of `labels`
        self.data: np.ndarray = np.zeros((bufsize, len(self.LABELS)))

        fp = open(savedir / self.NAME_TEMPLATE.format(name=name), "w")

        # filepointer to write CSV data to
        self.sensor_fp: TextIO = fp
        # name of this device
        self.name: str = name

        self.savedir: Path = savedir

    def __len__(self):
        return len(self.data)

    def close(self):
        "Close open file pointers"
        self.sensor_fp.close()

    def add_packet(self, *_):
        raise NotImplementedError


class YostBuffer(_Buffer):
    """Manage all data (packets) consumed from the queue

    YostBuffer holds data from 1 Yost body sensor
    """

    LABELS: ClassVar = ("Roll", "Pitch", "Yaw", "abs(roll) + abs(pitch)")
    NAME_TEMPLATE: ClassVar = "yost_sensor_{name}.csv"

    def __init__(self, bufsize: int, savedir: Path, name: str):
        super().__init__(bufsize, savedir, name)
        header = ",".join(("t", *self.LABELS)) + "\n"
        self.sensor_fp.write(header)

    def add_packet(self, packet: Packet):
        "Add `Packet` of sensor data"
        data, ts = self.data, self.timestamp
        _packet = (
            packet.roll,
            packet.pitch,
            packet.yaw,
            abs(packet.roll) + abs(packet.pitch),
        )

        # Write to file pointer
        self.sensor_fp.write(",".join((str(v) for v in (packet.t, *_packet))) + "\n")

        ### Shift buffer when full, never changing buffer size
        data[:-1] = data[1:]
        data[-1] = _packet
        ts[:-1] = ts[1:]
        ts[-1] = packet.t


class DelsysBuffer(_Buffer):
    """Manage data for all Delsys EMG sensors"""

    LABELS: ClassVar = [str(i) for i in range(1, 17)]
    NAME_TEMPLATE: ClassVar = "sensor_{name}.csv"

    def __init__(self, bufsize: int, savedir: Path):
        super().__init__(bufsize, savedir, "EMG")
        header = ",".join(self.LABELS) + "\n"
        self.sensor_fp.write(header)

    def add_packet(self, packet: Tuple[float, ...]):
        data, ts = self.data, self.timestamp
        # assert len(packet) == 16
        self.sensor_fp.write(",".join((str(v) for v in packet)) + "\n")

        ### Shift buffer when full, never changing buffer size
        data[:-1] = data[1:]
        data[-1] = packet
        ts[:-1] = ts[1:]
        ts[-1] = default_timer()

    def add_packets(self, packets: np.ndarray):
        data, ts = self.data, self.timestamp
        for packet in packets:
            self.sensor_fp.write(",".join((str(v) for v in packet)) + "\n")

        n = len(packets)
        _t = default_timer()

        ### Shift buffer when full, never changing buffer size
        data[:-n] = data[n:]
        data[-n:] = packets
        ts[:-n] = ts[n:]
        ts[-n:] = [_t] * n


if __name__ == "__main__":
    from dis import dis

    dis(Packet)
