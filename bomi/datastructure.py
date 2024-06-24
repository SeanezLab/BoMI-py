from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from timeit import default_timer
from typing import TextIO, Tuple, Any

import numpy as np

def get_savedir(data_root: Path, task_name: str, mkdir=True) -> Path:
    datestr = datetime.now().strftime("%Y-%m-%d %H-%M-%S-%f")

    savedir = data_root / "_".join((datestr, task_name))
    if mkdir:
        savedir.mkdir(parents=True, exist_ok=True)
    return savedir


@dataclass
class SubjectMetadata:
    subject_id: str = "Enter S00#"
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
        self.timestamp: np.ndarray = np.zeros(bufsize)
        # 2D array of `labels`
        self.data: np.ndarray = np.recarray(
            shape=(bufsize,),
            dtype=[
                (name, np.number)
                for name in channel_labels
            ]
        )
        self.data.fill(0)

        # file pointer to write CSV data to
        self.sensor_fp: TextIO = open(savedir / f"{input_kind}_{name}.csv", "w")
        # name of this device
        self.name: str = name

        self.savedir: Path = savedir
        header = ",".join(("t", *self.channel_labels)) + "\n"
        self.sensor_fp.write(header)

    def __len__(self):
        return len(self.data)

    def __del__(self):
        """Close open file pointers"""
        self.sensor_fp.close()

    def add_packet(self, packet: Packet):
        """Add `Packet` of sensor data"""
        #readings = tuple(packet.channel_readings[key] for key in self.channel_labels)
        #Code below is expanded one line of readings
        readings = ()
        for key in self.channel_labels:
           value = packet.channel_readings[key]
           readings += (value,)
        ##

        # Write to file pointer
        self.sensor_fp.write(",".join((str(v) for v in (packet.time, *readings))) + "\n")
  
        # Shift buffer when full, never changing buffer size
        #INSTEAD OF ONE YOU'D SHIFT HOW MANY SAMPLES IN A FRAME, LIKE 128 FOR 100
        #HOW LONG ARE YYOU
        self.data[:-1] = self.data[1:]
        #print(self.data[1])
        self.data[-1] = readings
        self.timestamp[:-1] = self.timestamp[1:]
        self.timestamp[-1] = packet.time


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
