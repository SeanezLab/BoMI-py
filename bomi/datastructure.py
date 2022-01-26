from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import ClassVar, Dict, List, NamedTuple, TextIO

import numpy as np


class Packet(NamedTuple):
    """Packet represents one streaming batch from one sensor"""

    pitch: float
    yaw: float
    roll: float
    battery: int
    t: float  # time
    name: str  # device nickname


@dataclass
class Buffer:
    """Manage all data (packets) consumed from the queue"""

    labels: ClassVar = ("Roll", "Pitch", "Yaw", "abs(roll) + abs(pitch)")

    ptr: int
    timestamp: np.array  # 1D array of timestamps
    data: np.array  # 2D array of (roll, pitch, yaw)
    fp: TextIO  # filepointer to write CSV data to

    @classmethod
    def init(cls, initial_buf_size: int, name: str = "") -> Buffer:
        timestamp = np.zeros(initial_buf_size)
        buf = np.zeros((initial_buf_size, len(cls.labels)))

        datestr = datetime.now().strftime("%Y-%m-%d %H-%M-%S-%f")
        fname = f"{datestr}_{name}.csv"
        savedir = Path.home() / "Documents" / "BoMI Data"
        savedir.mkdir(exist_ok=True)
        print("Writing data to ", savedir / fname)
        fp = open(savedir / fname, "w")

        header = ",".join(("t", *cls.labels)) + "\n"
        fp.write(header)

        return Buffer(ptr=0, timestamp=timestamp, data=buf, fp=fp)

    @staticmethod
    def init_buffers(names: List[str], bufsize: int) -> Dict[str, Buffer]:
        return {dev: Buffer.init(initial_buf_size=bufsize, name=dev) for dev in names}

    def add(self, packet: Packet):
        data, ts = self.data, self.timestamp
        _packet = (
            packet.roll,
            packet.pitch,
            packet.yaw,
            abs(packet.roll) + abs(packet.pitch),
        )
        data[self.ptr, :] = _packet
        ts[self.ptr] = packet.t

        self.fp.write(
            ",".join((str(v) for v in (packet.t, *_packet))) + "\n"
        )  # write to file pointer

        # Double buffer size if full
        self.ptr += 1
        l, dims = data.shape
        if self.ptr >= l:
            self.data = np.empty((l * 2, dims))
            self.data[:l] = data
            self.timestamp = np.empty(l * 2)
            self.timestamp[:l] = ts
