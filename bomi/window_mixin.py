import PySide6.QtWidgets as qw
import PySide6.QtGui as qg


class WindowMixin(object):
    def error_dialog(self, msg: str):
        "Display `msg` in a popup error dialog"
        if not hasattr(self, "_err_dialog"):
            self._err_dialog = qw.QErrorMessage()
            self._err_dialog.setWindowTitle("BoMI Error")

        self._err_dialog.showMessage(msg)

    def msg_dialog(self, msg: str) -> bool:
        "Display msg"
        return qw.QMessageBox.Yes == qw.QMessageBox.question(
            self, "BoMI Confirmation", msg, qw.QMessageBox.Yes | qw.QMessageBox.No
        )

    def no_yost_sensors_error(self): #adjust this, tell it to work without IMU Yost
        return self.error_dialog(
            "No Yost sensors available. Plug in the devices, then click on 'Discover devices'"
        )

    def start_widget(self, obj: qw.QWidget, maximize=True):
        "Run the given QWidget object in a new window"
        attr = str(type(obj))
        setattr(self, attr, obj)

        # Monkey patch QWidget's `closeEvent` to delete the object on close
        def closeEvent(event: qg.QCloseEvent):
            delattr(self, attr)
            obj._closeEvent(event)

        obj._closeEvent = obj.closeEvent
        obj.closeEvent = closeEvent

        if maximize:
            obj.showMaximized()
        else:
            obj.show()
