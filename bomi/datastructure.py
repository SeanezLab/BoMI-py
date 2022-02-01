from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime
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


def get_savedir(task_name: str) -> Path:
    datestr = datetime.now().strftime("%Y-%m-%d %H-%M-%S-%f")
    savedir = DATA_ROOT / "_".join((datestr, task_name))
    savedir.mkdir()
    return savedir


class TaskEventFmt:
    event = "{event_name} t={t}"

    visual = "visual t={t}"
    visual_auditory = "visual_auditory t={t}"
    visual_startle = "visual_startling t={t}"


@dataclass
class Metadata:
    subject_id: str = "unknown"

    def dict(self):
        return asdict(self)

    def to_disk(self, savedir: Path):
        "Write metadata to `savedir`"
        with (savedir / "meta.json").open("w") as fp:
            json.dump(asdict(self), fp)


@dataclass()
class Buffer:
    """Manage all data (packets) consumed from the queue"""

    # Sensor data
    labels: ClassVar = ("Roll", "Pitch", "Yaw", "abs(roll) + abs(pitch)")
    ptr: int
    bufsize: int
    timestamp: np.ndarray  # 1D array of timestamps
    data: np.ndarray  # 2D array of `labels`
    sensor_fp: TextIO  # filepointer to write CSV data to

    # task data
    task_history: TextIO  # filepointer to write task history

    savedir: Path

    def close(self):
        "Close open file pointers"
        self.sensor_fp.close()
        self.task_history.close()

    @classmethod
    def init(cls, bufsize: int, savedir: Path, name: str) -> Buffer:
        timestamp = np.zeros(bufsize)
        buf = np.zeros((bufsize, len(cls.labels)))

        print("Writing data to ", savedir)

        sensor_fp = open(savedir / f"sensor_{name}.csv", "w")
        header = ",".join(("t", *cls.labels)) + "\n"
        sensor_fp.write(header)

        task_history = open(savedir / f"task_history_{name}.csv", "w")

        return Buffer(
            ptr=0,
            bufsize=bufsize,
            timestamp=timestamp,
            data=buf,
            sensor_fp=sensor_fp,
            task_history=task_history,
            savedir=savedir,
        )

    @staticmethod
    def init_buffers(
        names: List[str], bufsize: int, savedir: Path
    ) -> Dict[str, Buffer]:
        """Create the save directory and return a dictionary of {name: Buffer}"""
        bufs = {}
        for dev in names:
            bufs[dev] = Buffer.init(bufsize=bufsize, savedir=savedir, name=dev)

        return bufs

    def move_target(self, t: float, tmin: float, tmax: float):
        self.task_history.write(f"target_moved t={t} tmin={tmin} tmax={tmax}\n")

    def write_task_event(self, event_name: str, t: float = None):
        if t == None:
            t = default_timer()
        self.task_history.write(f"{event_name} t={t}\n")

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
        if self.ptr >= self.bufsize:
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
