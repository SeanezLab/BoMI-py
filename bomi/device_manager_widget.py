from __future__ import annotations
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, TypeVar
import traceback
import PySide6.QtGui as qg
import PySide6.QtWidgets as qw
import PySide6.QtCore as qc
from PySide6.QtCore import Qt
import pyqtgraph as pg

from bomi.device_manager import YostDeviceManager, DeviceT, Packet
from bomi.scope_widget import ScopeWidget
from bomi.window_mixin import WindowMixin


def _print(*args):
    print("[DeviceManagerWidget]", *args)


T = TypeVar("T")


@dataclass
class ColumnProps:
    name: str
    dtype: Callable
    get: Optional[Callable[[DeviceT], T]] = None
    set: Optional[Callable[[DeviceT, T], T]] = None
    editable: bool = False
    _val: Dict[DeviceT, T] = field(default_factory=dict)

    def use_getter(self, getter: Callable[[DeviceT], T]) -> ColumnProps:
        def _getter(dev: DeviceT):
            if dev in self._val:
                return self._val[dev]
            self._val[dev] = getter(dev)
            return self._val[dev]

        self.get = _getter
        return self

    def use_setter(self, setter: Callable[[DeviceT, T], T]) -> ColumnProps:
        def _setter(dev: DeviceT, val: T):
            setter(dev, self.dtype(val))
            del self._val[dev]

        self.editable = True
        self.set = _setter
        return self


def make_getter(attr: str, default=None) -> Callable[[DeviceT], T]:
    def _getter(dev: DeviceT) -> T:
        if hasattr(dev, attr):
            return getattr(dev, attr)()
        return default

    return _getter


def prop_getter(attr: str, default=None):
    def _getter(dev: DeviceT) -> T:
        return getattr(dev, attr, default)

    return _getter


def make_setter(attr: str) -> Callable[[DeviceT, T], bool]:
    def _setter(dev: DeviceT, val: T):
        if hasattr(dev, attr):
            success = getattr(dev, attr)(val)
            _print(dev.serial_number_hex, attr, val, "success" if success else "failed")
            return success
        return False

    return _setter


DEVICE_TYPE = {
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


# COL_PROPS is a list of column props for rendering the device manager table
COL_PROPS: List[ColumnProps] = [
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
]


class TableModel(qc.QAbstractTableModel):
    """TableModel handles data for the device table
    This class simply uses the definition of `COL_PROPS` to render data.
    Modify the definitions of `COL_PROPS` to change the table structure.
    """

    def __init__(self, parent=None):
        super().__init__(parent)

        self.devices: List = []
        self._n_cols = len(COL_PROPS)

    def set_devices(self, devs: List):
        self.devices: List = list(set(devs))

    def rowCount(self, index=qc.QModelIndex()):
        """Returns the number of rows the model holds."""
        return len(self.devices)

    def columnCount(self, index=qc.QModelIndex()):
        """Returns the number of columns the model holds."""
        return self._n_cols

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
            and col < len(COL_PROPS)
        ):
            return COL_PROPS[col].get(self.devices[row])

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
            and col < len(COL_PROPS)
            and value
        ):
            COL_PROPS[col].set(self.devices[row], value)
            self.dataChanged.emit(index, index, 0)
            return True

        return False

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        """Set the headers to be displayed."""
        if (
            role == Qt.DisplayRole
            and orientation == Qt.Horizontal
            and section < len(COL_PROPS)
        ):
            return COL_PROPS[section].name

        return None

    def flags(self, index):
        """Set the item flags at the given index."""
        if not index.isValid():
            return Qt.ItemIsEnabled
        flags = qc.QAbstractTableModel.flags(self, index)
        if COL_PROPS[index.column()].editable:
            flags |= Qt.ItemIsEditable

        return Qt.ItemFlags(flags)


class DeviceManagerWidget(qw.QWidget, WindowMixin):
    """A GUI for DeviceManager.
    Can be embedded as a widget
    """

    def __init__(self, device_manager: YostDeviceManager):
        super().__init__()
        self.dm = device_manager
        self.setMinimumSize(350, 70)

        main_layout = qw.QHBoxLayout()
        self.setLayout(main_layout)

        # Device controls
        layout = qw.QVBoxLayout()
        main_layout.addLayout(layout)

        btn1 = qw.QPushButton(text="Discover devices")
        btn1.setStyleSheet("QPushButton { background-color: rgb(0,255,0); }")
        btn1.clicked.connect(self.s_discover_devices)
        layout.addWidget(btn1)

        btn1 = qw.QPushButton(text="Tare all devices")
        btn1.clicked.connect(self.s_tare_all)
        layout.addWidget(btn1)

        btn1 = qw.QPushButton(text="Data Charts")
        btn1.clicked.connect(self.s_data_charts)
        layout.addWidget(btn1)

        btn1 = qw.QPushButton(text="Commit all settings")
        btn1.clicked.connect(self.s_commit_all)
        layout.addWidget(btn1)

        btn1 = qw.QPushButton(text="Disconnect All")
        btn1.clicked.connect(self.s_disconnect_all)
        layout.addWidget(btn1)

        ### Setup nickname callbacks
        nickname_col = COL_PROPS[0]

        def nn_getter(dev: DeviceT):
            return device_manager.get_device_name(dev.serial_number_hex)

        def nn_setter(dev: DeviceT, name):
            return device_manager.set_device_name(dev.serial_number_hex, name)

        nickname_col.use_getter(nn_getter).use_setter(nn_setter)

        # Show device status
        self.table_model = TableModel()
        self.proxy_model = qc.QSortFilterProxyModel()
        self.proxy_model.setSourceModel(self.table_model)
        self.proxy_model.setDynamicSortFilter(True)

        tv = qw.QTableView()
        tv.setModel(self.proxy_model)
        tv.setSortingEnabled(True)
        tv.setSelectionBehavior(qw.QAbstractItemView.SelectRows)
        tv.setSelectionMode(qw.QAbstractItemView.SingleSelection)
        # tv.horizontalHeader().setStretchLastSection(True)
        tv.horizontalHeader().setSectionResizeMode(qw.QHeaderView.Stretch)
        tv.resizeColumnsToContents()
        tv.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        tv.setSizePolicy(qw.QSizePolicy.Expanding, qw.QSizePolicy.Expanding)

        main_layout.addWidget(tv)

    @qc.Slot()
    def s_discover_devices(self):
        self.s_disconnect_all()
        with pg.BusyCursor():
            self.dm.discover_devices()
        if not self.dm.all_sensors:
            self.error_dialog(
                "No devices found. Make sure wired dongle/sensors are plugged in, "
                "and make sure wireless sensors are turned on, and use the same "
                "Channel and Pan ID as the dongle."
            )
        self.table_model.set_devices(self.dm.dongles + self.dm.all_sensors)
        self.proxy_model.invalidate()

    @qc.Slot()
    def s_tare_all(self):
        dm = self.dm
        if not dm.has_sensors():
            return self.error_dialog(
                "No sensors available. Plug in the devices, then click on 'Discover devices'"
            )

        dm.tare_all_devices()

    @qc.Slot()
    def s_commit_all(self):
        for dev in self.dm.all_sensors + self.dm.dongles:
            dev.commitSettings()

    @qc.Slot()
    def s_data_charts(self):
        dm = self.dm
        if not dm.has_sensors():
            return self.error_dialog(
                "No sensors available. Plug in the devices, then click on 'Discover devices'"
            )

        ## Start scope here.
        try:
            self._sw = ScopeWidget(dm)
            self._sw.showMaximized()
        except Exception as e:
            _print(traceback.format_exc())
            dm.stop_stream()

    @qc.Slot()
    def s_disconnect_all(self):
        self.dm.close_all_devices()
        self.table_model.set_devices([])
        self.proxy_model.invalidate()


if __name__ == "__main__":
    app = qw.QApplication()
    dm = YostDeviceManager()
    win = DeviceManagerWidget(dm)
    win.show()
    app.exec()
