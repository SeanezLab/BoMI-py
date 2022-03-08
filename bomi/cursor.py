import traceback
from queue import Queue
from typing import Dict, List
from timeit import default_timer

import PySide6.QtCore as qc
import PySide6.QtWidgets as qw
import PySide6.QtGui as qg
from PySide6.QtCore import Qt

from bomi.device_managers import YostDeviceManager, YostWidget
from bomi.scope_widget import ScopeConfig, ScopeWidget
from bomi.base_widgets import wrap_gb
from bomi.window_mixin import WindowMixin
from bomi.datastructure import get_savedir, YostBuffer, Packet


def _print(*args):
    print("[Cursor Control]", *args)


class CursorControlWidget(qw.QWidget, WindowMixin):
    def __init__(self, dm: YostDeviceManager = None, show_device_manager=True):
        super().__init__()
        self.setWindowTitle("Cursor Control")
        self.dm = dm if dm else YostDeviceManager()
        self.show_device_manager = show_device_manager
        self.init_ui()

        self.quitAct = qg.QAction("Exit", self)
        self.quitAct.setShortcut("esc")
        self.quitAct.triggered.connect(self.close)  # type: ignore

        self.savedir = get_savedir("CursorControl")

        # Yost data
        self.queue: Queue[Packet] = Queue()
        self.buffers: Dict[str, YostBuffer] = {}
        self.dev_names: List[str] = []  # device name/nicknames
        self.dev_sn: List[str] = []  # device serial numbers (hex str)
        self.init_bufsize = 2500  # buffer size

        # Cursor control
        self.timer = qc.QTimer()
        self.timer.setInterval(10)
        self.timer.timeout.connect(self.update)  # type: ignore
        self.fps_counter = 0
        self.fps_last_time = default_timer()

        self.running = False

        # Calibration timer
        self._calib_timer = qc.QTimer()
        self._calib_timer.setInterval(10 * 1000)
        self._calib_timer.setSingleShot(True)
        self._calib_timer.timeout.connect(self.end_calibration)  # type: ignore

    def init_ui(self):
        main_layout = qw.QVBoxLayout(self)

        if self.show_device_manager:
            l = qw.QLabel(self, text="BoMI 🚶", alignment=qc.Qt.AlignCenter)  # type: ignore
            main_layout.addWidget(l)

            ### Device manager group
            main_layout.addWidget(wrap_gb("Yost Device Manager", YostWidget(self.dm)))

        ### Cursor Control
        gb = qw.QGroupBox("Cursor Control")
        main_layout.addWidget(gb)
        layout = qw.QVBoxLayout(gb)

        self.calib_btn = qw.QPushButton("Calibrate Cursor Control")
        self.calib_btn.clicked.connect(self.start_calibration)  # type: ignore
        layout.addWidget(self.calib_btn)

        self.toggle_btn = qw.QPushButton("Start Cursor Control")
        self.toggle_btn.clicked.connect(self.toggle_cursor_control)  # type: ignore
        layout.addWidget(self.toggle_btn)

    def start_calibration(self):
        dm = self.dm
        if not dm.has_sensors():
            return self.no_yost_sensors_error()

        scope_config = ScopeConfig(
            show_scope_params=False,
            autoscale_y=True,
            show_roll=True,
            show_pitch=True,
            show_yaw=True,
            show_rollpitch=False,
        )

        ## Start scope here.
        try:
            self._sw = ScopeWidget(
                dm, savedir=get_savedir("CursorControl"), config=scope_config
            )

            self._calib_timer.start()

            self._sw.showMaximized()

        except Exception:
            _print(traceback.format_exc())
            dm.stop_stream()

    def end_calibration(self):
        if hasattr(self, "_sw"):
            sw: ScopeWidget = getattr(self, "_sw")
            delattr(self, "_sw")
            sw.close()

            for name, buffer in sw.buffers.items():
                ...

    def stop(self):
        if self.running:
            return self.toggle_cursor_control()

    def keyPressEvent(self, event: qg.QKeyEvent):
        if self.running and event.key() == Qt.Key_Escape:
            return self.toggle_cursor_control()
        return super().keyPressEvent(event)

    def closeEvent(self, event: qg.QCloseEvent):
        if self.running:
            self.end_cursor_control()
        return super().closeEvent(event)

    def toggle_cursor_control(self):
        if self.running:
            self.running = False
            self.toggle_btn.setText("Start Cursor Control")
            self.end_cursor_control()
        else:
            if not self.dm.has_sensors():
                return self.no_yost_sensors_error()

            self.running = True
            self.toggle_btn.setText("End Cursor Control")
            self.start_cursor_control()

    def start_cursor_control(self):
        self.init_data()
        self.dm.start_stream(self.queue)
        self.timer.start()

    def end_cursor_control(self):
        self.dm.stop_stream()
        hasattr(self, "timer") and self.timer.stop()

    def update(self):
        self.fps_counter += 1
        if self.fps_counter > 2000:
            now = default_timer()
            interval = now - self.fps_last_time
            fps = self.fps_counter / interval
            self.fps_counter = 0
            self.fps_last_time = now
            _print("FPS: ", fps)

        q = self.queue
        qsize = q.qsize()

        for _ in range(qsize):  # process current items in queue
            packet: Packet = q.get()
            self.buffers[packet.name].add_packet(packet)

        # On successful read from queue, update cursor position
        name = self.dev_names[0]
        buf = self.buffers[name]
        dx, dy = buf.data[-1, :2]

        cursor = qg.QCursor()
        pos = cursor.pos()
        cursor.setPos(pos.x() - dx, pos.y() - dy)

    def init_data(self):
        ### data
        while self.queue.qsize():
            self.queue.get()
        self.dev_names = self.dm.get_all_sensor_names()
        self.dev_sn = self.dm.get_all_sensor_serial()

        for dev in self.dev_names:
            if dev in self.buffers:  # buffer already initialized
                continue
            self.buffers[dev] = YostBuffer(
                bufsize=self.init_bufsize, savedir=self.savedir, name=dev
            )


if __name__ == "__main__":
    app = qw.QApplication()
    win = CursorControlWidget()
    win.show()
    app.exec()
