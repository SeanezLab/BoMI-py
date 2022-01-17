from __future__ import annotations
from dataclasses import dataclass, field
from queue import Queue
from typing import Callable, Dict, List, NamedTuple, Optional, TypeVar
import PySide6.QtGui as qg
import PySide6.QtWidgets as qw
import PySide6.QtCore as qc
from PySide6.QtCore import Qt
import pyqtgraph as pg

from bomi.device_manager import DeviceManager, DeviceT
from bomi.scope_widget import ScopeWidget
from bomi.window_mixin import WindowMixin


def _print(*args):
    print("[DeviceManagerWidget]", *args)


T = TypeVar("T")


@dataclass
class ColumnProps:
    name: str
    type: Callable
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
            setter(dev, self.type(val))
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


def make_setter(attr: str) -> Callable[[DeviceT, T], bool]:
    def _setter(dev: DeviceT, val: T):
        if hasattr(dev, attr):
            success = getattr(dev, attr)(val)
            _print(dev.serial_number_hex, attr, val, "success" if success else "failed")
            return success
        return False

    return _setter


COL_PROPS: List[ColumnProps] = [
    ColumnProps("Serial Number", int).use_getter(lambda dev: dev.serial_number_hex),
    ColumnProps("Device Type", str).use_getter(lambda dev: dev.device_type),
    ColumnProps("Battery", int).use_getter(make_getter("getBatteryPercentRemaining")),
    ColumnProps("Serial Port", str).use_getter(
        lambda dev: dev.serial_port.port if dev.serial_port else None
    ),
    ColumnProps("WL Channel", int)
    .use_getter(make_getter("getWirelessChannel"))
    .use_setter(make_setter("setWirelessChannel")),
    ColumnProps("WL Pan ID", int)
    .use_getter(make_getter("getWirelessPanID"))
    .use_setter(make_setter("setWirelessPanID")),
]


class DeviceItem(NamedTuple):
    serial_hex: str
    type: str
    battery: int
    serial_port: str
    wl_channel: int
    wl_pan_id: int


class DeviceManagerWidget(qw.QWidget, WindowMixin):
    def __init__(self, device_manager: DeviceManager):
        super().__init__()
        self._dm = device_manager
        self.setMinimumSize(400, 70)

        main_layout = qw.QHBoxLayout()
        self.setLayout(main_layout)

        # Device controls
        layout = qw.QVBoxLayout()
        main_layout.addLayout(layout)

        btn1 = qw.QPushButton(text="Discover devices")
        btn1.clicked.connect(self.s_discover_devices)
        layout.addWidget(btn1)

        btn1 = qw.QPushButton(text="Tare all devices")
        btn1.clicked.connect(self.s_tare_all)
        layout.addWidget(btn1)

        btn1 = qw.QPushButton(text="Stream data")
        btn1.clicked.connect(self.s_stream_data)
        layout.addWidget(btn1)

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
        tv.horizontalHeader().setStretchLastSection(True)
        # tv.resizeColumnsToContents()
        tv.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        tv.setSizePolicy(qw.QSizePolicy.Expanding, qw.QSizePolicy.Expanding)

        main_layout.addWidget(tv)

    @qc.Slot()
    def s_discover_devices(self):
        with pg.BusyCursor():
            self._dm.discover_devices()
            self.table_model.set_devices(self._dm.sensor_list + self._dm.all_list)
            self.proxy_model.invalidate()

        _print(self._dm.status())

    @qc.Slot()
    def s_tare_all(self):
        dm = self._dm
        if not dm.has_sensors():
            return self.error_dialog(
                "No sensors available. Plug in the devices, then click on 'Discover devices'"
            )

        dm.tare_all_devices()

    @qc.Slot()
    def s_stream_data(self):
        dm = self._dm
        if not dm.has_sensors():
            return self.error_dialog(
                "No sensors available. Plug in the devices, then click on 'Discover devices'"
            )

        queue = Queue()
        dm.start_stream(queue)

        ## Start scope here.
        self._sw = sw = ScopeWidget(
            queue=queue, dims=3, close_callbacks=[dm.stop_stream]
        )
        sw.show()


class TableModel(qc.QAbstractTableModel):
    """TableModel handles data for the device table
    This class simply uses the definition of `DeviceItem` and `COL_PROPS` to render data.
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
        if COL_PROPS[index.column()].editable:
            return Qt.ItemFlags(
                qc.QAbstractTableModel.flags(self, index) | Qt.ItemIsEditable
            )
        return Qt.ItemFlags(qc.QAbstractTableModel.flags(self, index))


if __name__ == "__main__":
    app = qw.QApplication()
    dm = DeviceManager()
    win = DeviceManagerWidget(dm)
    win.show()
    app.exec()
