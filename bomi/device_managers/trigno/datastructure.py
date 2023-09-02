from typing import List
from dataclasses import dataclass

__all__ = ("EMGSensorMeta", "EMGSensor", "DSChannel")


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
    mode: int
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
