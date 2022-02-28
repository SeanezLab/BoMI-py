from __future__ import annotations
from collections import defaultdict, deque

from typing import Deque, Dict, List, NamedTuple, Tuple
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

from trigno_sdk.client import TrignoClient, EMGSensor, EMGSensorMeta

__all__ = ("TrignoClient", "TrignoWidget", "MUSCLES")


def _print(*args):
    print("[TrignoDeviceManager]", *args)


MUSCLES = (
    "RF (Rectus Femoris)",
    "ST (Semitendinosus)",
    "VLat (Vastus Lateralis)",
    "MG (Gastrocnemius Med)",
    "TA (Transversus Abdominis)",
)


class COLORS:
    RED = qg.QColor(253, 0, 58)  # red
    GREEN = qg.QColor(25, 222, 193)  # green/cyan
    BLUE = qg.QColor(19, 10, 241)  # dark blue
    ORANGE = qg.QColor(254, 136, 33)  # orange
    PURPLE = qg.QColor(177, 57, 255)  # purple


class PlotHandle(NamedTuple):
    plot: pg.PlotItem | pg.ViewBox
    curve: pg.PlotCurveItem


class EMGLayoutError(ValueError):
    ...


class EMGScope(qw.QWidget, WindowMixin):
    sigNameChanged: qc.SignalInstance = qc.Signal()  # type: ignore

    def __init__(self, dm: TrignoClient, savedir: Path):
        super().__init__()
        self.setWindowTitle("EMG Scope")
        self.dm = dm
        self.savedir = savedir

        ### init data
        self.queue: Deque[Tuple[float]] = deque()
        self.buffer: DelsysBuffer = DelsysBuffer(10000, self.savedir)

        ### init UI
        main_layout = qw.QHBoxLayout(self)
        splitter = qw.QSplitter()
        main_layout.addWidget(splitter)

        self.glw: pg.GraphicsLayout | pg.GraphicsView = pg.GraphicsLayoutWidget()
        self.glw.setBackground("white")
        splitter.addWidget(self.glw)

        self.init_plots()

    def calc_layout(self) -> Dict[str, Dict[str, int]]:
        _layout = defaultdict(lambda: {"L": 0, "R": 0, "N/A": 0})

        def add_check(muscle_name: str, side: str):
            if _layout[muscle_name][side] != 0:
                raise EMGLayoutError(
                    f"Multiple EMG sensors assigned to the same muscle (name: {muscle_name}, side: {side}). Please fix the sensor configuration."
                )
            _layout[muscle_name][side] = idx

        for idx in self.dm.sensor_idx:
            sensor: EMGSensor = self.dm.sensors[idx]  # type: ignore
            meta = self.dm.sensor_meta[sensor.serial]
            if meta.side == "L":
                add_check(meta.muscle_name, "L")
            elif meta.side == "R":
                add_check(meta.muscle_name, "R")
            else:
                add_check(meta.muscle_name, "N/A")
        return _layout

    def init_plots(self):
        """
        1. Create a mapping from muscle name to sensor idx corresponding to
        the {left, right, n/a} sides

        for each muscle:
            * if have {left, right}, create pair of plots
            * If only have one, create one horizontal plot
        """
        _layout = self.calc_layout()

        self.plot_handles: Dict[int, PlotHandle] = {}
        plot_style = {"color": "k"}  # label style

        def _setup_emg_plot(plot: pg.PlotItem, idx: int):
            plot.setXRange(-5, 0)
            plot.setLabel("bottom", "Time", units="s", **plot_style)
            plot.setLabel("left", "Voltage", units="V", **plot_style)
            plot.setDownsampling(mode="peak")

            curve = plot.plot()
            self.plot_handles[idx] = PlotHandle(plot=plot, curve=curve)

        pairs: List[Tuple[int, int]] = []
        singles: List[int] = []
        for mp in _layout.values():
            if mp["L"] and mp["R"]:
                pairs.append((mp["L"], mp["R"]))
            else:
                for idx in mp.values():
                    if idx != 0:
                        singles.append(idx)

        row = 1
        for L, R in pairs:
            _setup_emg_plot(self.glw.addPlot(row=row, col=0, colspan=1), L)
            _setup_emg_plot(self.glw.addPlot(row=row, col=1, colspan=1), R)
            row += 1

        for idx in singles:
            _setup_emg_plot(self.glw.addPlot(row=row, col=0, colspan=2), idx)
            row += 1

        # for row, mp in enumerate(_layout.values()):
        # if mp["N/A"]:
        # idx = mp["N/A"]
        # plot: pg.PlotItem = self.glw.addPlot(row=row, col=0, colspan=2)
        # _setup_emg_plot(plot, idx)
        # else:
        # if mp["L"]:
        # idx = mp["L"]
        # plot: pg.PlotItem = self.glw.addPlot(row=row, col=0, colspan=1)
        # _setup_emg_plot(plot, idx)

        # if mp["R"]:
        # idx = mp["R"]
        # plot: pg.PlotItem = self.glw.addPlot(row=row, col=1, colspan=1)
        # _setup_emg_plot(plot, idx)

        def update_title():
            "Update plot titles according to the sensor metadata"
            for idx in self.dm.sensor_idx:
                sensor = self.dm.sensors[idx]
                meta = self.dm.sensor_meta[sensor.serial]
                if meta.side:
                    title = f"{meta.muscle_name} ({meta.side})"
                else:
                    title = meta.muscle_name
                handle = self.plot_handles[idx]
                handle.plot.setTitle(title, **plot_style)

        update_title()
        self.sigNameChanged.connect(update_title)

        # Timer
        self.timer = qc.QTimer()
        self.timer.setInterval(5)
        self.timer.timeout.connect(self.update)  # type: ignore

    def showEvent(self, event: qg.QShowEvent) -> None:
        self.dm.handle_stream(self.queue, savedir=self.savedir)
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

        self.active = False
        if not sensor:
            idx_label = qw.QLabel(f"{idx}", self)
            layout.addRow(idx_label)
            return

        self.active = True

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
        layout.addRow("Muscle:", self.name)

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
            self.sigDataChanged.emit()

        self.name.editingFinished.connect(data_changed)  # type: ignore
        [r.toggled.connect(data_changed) for r in self.radios]  # type: ignore


class TrignoWidget(qw.QWidget, WindowMixin):
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
        main_layout = qw.QVBoxLayout(self)
        control_layout = qw.QGridLayout()
        main_layout.addLayout(control_layout)

        self.status_label = qw.QLabel("Base Station")
        self.status_label.setToolTip(repr(self.trigno_client))
        control_layout.addWidget(self.status_label, 0, 0)
        self.update_status()

        self.connect_btn = btn = qw.QPushButton("Connect to Base Station")
        btn.setStyleSheet("QPushButton { background-color: rgb(0,255,0); }")
        btn.clicked.connect(self.connect)  # type: ignore
        control_layout.addWidget(btn, 0, 1)

        btn = qw.QPushButton("Data charts")
        btn.clicked.connect(self.start_data_scope)  # type: ignore
        control_layout.addWidget(btn, 0, 2)

        btn = qw.QPushButton("Save metadata")
        btn.clicked.connect(self.save_meta)  # type: ignore
        control_layout.addWidget(btn, 0, 3)

        # Devices UI
        self.grid_layout = qw.QGridLayout()
        main_layout.addLayout(self.grid_layout)

        self.setMinimumSize(680, 390)
        self.setup_grid()

    def setup_grid(self):
        for _ in range(self.grid_layout.count()):
            try:
                li = self.grid_layout.takeAt(0)
                w = li.widget()
                w.setParent(None)
                w.deleteLater()
            except Exception:
                break

        for i in range(16):
            sensor = self.trigno_client.sensors[i + 1]
            if sensor:
                if sensor.serial in self.trigno_client.sensor_meta:
                    meta = self.trigno_client.sensor_meta[sensor.serial]
                else:
                    meta = EMGSensorMeta()
                    self.trigno_client.sensor_meta[sensor.serial] = meta

                sensor_w = TrignoSensor(sensor, meta, i + 1)
            else:
                sensor_w = TrignoSensor(None, None, i + 1)

            self.grid_layout.addWidget(sensor_w, i // 4, i % 4)
            sensor_w.sigDataChanged.connect(self.handle_data_changed)

        self.scope: EMGScope | None = None

    def update_status(self):
        self.status_label.setText(
            f"Base Station: {self.trigno_client.host_ip if self.trigno_client.connected else 'Disconnected'}"
        )

    @qc.Slot()  # type: ignore
    def connect(self):
        with pg.BusyCursor():
            self.trigno_client.connect()
        self.update_status()
        self.setup_grid()
        self.connect_btn.setText("Reconnect to Base Station")
        self.status_label.setToolTip(repr(self.trigno_client))

    @qc.Slot()  # type: ignore
    def handle_data_changed(self):
        if self.scope:
            self.scope.sigNameChanged.emit()

    @qc.Slot()  # type: ignore
    def save_meta(self):
        self.trigno_client.save_meta("emg_meta.json", slim=True)

    @qc.Slot()  # type: ignore
    def start_data_scope(self):
        ## Start scope here.
        if not self.trigno_client.connected:
            return self.error_dialog("Trigno Base Station: Not connected.")

        if not self.trigno_client.sensor_idx:
            return self.error_dialog(
                "Trigno Base Station: No sensors paired. Please pair using the Trigno Control Utility"
            )

        try:
            self.scope = EMGScope(self.trigno_client, get_savedir("EMGScope"))
            self.scope.show()
        except EMGLayoutError as e:
            self.error_dialog(str(e))
            self.trigno_client.stop_stream()
        except Exception as e:
            _print(traceback.format_exc())
            self.trigno_client.stop_stream()


if __name__ == "__main__":
    app = qw.QApplication()
    win = TrignoWidget()
    win.show()
    app.exec()
