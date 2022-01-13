import math
import time
import random
from typing import List, Tuple
import PySide6.QtGui as qg
import PySide6.QtWidgets as qw
import PySide6.QtCore as qc
from PySide6.QtCore import Qt
import numpy as np


def _print(*args):
    print("[Reaching]", *args)


class ReachingParams:
    # Reaching task params
    HOLD_TIME = 0.5
    TIME_LIMIT = 1.0
    TARGET_RADIUS = 40
    N_TARGETS = 8
    N_REPS = 3


def create_spin_box(
    SpinBoxType: qw.QAbstractSpinBox,
    value: float,
    step_size: float,
    range: Tuple[float, float],
):
    spin_box = SpinBoxType()
    spin_box.setSingleStep(step_size)
    spin_box.setRange(*range)
    spin_box.setValue(value)
    return spin_box


class ReachingConfig(qw.QDialog):
    def __init__(self):
        super().__init__()

        self.create_menu()
        self.create_form_group_box()

        main_layout = qw.QVBoxLayout()
        main_layout.setMenuBar(self._menu_bar)
        main_layout.addWidget(self._form_group_box)
        self.setLayout(main_layout)

        button_box = qw.QDialogButtonBox(
            qw.QDialogButtonBox.Ok | qw.QDialogButtonBox.Cancel
        )
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)

        main_layout.addWidget(button_box)

    def create_menu(self):
        self._menu_bar = qw.QMenuBar()
        self._file_menu = qw.QMenu("&File", self)
        self._exit_action = self._file_menu.addAction("E&xit")
        self._menu_bar.addMenu(self._file_menu)
        self._exit_action.triggered.connect(self.accept)

    def create_form_group_box(self):
        self._form_group_box = qw.QGroupBox("Form layout")
        layout = qw.QFormLayout()

        self.hold_time = create_spin_box(
            qw.QDoubleSpinBox, ReachingParams.HOLD_TIME, 0.1, (0, 1)
        )
        self.time_limit = create_spin_box(
            qw.QDoubleSpinBox, ReachingParams.TIME_LIMIT, 0.1, (0, 2)
        )
        self.n_targets = create_spin_box(
            qw.QSpinBox, ReachingParams.N_TARGETS, 1, (1, 10)
        )
        self.n_reps = create_spin_box(
            qw.QSpinBox, ReachingParams.N_REPS, 1, (1, 5)
        )

        layout.addRow(qw.QLabel("Hold time"), self.hold_time)
        layout.addRow(qw.QLabel("Time limit"), self.time_limit)
        layout.addRow(qw.QLabel("No. targets"), self.n_targets)
        layout.addRow(qw.QLabel("No. reps"), self.n_reps)
        self._form_group_box.setLayout(layout)

    def accept(self):
        ReachingParams.HOLD_TIME = self.hold_time.value()
        ReachingParams.TIME_LIMIT = self.time_limit.value()
        ReachingParams.N_TARGETS = self.n_targets.value()
        ReachingParams.N_REPS = self.n_reps.value()
        return super().accept()


class ReachingWidget(qw.QWidget, ReachingParams):
    GREEN = qg.QColor(0, 255, 0)
    RED = qg.QColor(255, 0, 0)
    BLUE = qg.QColor(0, 0, 255)
    CURSOR_COLOR = Qt.white
    INF = np.inf
    Config = ReachingConfig

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Reaching Task")

        self._init_ui()  # Inititialize user interface
        self._init_states()  # Initialize all states

        self.begin_task()
        _print("Initialized")

    def __del__(self):
        _print("Bye bye")

    def _init_ui(self):
        layout = qw.QGridLayout(self)
        self.setLayout(layout)

        # change background color
        p = self.palette()
        p.setColor(self.backgroundRole(), Qt.black)
        self.setPalette(p)

        # init top label
        self.top_label = l1 = qw.QLabel("Reaching", self)
        l1.setStyleSheet("QLabel { background-color: black; color: white; }")
        l1.setFont(qg.QFont("Arial", 18))
        layout.addWidget(l1, 0, 0, alignment=Qt.AlignTop | Qt.AlignLeft)

    def _init_states(self):
        self._running = False

        ### Cursor states
        # This is updated only by `mouseMoveEvent`,
        # read-only for `_update_reaching_state`
        self._cursor_pos = qc.QPoint(0, 0)
        self._last_cursor_inside = False
        self._target_acquired_time = self.INF
        self._target_created_time = self.INF

        ### Generate targets
        center, targets = self.generate_targets(
            n_targets=self.N_TARGETS, n_reps=self.N_REPS
        )
        self._target_base: qc.QPoint = center
        self._targets: List[qc.QPoint] = targets

        ### Current target states
        # updated only by `_update_reaching_state` and `_move_target`
        self._target_center: qc.QPoint = qc.QPoint(0, 0)
        self._target_color = self.GREEN

        ### Task history
        # Every new cursor event is recorded in cursor_history as
        #    (timestamp, (x, y))
        # When a target is reached, the task_history stores
        #    ((target_x, target_y), cursor_history)
        PointT = Tuple[int, int]
        CursorPointT = Tuple[float, PointT]
        CursorHistoryT = List[CursorPointT]
        self._cursor_history: CursorHistoryT = []
        self._task_history: List[Tuple[PointT, CursorHistoryT]] = []

        ### Timer to update states
        self.timer = qc.QTimer()
        self.timer.timeout.connect(self._update_task_state)

    def begin_task(self):
        """Start the task"""
        # Show popup window with instructions and countdown
        popup = qw.QWidget(self, Qt.SplashScreen | Qt.WindowStaysOnTopHint)
        layout = qw.QVBoxLayout()
        popup.setLayout(layout)

        l1 = qw.QLabel("Get Ready")
        layout.addWidget(l1)
        l1.setFont(qg.QFont("Arial", 18))
        l1.setFrameStyle(qw.QLabel.Panel)
        l1.setAlignment(Qt.AlignCenter)

        popup.setFixedSize(200, 100)
        popup.show()

        def begin():
            popup.close()
            self._begin_task()

        qc.QTimer.singleShot(1000, lambda: l1.setText("Starting in 3 s"))
        qc.QTimer.singleShot(2000, lambda: l1.setText("Starting in 2 s"))
        qc.QTimer.singleShot(3000, lambda: l1.setText("Starting in 1 s"))
        qc.QTimer.singleShot(4000, begin)

    def _begin_task(self):
        _print("Begin task")
        self._running = True
        self._task_begin_time = time.time()
        self.setMouseTracking(True)
        self.timer.start(1000 / 50)  # 50 Hz update rate
        self._move_target()
        self.update()

    def _finish_task(self):
        """Save task history, reinitialize states."""
        _print("Finish task")
        self._running = False
        self.setMouseTracking(False)
        self.timer.stop()

        # TODO: save task history
        h = self._task_history

        popup = qw.QWidget(self, Qt.SplashScreen | Qt.WindowStaysOnTopHint)
        layout = qw.QVBoxLayout()
        popup.setLayout(layout)

        l1 = qw.QLabel("Task Finished!")
        layout.addWidget(l1)
        l1.setFont(qg.QFont("Arial", 18))
        l1.setFrameStyle(qw.QLabel.Panel)
        l1.setAlignment(Qt.AlignCenter)

        popup.setFixedSize(200, 100)
        popup.show()

    @staticmethod
    def generate_targets(n_targets=8, n_reps=3) -> Tuple[qc.QPoint, List[qc.QPoint]]:
        # Init targets
        geo = qw.QApplication.primaryScreen().geometry()
        dist = geo.height() / 2 * 0.8
        center = qc.QPoint(geo.width() // 2, geo.height() // 2)
        targets: List[qc.QPoint] = []
        for i in range(n_targets):
            alpha = 2 * np.pi * i / n_targets
            c = center + qc.QPoint(dist * np.cos(alpha), dist * np.sin(alpha))
            targets.extend([c] * n_reps)
        random.shuffle(targets)
        return center, targets

    def _move_target(self):
        self._target_created_time = time.time()
        if self._target_center == self._target_base:
            self._target_center = self._targets.pop()
        else:
            self._target_center = self._target_base
        # _print(len(self._targets), "targets left")

    def paintEvent(self, event: qg.QPaintEvent):
        if self._running:
            painter = qg.QPainter(self)
            painter.setRenderHint(qg.QPainter.Antialiasing)
            # Paint target
            painter.setBrush(self._target_color)
            painter.drawEllipse(
                self._target_center, self.TARGET_RADIUS, self.TARGET_RADIUS
            )
            # # Paint cursor
            # painter.setBrush(self.CURSOR_COLOR)
            # painter.drawEllipse(self._cursor_pos, 5, 5)

        return super().paintEvent(event)

    def _update_task_state(self):
        """Check cursor states and decide whether to update the target"""
        now = time.time()
        if now - self._target_acquired_time > self.HOLD_TIME:
            # Cursor has been held inside target for enough time.
            # _print(f"Held for long enough ({self.HOLD_TIME}s). Moving target")

            # Save task history
            self._task_history.append(
                (
                    (self._target_center.x(), self._target_center.y()),
                    self._cursor_history,
                )
            )
            self._cursor_history = []

            # Check if task is over
            if len(self._targets) == 0:
                self._finish_task()
                self.update()
                return

            # Create a new target
            self._target_color = self.GREEN
            self._last_cursor_inside = False
            self._target_acquired_time = self.INF
            self._move_target()
            self.update()
        elif now - self._target_created_time > self.TIME_LIMIT:
            if self._target_color != self.RED and not self._last_cursor_inside:
                # _print(f"Failed to reach target within time limit ({self.TIME_LIMIT}s)")
                self._target_color = self.RED
                self.update()

    def update(self):
        now = time.time()
        # save cursor history
        self._cursor_history.append(
            (now - self._task_begin_time, self._cursor_pos.toTuple())
        )

        # update cursor states
        d = self._target_center - self._cursor_pos
        cursor_inside = math.hypot(d.x(), d.y()) < self.TARGET_RADIUS
        if cursor_inside:
            if not self._last_cursor_inside:
                self._target_acquired_time = now
        else:
            self._target_acquired_time = self.INF

        self._last_cursor_inside = cursor_inside
        self.top_label.setText(f"Reaching. Targets to reach: {len(self._targets)}")
        return super().update()

    def mouseMoveEvent(self, event: qg.QMouseEvent) -> None:
        "Callback for any cursor movement inside the widget"
        self._cursor_pos = event.pos()
        self.update()
        return super().mouseMoveEvent(event)
