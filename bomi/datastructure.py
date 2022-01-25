from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar, Dict, List, NamedTuple

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

    @classmethod
    def init(cls, initial_buf_size: int) -> Buffer:
        timestamp = np.zeros(initial_buf_size)
        buf = np.zeros((initial_buf_size, len(cls.labels)))
        return Buffer(ptr=0, timestamp=timestamp, data=buf)

    def add(self, packet: Packet):
        data, ts = self.data, self.timestamp
        data[self.ptr, :] = (
            packet.roll,
            packet.pitch,
            packet.yaw,
            abs(packet.roll) + abs(packet.pitch),
        )
        ts[self.ptr] = packet.t
        self.ptr += 1

        # Double buffer size if full
        l, dims = data.shape
        if self.ptr >= l:
            self.data = np.empty((l * 2, dims))
            self.data[:l] = data
            self.timestamp = np.empty(l * 2)
            self.timestamp[:l] = ts

    def save(self, fname: str | Path):
        pass

    @staticmethod
    def init_buffers(names: List[str], bufsize: int) -> Dict[str, Buffer]:
        return {dev: Buffer.init(initial_buf_size=bufsize) for dev in names}
