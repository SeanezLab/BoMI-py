import sys
import PySide6.QtWidgets as qw
import pyqtgraph as pg
import numpy as np

from bomi.device_manager import DeviceManager


__appname__ = "BoMI"


class MainWindow(qw.QMainWindow):
    def __init__(self):
        super().__init__()
        self._device_manager = DeviceManager()

        self._init_window()

    def _init_window(self):
        self.setWindowTitle(__appname__)
        cw = qw.QWidget()
        self.setCentralWidget(cw)
        layout = qw.QGridLayout()
        cw.setLayout(layout)

        l = qw.QLabel(self)
        l.setText("Hello")
        layout.addWidget(l, 0, 0)

        button = qw.QPushButton(text="Discover devices", parent=self)
        layout.addWidget(button)


if __name__ == "__main__":
    app = qw.QApplication()
    app.setApplicationName(__appname__)
    win = MainWindow()
    win.show()
    sys.exit(app.exec())
