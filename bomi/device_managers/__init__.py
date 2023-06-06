"""
Device managers classes and their QWidget wrappers
"""
from .protocols import SupportsStreaming, SupportsGetSensorMetadata, SupportsHasSensors
from .yost_manager import YostDeviceManager
from .yost_widget import YostWidget
from .trigno_widget import TrignoClient, TrignoWidget
