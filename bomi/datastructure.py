from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from timeit import default_timer
from typing import TextIO, Tuple, Any

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
        """Write metadata to `savedir`"""
        with (savedir / "meta.json").open("w") as fp:
            json.dump(asdict(self), fp, indent=2)


@dataclass(frozen=True, slots=True)
class Packet:
    """
    Represents a packet of data from an individual sensor.
    """

    time: float
    """
    The time that this packet object was created,
    as returned by timeit.default_timer().
    """

    device_name: str
    """
    The name of the device that reported the data
    in this packet.
    """

    channel_readings: dict[str, Any]
    """
    A dictionary of the channel readings,
    where the keys are the device's channel labels,
    and the values are the readings.
    """


class MultichannelBuffer:
    """Manage all data (packets) consumed from the queue

    MultichannelBuffer holds data from an individual sensor
    """
    def __init__(self, bufsize: int, savedir: Path, name: str, input_kind: str, channel_labels: list[str]):
        self.bufsize = bufsize
        self.channel_labels = channel_labels
        # 1D array of timestamps
        self.timestamp = np.zeros(bufsize)
        # 2D array of `labels`
        self._raw_data = np.zeros(
            shape=(bufsize,),
            dtype=[
                (name, np.float64)
                for name in channel_labels
            ]
        )
        # The publicly exposed data is simply a reference to the raw data; i.e. there is no transformation applied.
        self.data = self._raw_data

        # file pointer to write CSV data to
        self.sensor_fp = open(savedir / f"{input_kind}_{name}.csv", "w")
        # name of this device
        self.name = name

        self.savedir = savedir
        header = ",".join(("t", *self.channel_labels)) + "\n"
        self.sensor_fp.write(header)

    def __len__(self):
        return len(self.data)

    def __del__(self):
        """Close open file pointers"""
        self.sensor_fp.close()

    def add_packet(self, packet: Packet):
        """Add `Packet` of sensor data"""
        readings = tuple(packet.channel_readings[key] for key in self.channel_labels)

        # Write to file pointer
        self.sensor_fp.write(",".join((str(v) for v in (packet.time, *readings))) + "\n")

        # Shift buffer when full, never changing buffer size
        self._raw_data[:-1] = self._raw_data[1:]
        self._raw_data[-1] = readings
        self.timestamp[:-1] = self.timestamp[1:]
        self.timestamp[-1] = packet.time


class AveragedMultichannelBuffer(MultichannelBuffer):
    DEFAULT_MOVING_AVERAGE_POINTS = 1024
    """
    The number of points for the moving average by default.
    If the buffer is initialized with a size lower than this,
    the number of points for the moving average will be the size.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.data = self._raw_data.copy()
        self.moving_average_points = min(self.bufsize, self.DEFAULT_MOVING_AVERAGE_POINTS)

    def add_packet(self, *args, **kwargs):
        super().add_packet(*args, **kwargs)

        moving_average_slice = self._raw_data[-self.moving_average_points:]
        averages = tuple(moving_average_slice[col_name].mean() for col_name in moving_average_slice.dtype.names)

        self.data[:-1] = self.data[1:]
        self.data[-1] = averages


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

        # Shift buffer when full, never changing buffer size
        self.data[:-1] = self.data[1:]
        self.data[-1] = packet
        self.timestamp[:-1] = self.timestamp[1:]
        self.timestamp[-1] = default_timer()

    def add_packets(self, packets: np.ndarray):
        n = len(packets)

        self.data[:-n] = self.data[n:]
        self.data[-n:] = packets
        self.timestamp[:-n] = self.timestamp[n:]
        self.timestamp[-n:] = [default_timer()] * n


if __name__ == "__main__":
    from dis import dis

    dis(DelsysBuffer.add_packets)
