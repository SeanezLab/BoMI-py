import math
from typing import Optional, Tuple
import time
import PySide6.QtGui as qg
import PySide6.QtWidgets as qw
import PySide6.QtCore as qc
import pyqtgraph as pg
import numpy as np


class DragRect(qw.QWidget):
    def __init__(self):
        super().__init__()
        # self.setGeometry(30, 30, 600, 400)
        self.resize(600, 400)
        self.begin = qc.QPoint()
        self.end = qc.QPoint()
        self.show()

    def paintEvent(self, event):
        qp = qg.QPainter(self)
        br = qg.QBrush(qg.QColor(100, 10, 10, 40))
        qp.setBrush(br)
        qp.drawRect(qc.QRect(self.begin, self.end))

    def mousePressEvent(self, event):
        self.begin = event.pos()
        self.end = event.pos()
        self.update()

    def mouseMoveEvent(self, event):
        self.end = event.pos()
        self.update()

    def mouseReleaseEvent(self, event):
        self.begin = event.pos()
        self.end = event.pos()
        self.update()


class _ReachingTarget(qw.QGraphicsItem):
    def __init__(self):
        super().__init__()

        self.color = qg.QColor(100, 100, 0)

    def paint(self, painter: qg.QPainter, option, widget):
        painter.setBrush(self.color)
        painter.drawEllipse(-10, -20, 20, 40)


class _ReachingWidget(qw.QGraphicsView):
    def __init__(self, parent=None):
        super().__init__(parent)
        print("reaching init")

        self.scene = scene = qw.QGraphicsScene()
        scene.setSceneRect(-300, -300, 600, 600)
        scene.setItemIndexMethod(qw.QGraphicsScene.NoIndex)

        target = _ReachingTarget()
        target.setPos(50, 50)
        scene.addItem(target)

        self.setScene(scene)
        self.setBackgroundBrush(qg.QColor(0, 0, 0))
        self.setRenderHint(qg.QPainter.Antialiasing)
        self.resize(400, 300)

        # self.timer = qc.QTimer()
        # self.timer.timeout.connect(self.scene.advance)
        # self.timer.start(1000 / 33)
        print("reaching init done")


class ReachingWidget(qw.QWidget):
    GREEN = qg.QColor(0, 255, 0)
    RED = qg.QColor(255, 0, 0)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.resize(800, 500)
        self.setWindowTitle("Reaching Exercise")

        layout = qw.QGridLayout()
        self.setLayout(layout)

        # self.l1 = qw.QLabel("Label")
        # layout.addChildWidget(self.l1)

        # self.timer = qc.QTimer()
        # self.timer.timeout.connect(self._update)
        # self.timer.start(1000)

        self._center = qc.QPoint(50, 50)
        self._r = 50
        self.newTarget()
        self._last_time = time.time()

        self.setMouseTracking(True)

    def newTarget(self):
        geo = self.geometry()
        r = self._r
        y = np.random.randint(r, geo.height() - r)
        x = np.random.randint(r, geo.width() - r)
        self._center = qc.QPoint(x, y)

    def paintEvent(self, _: qg.QPaintEvent):
        qp = qg.QPainter(self)
        qp.setRenderHint(qg.QPainter.Antialiasing)
        qp.setBrush(self.GREEN)
        qp.drawEllipse(self._center, self._r, self._r)

    @staticmethod
    def cursorInside(p1: qc.QPoint, p2: qc.QPoint, r: int):
        d = p1 - p2
        return math.hypot(d.x(), d.y()) < r

    def mouseMoveEvent(self, event: qg.QMouseEvent) -> None:
        pos = event.pos()

        if self.cursorInside(pos, self._center, self._r):
            self.newTarget()

        self.update()
        return super().mouseMoveEvent(event)

    def _update(self):
        # fps = self.getCursorPollFPS()
        # self.l1.setValue(fps)
        ...
