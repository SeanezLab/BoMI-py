from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path
from timeit import default_timer
from typing import ClassVar, Dict, List, NamedTuple, TextIO

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


class TaskEventFmt:
    target_moved = "target_moved t={t} tmin={tmin} tmax={tmax}"
    event = "{event_name} t={t}"

    visual = "visual_signal t={t}"
    visual_auditory = "visual_auditory_signal t={t}"
    visual_startle = "visual_startle_signal t={t}"


@dataclass()
class Buffer:
    """Manage all data (packets) consumed from the queue"""

    # Sensor data
    labels: ClassVar = ("Roll", "Pitch", "Yaw", "abs(roll) + abs(pitch)")
    ptr: int
    buf_size: int
    timestamp: np.array  # 1D array of timestamps
    data: np.array  # 2D array of (roll, pitch, yaw)
    sensor_fp: TextIO  # filepointer to write CSV data to

    # task data
    task_history: TextIO  # filepointer to write task history

    @classmethod
    def init(cls, buf_size: int, savedir: Path, name: str) -> Buffer:
        timestamp = np.zeros(buf_size)
        buf = np.zeros((buf_size, len(cls.labels)))

        print("Writing data to ", savedir)

        sensor_fp = open(savedir / f"sensor_{name}.csv", "w")
        header = ",".join(("t", *cls.labels)) + "\n"
        sensor_fp.write(header)

        task_history = open(savedir / f"task_history_{name}.csv", "w")

        return Buffer(
            ptr=0,
            buf_size=buf_size,
            timestamp=timestamp,
            data=buf,
            sensor_fp=sensor_fp,
            task_history=task_history,
        )

    @staticmethod
    def init_buffers(
        names: List[str], bufsize: int, task_name: str = ""
    ) -> Dict[str, Buffer]:
        """Create the save directory and return a dictionary of {name: Buffer}"""
        datestr = datetime.now().strftime("%Y-%m-%d %H-%M-%S-%f")
        savedir = DATA_ROOT / "_".join((datestr, task_name))
        savedir.mkdir()

        bufs = {}
        for dev in names:
            bufs[dev] = Buffer.init(buf_size=bufsize, savedir=savedir, name=dev)

        return bufs

    def move_target(self, t: float, tmin: float, tmax: float):
        s = TaskEventFmt.target_moved.format(t=t, tmin=tmin, tmax=tmax) + "\n"
        self.task_history.write(s)

    def write_task_event(self, event_name: str, t: float = None):
        if t == None:
            t = default_timer()
        s = TaskEventFmt.event.format(event_name=event_name, t=t)
        self.task_history.write(s + "\n")

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
        if self.ptr >= self.buf_size:
            data[:-1] = data[1:]
            data[-1] = _packet
            ts[:-1] = ts[1:]
            ts[-1] = packet.t
        else:
            data[self.ptr] = _packet
            ts[self.ptr] = packet.t
            self.ptr += 1


if __name__ == "__main__":
    from dis import dis

    dis(Packet)
