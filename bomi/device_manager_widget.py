from queue import Queue
from typing import List, NamedTuple
import PySide6.QtGui as qg
import PySide6.QtWidgets as qw
import PySide6.QtCore as qc
from PySide6.QtCore import Qt
import pyqtgraph as pg

from bomi.device_manager import DeviceManager
from bomi.scope_widget import ScopeWidget
from bomi.window_mixin import WindowMixin


def _print(*args):
    print("[DeviceManagerWidget]", *args)


class DeviceItem(NamedTuple):
    serial_hex: str
    type: str
    battery: int


HEADERS = ["Serial Number", "Device Type", "Battery"]


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

        self.devices: List[DeviceItem] = [
            DeviceItem(serial_hex="device1", type="WL", battery=99),
            DeviceItem(serial_hex="device2", type="WL", battery=98),
        ]

    @qc.Slot()
    def s_discover_devices(self):
        with pg.BusyCursor():
            self._dm.discover_devices()

            bat = self._dm.get_battery()

            devs = []
            for sensor, b in zip(self._dm.sensor_list, bat):
                d = DeviceItem(
                    serial_hex=sensor.serial_number_hex,
                    type=sensor.device_type,
                    battery=b,
                )
                devs.append(d)

            self.table_model.set_devices(devs)
            self.proxy_model.invalidate()

        _print(self._dm.status())

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
            queue=queue, dims=4, close_callbacks=[dm.stop_stream]
        )
        sw.show()


class TableModel(qc.QAbstractTableModel):
    """TableModel handles data for the device table
    This class simply uses the definition of `DeviceItem` and `HEADERS` to render data.
    Modify those two definitions to change the table structure.
    """

    def __init__(self, parent=None):
        super().__init__(parent)

        self.devices: List[DeviceItem] = []
        self._n_cols = len(HEADERS)

    def set_devices(self, devs: List[DeviceItem]):
        self.devices: List[DeviceItem] = devs

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
        if (
            index.isValid()
            and 0 <= index.row() < len(self.devices)
            and role == Qt.DisplayRole
            and index.column() < len(HEADERS)
        ):
            dev = self.devices[index.row()]
            return dev[index.column()]

        return None

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        """Set the headers to be displayed."""
        if (
            role == Qt.DisplayRole
            and orientation == Qt.Horizontal
            and section < len(HEADERS)
        ):
            return HEADERS[section]

        return None

    def insertRows(self, position, rows=1, index=qc.QModelIndex()):
        """Insert a row into the model."""
        self.beginInsertRows(qc.QModelIndex(), position, position + rows - 1)

        for row in range(rows):
            self.devices.insert(
                position + row,
                DeviceItem(serial_hex="New device", type="Unknown", battery=-1),
            )

        self.endInsertRows()
        return True

    def removeRows(self, position, rows=1, index=qc.QModelIndex()):
        """Remove a row from the model."""
        self.beginRemoveRows(qc.QModelIndex(), position, position + rows - 1)

        del self.devices[position : position + rows]

        self.endRemoveRows()
        return True

    def flags(self, index):
        """Set the item flags at the given index."""
        if not index.isValid():
            return Qt.ItemIsEnabled
        return Qt.ItemFlags(qc.QAbstractTableModel.flags(self, index))


if __name__ == "__main__":
    app = qw.QApplication()
    dm = DeviceManager()
    win = DeviceManagerWidget(dm)
    win.show()
    app.exec()
