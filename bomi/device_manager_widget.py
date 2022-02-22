from __future__ import annotations

import traceback
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Final, List, Optional, Tuple

import pyqtgraph as pg
import PySide6.QtCore as qc
import PySide6.QtWidgets as qw
from PySide6.QtCore import Qt
from bomi.datastructure import get_savedir

from bomi.device_manager import DeviceT, YostDeviceManager
from bomi.scope_widget import ScopeWidget
from bomi.window_mixin import WindowMixin


def _print(*args):
    print("[DeviceManagerWidget]", *args)


SetterT = Callable[[DeviceT, Any], None]
GetterT = Callable[[DeviceT], Any]


@dataclass
class ColumnProps:
    name: str
    dtype: Callable
    get: Optional[GetterT] = None
    set: Optional[SetterT] = None
    editable: bool = False
    _val: Dict[DeviceT, Any] = field(default_factory=dict)  # cache

    def use_getter(self, getter: GetterT) -> ColumnProps:
        def _getter(dev: DeviceT):
            if dev in self._val:
                return self._val[dev]
            self._val[dev] = getter(dev)
            return self._val[dev]

        self.get = _getter
        return self

    def use_setter(self, setter: SetterT) -> ColumnProps:
        def _setter(dev: DeviceT, val: Any):
            setter(dev, self.dtype(val))
            del self._val[dev]

        self.editable = True
        self.set = _setter
        return self


def make_getter(attr: str, default=None) -> GetterT:
    def _getter(dev: DeviceT) -> Any:
        if hasattr(dev, attr):
            return getattr(dev, attr)()
        return default

    return _getter


def prop_getter(attr: str, default=None) -> GetterT:
    def _getter(dev: DeviceT) -> Any:
        return getattr(dev, attr, default)

    return _getter


def make_setter(attr: str) -> SetterT:
    def _setter(dev: DeviceT, val: Any):
        if hasattr(dev, attr):
            getattr(dev, attr)(val)

    return _setter


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


def get_device_type(dev: DeviceT) -> str:
    return DEVICE_TYPE[dev.device_type]


def get_wl_table(dongle: DeviceT):
    return dongle.wireless_table


def set_wl_table(dongle: DeviceT, idx: int, serial_hex: str):
    try:
        assert 0 <= 15 < idx, "Idx must be between 0 and 14"
        hw_id = int(serial_hex, 16)
        dongle.setSensorToDongle(idx, hw_id)
    except:
        ...


# a list of column props for rendering the device manager table
YOST_COL_PROPS: Tuple[ColumnProps, ...] = (
    ColumnProps("Nickname", str),
    ColumnProps("Serial Number", int).use_getter(prop_getter("serial_number_hex")),
    ColumnProps("Device Type", str).use_getter(get_device_type),
    ColumnProps("Battery", int).use_getter(make_getter("getBatteryPercentRemaining")),
    ColumnProps("Serial Port", str).use_getter(prop_getter("port_name")),
    ColumnProps("Channel", int)
    .use_getter(make_getter("getWirelessChannel"))
    .use_setter(make_setter("setWirelessChannel")),
    ColumnProps("Pan ID", int)
    .use_getter(make_getter("getWirelessPanID"))
    .use_setter(make_setter("setWirelessPanID")),
)


class TableModel(qc.QAbstractTableModel):
    """TableModel handles data for the device table
    This class simply uses the definition of `col_props` to render data.
    Modify the definitions of `col_props` to change the table structure.
    """

    def __init__(self, col_props: Tuple[ColumnProps]):
        super().__init__()

        self.devices: List = []
        self.col_props = col_props
        self.n_cols = len(col_props)

    def set_devices(self, devs: List):
        self.devices: List = list(set(devs))

    def rowCount(self, index=qc.QModelIndex()):
        """Returns the number of rows the model holds."""
        return len(self.devices)

    def columnCount(self, index=qc.QModelIndex()):
        """Returns the number of columns the model holds."""
        return self.n_cols

    def data(self, index, role=Qt.DisplayRole):
        """Depending on the index and role given, return data. If not
        returning data, return None (PySide equivalent of QT's
        "invalid QVariant").
        """
        col, row = index.column(), index.row()
        if (
            index.isValid()
            and 0 <= row < len(self.devices)
            and role == Qt.DisplayRole
            and col < self.n_cols
        ):
            return self.col_props[col].get(self.devices[row])

        return None

    def setData(self, index, value, role=Qt.EditRole):
        """Adjust the data (set it to <value>) depending on the given
        index and role.
        """
        col, row = index.column(), index.row()
        if (
            role == Qt.EditRole
            and index.isValid()
            and 0 <= row < len(self.devices)
            and col < self.n_cols
            and value
        ):
            self.col_props[col].set(self.devices[row], value)
            self.dataChanged.emit(index, index, 0)
            return True

        return False

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        """Set the headers to be displayed."""
        if (
            role == Qt.DisplayRole
            and orientation == Qt.Horizontal
            and section < self.n_cols
        ):
            return self.col_props[section].name

        return None

    def flags(self, index):
        """Set the item flags at the given index."""
        if not index.isValid():
            return Qt.ItemIsEnabled
        flags = qc.QAbstractTableModel.flags(self, index)
        if self.col_props[index.column()].editable:
            flags |= Qt.ItemIsEditable

        return Qt.ItemFlags(flags)


class DeviceManagerWidget(qw.QWidget, WindowMixin):
    """A GUI for DeviceManager.
    Can be embedded as a widget
    """

    def __init__(self, yost_device_manager: YostDeviceManager):
        super().__init__()
        self.yost_dm = yost_device_manager
        self.setMinimumSize(350, 200)

        main_layout = qw.QHBoxLayout(self)

        ### Device controls
        layout = qw.QVBoxLayout()
        main_layout.addLayout(layout)

        discover_btn = qw.QPushButton("&Discover devices")
        discover_btn.setStyleSheet("QPushButton { background-color: rgb(0,255,0); }")
        discover_btn.clicked.connect(self.s_discover_devices)

        tare_btn = qw.QPushButton(text="&Tare all devices")
        tare_btn.clicked.connect(self.s_tare_all)

        chart_btn = qw.QPushButton(text="Data &Charts")
        chart_btn.clicked.connect(self.s_data_charts)

        commit_btn = qw.QPushButton(text="Commit all settings")
        commit_btn.clicked.connect(self.s_commit_all)

        disconnect_btn = qw.QPushButton(text="Disconnect All")
        disconnect_btn.clicked.connect(self.s_disconnect_all)

        layout.addWidget(discover_btn)
        layout.addWidget(tare_btn)
        layout.addWidget(chart_btn)
        layout.addWidget(commit_btn)
        layout.addWidget(disconnect_btn)

        ### Setup nickname callbacks
        def nn_getter(dev: DeviceT):
            return yost_device_manager.get_device_name(dev.serial_number_hex)

        def nn_setter(dev: DeviceT, name):
            return yost_device_manager.set_device_name(dev.serial_number_hex, name)

        nickname_col = YOST_COL_PROPS[0]
        nickname_col.use_getter(nn_getter).use_setter(nn_setter)

        # Show device status
        self.yost_model = TableModel(YOST_COL_PROPS)
        self.yost_proxy_model = qc.QSortFilterProxyModel()
        self.yost_proxy_model.setSourceModel(self.yost_model)
        self.yost_proxy_model.setDynamicSortFilter(True)

        yost_tv = qw.QTableView()
        yost_tv.setModel(self.yost_proxy_model)
        yost_tv.setSortingEnabled(True)
        yost_tv.setSelectionBehavior(qw.QAbstractItemView.SelectRows)
        yost_tv.setSelectionMode(qw.QAbstractItemView.SingleSelection)
        yost_tv.horizontalHeader().setSectionResizeMode(qw.QHeaderView.Stretch)
        yost_tv.resizeColumnsToContents()
        yost_tv.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        yost_tv.setSizePolicy(qw.QSizePolicy.Expanding, qw.QSizePolicy.Expanding)

        main_layout.addWidget(yost_tv)

    @qc.Slot()
    def s_discover_devices(self):
        self.s_disconnect_all()
        with pg.BusyCursor():
            self.yost_dm.discover_devices()
        if not self.yost_dm.all_sensors:
            self.error_dialog(
                "No devices found. Make sure wired dongle/sensors are plugged in, "
                "and make sure wireless sensors are turned on, and use the same "
                "Channel and Pan ID as the dongle."
            )
        self.yost_model.set_devices(self.yost_dm.dongles + self.yost_dm.all_sensors)
        self.yost_proxy_model.invalidate()

    @qc.Slot()
    def s_tare_all(self):
        dm = self.yost_dm
        if not dm.has_sensors():
            return self.no_sensors_error()

        dm.tare_all_devices()

    @qc.Slot()
    def s_commit_all(self):
        for dev in self.yost_dm.all_sensors + self.yost_dm.dongles:
            dev.commitSettings()

    @qc.Slot()
    def s_data_charts(self):
        dm = self.yost_dm
        if not dm.has_sensors():
            return self.no_sensors_error()

        ## Start scope here.
        try:
            self._sw = ScopeWidget(dm, get_savedir("Scope"))
            self._sw.showMaximized()
        except Exception as e:
            _print(traceback.format_exc())
            dm.stop_stream()

    @qc.Slot()
    def s_disconnect_all(self):
        self.yost_dm.close_all_devices()
        self.yost_model.set_devices([])
        self.yost_proxy_model.invalidate()


if __name__ == "__main__":
    app = qw.QApplication()
    dm = YostDeviceManager()
    win = DeviceManagerWidget(dm)
    win.show()
    app.exec()
