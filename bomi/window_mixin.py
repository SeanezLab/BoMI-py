import PySide6.QtWidgets as qw
import PySide6.QtCore as qc
import PySide6.QtGui as qg


class WindowMixin:
    def error_dialog(self, msg: str):
        "Display `msg` in a popup error dialog"
        if not hasattr(self, "_popup_window"):
            self._err_dialog = qw.QErrorMessage()
            self._err_dialog.setWindowTitle(f"BoMI Error")

        self._err_dialog.showMessage(msg)

    @qc.Slot()
    def start_widget(self, cls: qw.QWidget, maximize=True):
        "Run the given QWidget class in a new window"
        attr = str(cls)
        if not hasattr(self, attr):
            obj = cls()
            setattr(self, attr, obj)

            # when the window is close, remove the attribute stored in this parent class
            def closeEvent(event: qg.QCloseEvent):
                event.accept()
                delattr(self, attr)

            obj.closeEvent = closeEvent
            if maximize:
                obj.showMaximized()
            else:
                obj.show()