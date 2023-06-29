from typing import Protocol, Sequence, ClassVar
from queue import Queue
from PySide6.QtCore import Signal

from bomi.datastructure import Packet


class SupportsStreaming(Protocol):
    def start_stream(self, queue: Queue[Packet]) -> None:
        """
        Start streaming data to the passed in queue
        """

    def stop_stream(self) -> None:
        """
        Stop streaming data
        """


class SupportsGetSensorMetadata(Protocol):
    def get_all_sensor_names(self) -> Sequence[str]:
        """
        Returns the names of the sensors added to this device manager
        """

    def get_all_sensor_serial(self) -> Sequence[str]:
        """
        Returns the hex serials of the sensors added to this device manager
        """


class SupportsHasSensors(Protocol):
    def has_sensors(self) -> bool:
        """
        Returns True if the device manager has sensors added.
        """


class HasDiscoverDevicesSignal(Protocol):
    discover_devices_signal: ClassVar[Signal]
    """
    Signal fired when the device manager discovers devices.
    """


class HasChannelLabels(Protocol):
    CHANNEL_LABELS: Sequence[str]
    """
    Contains the labels for the channels available with the devices
    of this device manager.
    """


class HasInputKind(Protocol):
    INPUT_KIND: str
    """
    The name of the kind of input that this device manager allows you to use,
    e.g. "Yost".
    """


class SupportsGetChannelMetadata(Protocol):
    @staticmethod
    def get_channel_unit(channel: str) -> str:
        """
        Gets the unit for the data of a given channel.
        """

    @staticmethod
    def get_channel_default_range(channel: str) -> tuple[float, float]:
        """
        Gets a reasonable range for the data of a given channel.
        """


class HasDefaultRanges(Protocol):
    DEFAULT_BASE_RANGE: tuple[float, float]
    """
    Default (min, max) for the ScopeWidget base region when using this device manager.
    """

    DEFAULT_TARGET_RANGE: tuple[float, float]
    """
    Default (min, max) for the ScopeWidget target region when using this device manager.
    """
