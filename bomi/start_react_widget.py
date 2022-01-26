from __future__ import annotations
import traceback
import PySide6.QtGui as qg
import PySide6.QtWidgets as qw
import PySide6.QtCore as qc
from PySide6.QtCore import Qt
import pyqtgraph as pg
import numpy as np

from bomi.device_manager import YostDeviceManager
from bomi.scope_widget import ScopeConfig, ScopeWidget
from bomi.window_mixin import WindowMixin


def _print(*args):
    print("[Start React]", *args)


precision_config = ScopeConfig(
    window_title="Precision",
    target_show=True,
    yrange=(0, 180),
    show_roll=False,
    show_pitch=False,
    show_yaw=False,
)


class StartReactWidget(qw.QWidget, WindowMixin):
    """GUI to manage StartReact tasks"""

    def __init__(self, device_manager: YostDeviceManager):
        super().__init__()
        self.dm = device_manager

        main_layout = qw.QVBoxLayout()
        self.setLayout(main_layout)

        btn1 = qw.QPushButton(text="Precision")
        btn1.clicked.connect(self.s_precision_task)
        main_layout.addWidget(btn1)

    def s_precision_task(self):
        dm = self.dm
        if not dm.has_sensors():
            return self.error_dialog(
                "No sensors available. Plug in the devices, then click on 'Discover devices'"
            )

        try:
            self._precision = ScopeWidget(dm, config=precision_config)
            self._precision.showMaximized()
        except Exception as e:
            _print(traceback.format_exc())
            self.dm.stop_stream()
