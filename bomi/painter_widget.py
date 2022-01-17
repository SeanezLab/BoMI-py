from typing import Optional, Tuple
import time
import PySide6.QtGui as qg
import PySide6.QtWidgets as qw
import PySide6.QtCore as qc
import pyqtgraph as pg
import pyqtgraph.opengl
import OpenGL.GL as GL
import numpy as np

SIZE = 32


class GLPainterItem(pg.opengl.GLGraphicsItem.GLGraphicsItem):
    def __init__(self, **kwds):
        super().__init__()
        glopts = kwds.pop("glOptions", "additive")
        self.setGLOptions(glopts)

    def compute_projection(self):
        modelview = GL.glGetDoublev(GL.GL_MODELVIEW_MATRIX)
        projection = GL.glGetDoublev(GL.GL_PROJECTION_MATRIX)
        mvp = projection.T @ modelview.T
        mvp = qg.QMatrix4x4(mvp.ravel().tolist())

        # note that QRectF.bottom() != QRect.bottom()
        rect = qc.QRectF(self.view().rect())
        ndc_to_viewport = qg.QMatrix4x4()
        ndc_to_viewport.viewport(
            rect.left(), rect.bottom(), rect.width(), -rect.height()
        )

        return ndc_to_viewport * mvp

    def paint(self):
        self.setupGLState()

        painter = qg.QPainter(self.view())
        self.draw(painter)
        painter.end()

    def draw(self, painter):
        painter.setPen(qc.Qt.GlobalColor.white)
        painter.setRenderHints(
            qg.QPainter.RenderHint.Antialiasing
            | qg.QPainter.RenderHint.TextAntialiasing
        )

        rect = self.view().rect()
        af = qc.Qt.AlignmentFlag

        painter.drawText(rect, af.AlignTop | af.AlignRight, "TR")
        painter.drawText(rect, af.AlignBottom | af.AlignLeft, "BL")
        painter.drawText(rect, af.AlignBottom | af.AlignRight, "BR")

        opts = self.view().cameraParams()
        lines = []
        center = opts["center"]
        lines.append(f"center : ({center.x():.1f}, {center.y():.1f}, {center.z():.1f})")
        for key in ["distance", "fov", "elevation", "azimuth"]:
            lines.append(f"{key} : {opts[key]:.1f}")
        xyz = self.view().cameraPosition()
        lines.append(f"xyz : ({xyz.x():.1f}, {xyz.y():.1f}, {xyz.z():.1f})")
        info = "\n".join(lines)
        painter.drawText(rect, af.AlignTop | af.AlignLeft, info)

        project = self.compute_projection()

        hsize = SIZE // 2
        for xi in range(-hsize, hsize + 1):
            for yi in range(-hsize, hsize + 1):
                if xi == -hsize and yi == -hsize:
                    # skip one corner for visual orientation
                    continue
                vec3 = qg.QVector3D(xi, yi, 0)
                pos = project.map(vec3).toPointF()
                painter.drawEllipse(pos, 1, 1)


class PainterWidget(pg.opengl.GLViewWidget):
    def __init__(self):
        super().__init__()
        self.setCameraPosition(distance=50, elevation=90, azimuth=0)

        self.griditem = griditem = pg.opengl.GLGridItem()
        griditem.setSize(SIZE, SIZE)
        griditem.setSpacing(1, 1)
        self.addItem(griditem)

        self.axisitem = axisitem = pg.opengl.GLAxisItem()
        axisitem.setSize(SIZE / 2, SIZE / 2, 1)
        self.addItem(axisitem)

        self.paintitem = paintitem = GLPainterItem()
        self.addItem(paintitem)
