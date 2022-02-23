from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional, Tuple, TypeVar
from dataclasses import dataclass, field

import PySide6.QtCore as qc
from PySide6.QtCore import Qt


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


T = TypeVar("T")
SetterT = Callable[[T, Any], None]
GetterT = Callable[[T], Any]


@dataclass
class ColumnProps:
    name: str
    dtype: Callable
    get: Optional[GetterT] = None
    set: Optional[SetterT] = None
    editable: bool = False
    _val: Dict[T, Any] = field(default_factory=dict)  # cache

    def use_getter(self, getter: GetterT) -> ColumnProps:
        def _getter(dev: T):
            if dev in self._val:
                return self._val[dev]
            self._val[dev] = getter(dev)
            return self._val[dev]

        self.get = _getter
        return self

    def use_setter(self, setter: SetterT) -> ColumnProps:
        def _setter(dev: T, val: Any):
            setter(dev, self.dtype(val))
            del self._val[dev]

        self.editable = True
        self.set = _setter
        return self


def make_getter(attr: str, default=None) -> GetterT:
    def _getter(dev: T) -> Any:
        if hasattr(dev, attr):
            return getattr(dev, attr)()
        return default

    return _getter


def prop_getter(attr: str, default=None) -> GetterT:
    def _getter(dev: T) -> Any:
        return getattr(dev, attr, default)

    return _getter


def make_setter(attr: str) -> SetterT:
    def _setter(dev: T, val: Any):
        if hasattr(dev, attr):
            getattr(dev, attr)(val)

    return _setter
