from __future__ import annotations
from dataclasses import dataclass, field
from queue import Queue
from typing import Callable, Dict, List, Optional, TypeVar
import traceback
import PySide6.QtGui as qg
import PySide6.QtWidgets as qw
import PySide6.QtCore as qc
from PySide6.QtCore import Qt
import pyqtgraph as pg
import numpy as np

from bomi.device_manager import DeviceManager, DeviceT, Packet
from bomi.scope_widget import ScopeWidget
from bomi.sr_precision_widget import SRPrecisionWidget
from bomi.window_mixin import WindowMixin


def _print(*args):
    print("[Start React]", *args)


@dataclass
class Buffer:
    timestamp: np.array
    data: np.array
    ptr: int

    @classmethod
    def init(cls, initial_buf_size: int, dims: int) -> Buffer:
        timestamp = np.zeros(initial_buf_size)
        buf = np.zeros((initial_buf_size, dims))
        ptr = 0
        return Buffer(timestamp, buf, ptr)

    def add(self, packet: Packet):
        data, ts = self.data, self.timestamp
        data[self.ptr, :2] = (packet.roll, packet.pitch)
        ts[self.ptr] = packet.t
        self.ptr += 1

        # Double buffer size if full
        l, dims = data.shape
        if self.ptr >= l:
            self.data = np.empty((l * 2, dims))
            self.data[:l] = data
            self.timestamp = np.empty(l * 2)
            self.timestamp[:l] = ts


class StartReactWidget(qw.QWidget, WindowMixin):
    """GUI to manage StartReact tasks"""

    def __init__(self, device_manager: DeviceManager):
        super().__init__()
        self.dm = device_manager

        main_layout = qw.QVBoxLayout()
        self.setLayout(main_layout)

        btn1 = qw.QPushButton(text="Precision")
        btn1.clicked.connect(self.s_precision_task)
        main_layout.addWidget(btn1)

    def s_precision_task(self):
        self.srp = SRPrecisionWidget(self.dm)
        self.srp.show()
