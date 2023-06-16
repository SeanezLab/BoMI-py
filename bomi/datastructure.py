from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from timeit import default_timer
from typing import TextIO, Tuple

import numpy as np

DATA_ROOT = Path.home() / "Documents" / "BoMI Data"
DATA_ROOT.mkdir(exist_ok=True)


def get_savedir(task_name: str, mkdir=True) -> Path:
    datestr = datetime.now().strftime("%Y-%m-%d %H-%M-%S-%f")
    savedir = DATA_ROOT / "_".join((datestr, task_name))
    if mkdir:
        savedir.mkdir()
    return savedir


@dataclass
class SubjectMetadata:
    subject_id: str = "Enter S00#"
    joint: str = "Enter TaskJointSide"
    max_rom: int = -1
    sham: str = "Enter 'sham' or 'none'" 
    stim: bool = False

    def dict(self):
        return asdict(self)

    def to_disk(self, savedir: Path):
        "Write metadata to `savedir`"
        with (savedir / "meta.json").open("w") as fp:
            json.dump(asdict(self), fp, indent=2)


class MultichannelBuffer:
    """Manage all data (packets) consumed from the queue

    MultichannelBuffer holds data from an individual sensor
    """
    def __init__(self, bufsize: int, savedir: Path, name: str, input_kind: str, channel_labels: list[str]):
        self.bufsize = bufsize
        self.channel_labels = channel_labels
        # 1D array of timestamps
        self.timestamp: np.ndarray = np.zeros(bufsize)
        # 2D array of `labels`
        self.data: np.ndarray = np.zeros((bufsize, len(self.channel_labels)))

        fp = open(savedir / f"{input_kind}_{name}.csv", "w")

        # filepointer to write CSV data to
        self.sensor_fp: TextIO = fp
        # name of this device
        self.name: str = name

        self._channel_index: int = -1  # index of the labelled channel in use
        self.last_measurement: float = 0.0  # last measurement from the channel selected for the task

        self.savedir: Path = savedir
        header = ",".join(("t", *self.channel_labels)) + "\n"
        self.sensor_fp.write(header)

    def __len__(self):
        return len(self.data)

    def __del__(self):
        "Close open file pointers"
        self.sensor_fp.close()

    def set_angle_type(self, label: str):
        i = self.channel_labels.index(label)
        self._channel_index = i

    def add_packet(self, packet: dict[str, int | float]):
        "Add `Packet` of sensor data"
        _packet = [packet[key] for key in self.channel_labels]

        # Write to file pointer
        self.sensor_fp.write(",".join((str(v) for v in (packet["Time"], *_packet))) + "\n")

        ### Shift buffer when full, never changing buffer size
        self.data[:-1] = self.data[1:]
        self.data[-1] = _packet
        self.timestamp[:-1] = self.timestamp[1:]
        self.timestamp[-1] = packet["Time"]

        self.last_measurement = _packet[self._channel_index]


class DelsysBuffer:
    """Manage data for all Delsys EMG sensors"""

    def __init__(self, bufsize: int, savedir: Path):
        self.bufsize = bufsize

        # 1D array of timestamps
        self.timestamp: np.ndarray = np.zeros(bufsize)

        # 2D array of `labels`
        self.data: np.ndarray = np.zeros((bufsize, 16))

    def add_packet(self, packet: Tuple[float, ...]):
        # assert len(packet) == 16

        ### Shift buffer when full, never changing buffer size
        self.data[:-1] = self.data[1:]
        self.data[-1] = packet
        self.timestamp[:-1] = self.timestamp[1:]
        self.timestamp[-1] = default_timer()

    def add_packets(self, packets: np.ndarray):
        n = len(packets)

        ### Shift buffer when full, never changing buffer size
        self.data[:-n] = self.data[n:]
        self.data[-n:] = packets
        self.timestamp[:-n] = self.timestamp[n:]
        self.timestamp[-n:] = [default_timer()] * n


if __name__ == "__main__":
    from dis import dis

    dis(DelsysBuffer.add_packets)
