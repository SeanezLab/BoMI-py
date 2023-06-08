from __future__ import annotations

import traceback
from typing import Final, Tuple

import pyqtgraph as pg
import PySide6.QtCore as qc
import PySide6.QtWidgets as qw
from PySide6.QtCore import Qt

from bomi.datastructure import get_savedir
from bomi.device_managers.table_model import (
    TableModel,
    ColumnProps,
    prop_getter,
    make_getter,
    make_setter,
)
from bomi.device_managers.qtm_manager import QtmDeviceManager
#from bomi.scope_widget import ScopeWidget
from bomi.window_mixin import WindowMixin


__all__ = ("QtmWidget",)

#edited
def _print(*args):
    print("[QtmWidget]", *args)


DEVICE_TYPE: Final = {
    "???": "Unknown",
    "BTL": "Bootloader (No Firmware)",
    "USB": "USB",
    "DNG": "Dongle",
    "WL": "Wireless",
    "EM": "Embedded",
    "DL": "Data-logging",
    "BT": "Bluetooth",
}


# a list of column props for rendering the device manager table
QTM_COL_PROPS: Tuple[ColumnProps, ...] = (
    ColumnProps("QTM Box Port Number", int), #this is the number on the QTM interface.
    #this is NOT the BNC cable number, because they do not match.
    ColumnProps("Nickname", str),
    ColumnProps("Units", str),
)

class QtmWidget(qw.QWidget, WindowMixin):
    """A GUI for QtmDeviceManager.
    Can be used standalone or embedded as a widget
    """

    def __init__(self, qtm_device_manager: QtmDeviceManager):
        super().__init__()
        self.qtm_dm = qtm_device_manager
        self.setWindowTitle("Qtm devices")
        self.setMinimumSize(350, 200)
        self.setSizePolicy(qw.QSizePolicy.Expanding, qw.QSizePolicy.Fixed)

        main_layout = qw.QHBoxLayout(self)

        ### Device controls
        layout = qw.QVBoxLayout()
        main_layout.addLayout(layout)

        discover_btn = qw.QPushButton("&Discover devices")
        discover_btn.setStyleSheet("QPushButton { background-color: rgb(0,255,0); }")
        discover_btn.clicked.connect(self.s_discover_devices)

        chart_btn = qw.QPushButton(text="Data &charts")
        chart_btn.clicked.connect(self.s_data_charts)

        disconnect_btn = qw.QPushButton(text="Disconnect all")
        disconnect_btn.clicked.connect(self.s_disconnect_all)

        layout.addWidget(discover_btn)
        layout.addWidget(chart_btn)
        layout.addWidget(disconnect_btn)

        self.qtm_model = TableModel(QTM_COL_PROPS)
        self.qtm_proxy_model = qc.QSortFilterProxyModel()
        self.qtm_proxy_model.setSourceModel(self.qtm_model)
        self.qtm_proxy_model.setDynamicSortFilter(True)

        qtm_tv = qw.QTableView()
        qtm_tv.setModel(self.qtm_proxy_model)
        qtm_tv.setSortingEnabled(True)
        qtm_tv.setSelectionBehavior(qw.QAbstractItemView.SelectRows)
        qtm_tv.setSelectionMode(qw.QAbstractItemView.SingleSelection)
        qtm_tv.horizontalHeader().setSectionResizeMode(qw.QHeaderView.Stretch)
        qtm_tv.resizeColumnsToContents()
        qtm_tv.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        qtm_tv.setSizePolicy(qw.QSizePolicy.Expanding, qw.QSizePolicy.Expanding)

        main_layout.addWidget(qtm_tv)

    @qc.Slot()
    def s_discover_devices(self):
        ...
        # self.s_disconnect_all()
        # with pg.BusyCursor():
        #     self.yost_dm.discover_devices()
        # if not self.yost_dm.all_sensors:
        #     self.error_dialog(
        #         "No devices found. Make sure wired dongle/sensors are plugged in, "
        #         "and make sure wireless sensors are turned on, and use the same "
        #         "Channel and Pan ID as the dongle."
        #     )
        # self.yost_model.set_devices(self.yost_dm.dongles + self.yost_dm.all_sensors)
        # self.yost_proxy_model.invalidate()

    @qc.Slot()
    def s_data_charts(self):
        ...
        #dm = self.qtm_dm
        #if not dm.has_sensors():
        #    return self.no_qtm_sensors_error()
        ## Start scope here.
        # try:
        #     self._sw = ScopeWidget(dm, get_savedir("Scope"))
        #     self._sw.showMaximized()
        # except Exception as e:
        #     _print(traceback.format_exc())
        #     dm.stop_stream()

    @qc.Slot()
    def s_disconnect_all(self):
        ...
        # self.qtm_dm.close_all_devices()
        # self.qtm_model.set_devices([])
        # self.qtm_proxy_model.invalidate()


if __name__ == "__main__":
    app = qw.QApplication()
    dm = QtmDeviceManager()
    win = QtmWidget(dm)
    win.show()
    app.exec()
