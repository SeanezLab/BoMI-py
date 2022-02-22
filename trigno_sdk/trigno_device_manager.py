from __future__ import annotations
from collections import deque

from typing import Deque, Dict, NamedTuple, Tuple
from pathlib import Path
from timeit import default_timer
import traceback

import pyqtgraph as pg
import PySide6.QtCore as qc
import PySide6.QtGui as qg
import PySide6.QtWidgets as qw
from PySide6.QtCore import Qt
import numpy as np

from bomi.datastructure import get_savedir, DelsysBuffer
from bomi.window_mixin import WindowMixin

from trigno_sdk import TrignoClient, EMGSensor, EMGSensorMeta
from pprint import pprint


def _print(*args):
    print("[TrignoDeviceManager]", *args)


class COLORS:
    RED = qg.QColor(253, 0, 58)  # red
    GREEN = qg.QColor(25, 222, 193)  # green/cyan
    BLUE = qg.QColor(19, 10, 241)  # dark blue
    ORANGE = qg.QColor(254, 136, 33)  # orange
    PURPLE = qg.QColor(177, 57, 255)  # purple


class PlotHandle(NamedTuple):
    plot: pg.PlotItem | pg.ViewBox
    curve: pg.PlotCurveItem


class EMGScope(qw.QWidget):
    sigNameChanged: qc.SignalInstance = qc.Signal()

    def __init__(self, dm: TrignoClient, savedir: Path):
        super().__init__()
        self.setWindowTitle("EMG Scope")
        self.dm = dm
        self.savedir = savedir

        # init data
        self.queue: Deque[Tuple[float]] = deque()
        self.buffer: DelsysBuffer = DelsysBuffer(10000, self.savedir, name="EMG")

        # init UI
        main_layout = qw.QHBoxLayout(self)
        splitter = qw.QSplitter()
        main_layout.addWidget(splitter)

        self.glw = glw = pg.GraphicsLayoutWidget()
        glw.setBackground("white")
        splitter.addWidget(glw)

        row = 1
        self.plot_handles: Dict[int, PlotHandle] = {}
        plot_style = {"color": "k"}  # label style
        for idx in dm.sensor_idx:
            sensor = self.dm.sensors[idx]
            meta = self.dm.sensor_meta[sensor.serial]

            plot: pg.PlotItem = glw.addPlot(row=row, col=0)
            row += 1
            plot.setXRange(-5, 0)
            plot.setYRange(-0.1, 0.1)
            plot.setLabel("bottom", "Time", units="s", **plot_style)
            plot.setLabel("left", "Voltage", units="V", **plot_style)
            plot.setTitle(meta.muscle_name, **plot_style)
            plot.setDownsampling(mode="peak")

            curve = plot.plot()
            self.plot_handles[idx] = PlotHandle(plot=plot, curve=curve)

        def update_title():
            for idx in dm.sensor_idx:
                sensor = self.dm.sensors[idx]
                meta = self.dm.sensor_meta[sensor.serial]
                handle = self.plot_handles[idx]
                handle.plot.setTitle(meta.muscle_name, **plot_style)

        self.sigNameChanged.connect(update_title)

        # Timer
        self.timer = qc.QTimer()
        self.timer.setInterval(5)
        self.timer.timeout.connect(self.update)  # type: ignore

    def showEvent(self, event: qg.QShowEvent) -> None:
        self.dm.handle_stream(self.queue)
        self.timer.start()
        return super().showEvent(event)

    def closeEvent(self, event: qg.QCloseEvent) -> None:
        with pg.BusyCursor():
            self.timer.stop()
            self.dm.stop_stream()
        return super().closeEvent(event)

    def update(self):
        q = self.queue
        qsize = len(q)

        if qsize:
            self.buffer.add_packets(np.array([q.popleft() for _ in range(qsize)]))

        now = default_timer()
        x = -(now - self.buffer.timestamp)
        y = self.buffer.data
        for idx in range(1, 17):
            sensor = self.dm.sensors[idx]
            if not sensor:
                continue

            handle = self.plot_handles[idx]
            handle.curve.setData(x=x, y=y[:, idx - 1])


class TrignoSensor(qw.QWidget):
    CLR_CONNECTED = COLORS.GREEN
    CLR_DISCONNECTED = Qt.gray

    sigDataChanged: qc.SignalInstance = qc.Signal()

    def __init__(self, sensor: EMGSensor | None, meta: EMGSensorMeta | None, idx: int):
        super().__init__()
        self.setMinimumSize(160, 80)

        self.setAutoFillBackground(True)
        self.setPalette(self.CLR_DISCONNECTED)  # background color

        self.sensor = sensor
        self.setToolTip(repr(sensor))

        layout = qw.QFormLayout(self)

        if not sensor:
            idx_label = qw.QLabel(f"{idx}", self)
            layout.addRow(idx_label)
            return

        idx_label = qw.QLabel(f"{idx} | Serial: {sensor.serial}", self)
        layout.addRow(idx_label)

        assert meta is not None
        self.setPalette(self.CLR_CONNECTED)  # background color

        ### Config options
        # Muscle name
        self.name = qw.QLineEdit(meta.muscle_name)
        model = qc.QStringListModel()
        model.setStringList(MUSCLES)
        completer = qw.QCompleter()
        completer.setModel(model)
        self.name.setCompleter(completer)
        layout.addRow("Muscle name:", self.name)

        # Left or right
        lo = qw.QHBoxLayout()
        self.radio_left = qw.QRadioButton("L")
        self.radio_right = qw.QRadioButton("R")
        self.radio_none = qw.QRadioButton("N/A")
        self.radios = [self.radio_left, self.radio_right, self.radio_none]
        if meta.side == "L":
            self.radio_left.toggle()
        elif meta.side == "R":
            self.radio_right.toggle()
        else:
            self.radio_none.toggle()

        lo.addWidget(self.radio_left)
        lo.addWidget(self.radio_right)
        lo.addWidget(self.radio_none)
        layout.addRow("Side", lo)

        def data_changed():
            meta.muscle_name = self.name.text()
            meta.side = next(filter(lambda r: r.isChecked(), self.radios)).text()
            if meta.side == "N/A":
                meta.side = ""
            print(meta)
            self.sigDataChanged.emit()

        self.name.editingFinished.connect(data_changed)  # type: ignore
        [r.toggled.connect(data_changed) for r in self.radios]  # type: ignore


MUSCLES = (
    "RF (Rectus Femoris)",
    "ST (Semitendinosus)",
    "VLat (Vastus Lateralis)",
    "MG (Gastrocnemius Med)",
    "TA (Transversus Abdominis)",
)


class TrignoDeviceManagerWidget(qw.QWidget, WindowMixin):
    """A GUI for the Trigno SDK Client"""

    def __init__(self, trigno_client: TrignoClient = None):
        super().__init__()
        self.setWindowTitle("Trigno SDK Client")
        trigno_client = trigno_client if trigno_client else TrignoClient()
        self.trigno_client = trigno_client

        if not trigno_client.sensor_meta:
            meta_path = Path("emg_meta.json")
            try:
                trigno_client.load_meta(meta_path)
            except FileNotFoundError:
                _print("EMG sensor meta file not found", meta_path)

        ### Init UI
        main_layout = qw.QHBoxLayout(self)
        control_layout = qw.QVBoxLayout()
        main_layout.addLayout(control_layout)

        self.status_label = qw.QLabel("Status")
        control_layout.addWidget(self.status_label)
        self.update_status()

        btn = qw.QPushButton("Connect to Base Station")
        btn.clicked.connect(self.connect)  # type: ignore
        control_layout.addWidget(btn)

        btn = qw.QPushButton("Data charts")
        btn.clicked.connect(self.start_data_scope)  # type: ignore
        control_layout.addWidget(btn)

        btn = qw.QPushButton("Save metadata")
        btn.clicked.connect(self.save_meta)  # type: ignore
        control_layout.addWidget(btn)

        # Devices UI
        grid_layout = qw.QGridLayout()
        main_layout.addLayout(grid_layout)

        for i in range(16):
            sensor = trigno_client.sensors[i + 1]
            if sensor:
                if sensor.serial in trigno_client.sensor_meta:
                    meta = trigno_client.sensor_meta[sensor.serial]
                else:
                    meta = EMGSensorMeta()
                    trigno_client.sensor_meta[sensor.serial] = meta

                sensor_w = TrignoSensor(sensor, meta, i + 1)
            else:
                sensor_w = TrignoSensor(None, None, i + 1)

            grid_layout.addWidget(sensor_w, i // 4, i % 4)
            sensor_w.sigDataChanged.connect(self.handle_data_changed)

        self.scope: EMGScope | None = None

    def update_status(self):
        self.status_label.setText(
            f"Status: {'Connected' if self.trigno_client.connected else 'Disconnected'}"
        )

    @qc.Slot()  # type: ignore
    def connect(self):
        self.trigno_client.setup()
        self.update_status()

    @qc.Slot()  # type: ignore
    def handle_data_changed(self):
        if self.scope:
            self.scope.sigNameChanged.emit()

    @qc.Slot()  # type: ignore
    def save_meta(self):
        self.trigno_client.save_meta("emg_meta.json")

    @qc.Slot()  # type: ignore
    def start_data_scope(self):
        ## Start scope here.
        try:
            self.scope = EMGScope(self.trigno_client, get_savedir("EMGScope"))
            self.scope.show()
        except Exception as e:
            _print(traceback.format_exc())
            self.trigno_client.stop_stream()


if __name__ == "__main__":
    app = qw.QApplication()
    win = TrignoDeviceManagerWidget()
    win.show()
    app.exec()
