from typing import Protocol, Sequence
from queue import Queue


class SupportsStreaming(Protocol):
    def start_stream(self, queue: Queue) -> None:
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