from __future__ import annotations

from typing import Iterable

import numpy as np
from PyQt5.QtCore import QPointF, QRectF, Qt, pyqtSignal
from PyQt5.QtGui import (
    QBrush,
    QColor,
    QKeySequence,
    QPainter,
    QPainterPath,
    QPen,
)
from PyQt5.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .model import CurveData, MapValidationError, format_axis_label, format_number
from .widgets import HeatmapLegend, TableZoomControls, contrast_color, palette_color


class CurvePlotWidget(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.curve: CurveData | None = None
        self.extrapolated_mask: np.ndarray | None = None
        self.selected_mask: np.ndarray | None = None
        self.diverging = False
        self.setMinimumHeight(260)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

    def set_curve(
        self,
        curve: CurveData,
        extrapolated_mask: np.ndarray | None = None,
        *,
        diverging: bool = False,
    ) -> None:
        self.curve = curve
        self.extrapolated_mask = (
            None
            if extrapolated_mask is None
            else np.asarray(extrapolated_mask, dtype=bool).reshape(-1)
        )
        self.selected_mask = np.zeros(curve.size, dtype=bool)
        self.diverging = diverging
        self.update()

    def set_selected(self, indexes: Iterable[int]) -> None:
        if self.curve is None:
            return
        self.selected_mask = np.zeros(self.curve.size, dtype=bool)
        for index in indexes:
            if 0 <= index < self.curve.size:
                self.selected_mask[index] = True
        self.update()

    def clear_curve(self) -> None:
        self.curve = None
        self.extrapolated_mask = None
        self.selected_mask = None
        self.diverging = False
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802 (Qt API)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.fillRect(self.rect(), QColor("#0a101b"))
        if self.curve is None:
            painter.setPen(QColor("#738198"))
            painter.drawText(self.rect(), Qt.AlignCenter, "Paste or create a 2D curve to begin")
            return

        left, right, top, bottom = 66.0, 24.0, 22.0, 42.0
        plot = QRectF(
            left,
            top,
            max(20.0, self.width() - left - right),
            max(20.0, self.height() - top - bottom),
        )
        x_min, x_max = float(np.min(self.curve.x)), float(np.max(self.curve.x))
        y_min, y_max = self.curve.value_range
        if self.diverging:
            extent = max(abs(y_min), abs(y_max), np.finfo(float).eps)
            y_min, y_max = -extent, extent
        elif y_max <= y_min:
            padding = max(abs(y_min) * 0.05, 1.0)
            y_min -= padding
            y_max += padding
        else:
            padding = (y_max - y_min) * 0.10
            y_min -= padding
            y_max += padding

        def point(x_value: float, y_value: float) -> QPointF:
            x_fraction = 0.5 if x_max == x_min else (x_value - x_min) / (x_max - x_min)
            y_fraction = (y_value - y_min) / (y_max - y_min)
            return QPointF(
                plot.left() + x_fraction * plot.width(),
                plot.bottom() - y_fraction * plot.height(),
            )

        painter.setPen(QPen(QColor("#223047"), 1))
        for step in range(6):
            fraction = step / 5.0
            x_position = plot.left() + fraction * plot.width()
            y_position = plot.bottom() - fraction * plot.height()
            painter.drawLine(QPointF(x_position, plot.top()), QPointF(x_position, plot.bottom()))
            painter.drawLine(QPointF(plot.left(), y_position), QPointF(plot.right(), y_position))

        painter.setPen(QColor("#8e9cb1"))
        painter.drawText(
            QRectF(2, plot.top() - 8, left - 10, 20),
            Qt.AlignRight | Qt.AlignVCenter,
            format_number(y_max, 6),
        )
        painter.drawText(
            QRectF(2, plot.bottom() - 10, left - 10, 20),
            Qt.AlignRight | Qt.AlignVCenter,
            format_number(y_min, 6),
        )
        painter.drawText(
            QRectF(plot.left(), plot.bottom() + 10, 120, 22),
            Qt.AlignLeft | Qt.AlignVCenter,
            format_number(x_min, 7),
        )
        painter.drawText(
            QRectF(plot.right() - 120, plot.bottom() + 10, 120, 22),
            Qt.AlignRight | Qt.AlignVCenter,
            format_number(x_max, 7),
        )

        path = QPainterPath()
        for index, (x_value, value) in enumerate(zip(self.curve.x, self.curve.values)):
            position = point(float(x_value), float(value))
            if index == 0:
                path.moveTo(position)
            else:
                path.lineTo(position)
        painter.setPen(QPen(QColor("#72e2eb"), 2.3))
        painter.setBrush(Qt.NoBrush)
        painter.drawPath(path)

        minimum, maximum = self.curve.value_range
        for index, (x_value, value) in enumerate(zip(self.curve.x, self.curve.values)):
            position = point(float(x_value), float(value))
            outside = bool(self.extrapolated_mask is not None and self.extrapolated_mask[index])
            selected = bool(self.selected_mask is not None and self.selected_mask[index])
            color = (
                QColor("#f59e0b")
                if outside
                else palette_color(float(value), minimum, maximum, self.diverging)
            )
            radius = 6.0 if selected else 4.2
            if selected:
                painter.setPen(QPen(QColor("#ffffff"), 2))
            else:
                painter.setPen(QPen(QColor("#09111e"), 1))
            painter.setBrush(QBrush(color))
            painter.drawEllipse(position, radius, radius)


class CurveTableWidget(QTableWidget):
    pasteRequested = pyqtSignal()
    dataEdited = pyqtSignal()
    zoomChanged = pyqtSignal(int)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._curve: CurveData | None = None
        self._mask: np.ndarray | None = None
        self._diverging = False
        self._editable = False
        self._updating = False
        self._base_column_width = 100
        self._base_row_height = 34
        self._base_font_size = max(8.0, self.font().pointSizeF())
        self._zoom_percent = 90

        self.setRowCount(1)
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.setSelectionBehavior(QAbstractItemView.SelectItems)
        self.horizontalHeader().setSectionResizeMode(QHeaderView.Fixed)
        self.horizontalHeader().setDefaultSectionSize(self._base_column_width)
        self.verticalHeader().setSectionResizeMode(QHeaderView.Fixed)
        self.verticalHeader().setDefaultSectionSize(self._base_row_height)
        self.setVerticalHeaderLabels(["Value"])
        self.setMaximumHeight(104)
        self.setMinimumHeight(94)
        self.itemChanged.connect(self._item_changed)
        self.set_zoom(self._zoom_percent)

    @property
    def zoom_percent(self) -> int:
        return self._zoom_percent

    def set_zoom(self, percent: int, *, snap_to_step: bool = True) -> None:
        if snap_to_step:
            percent = int(round(percent / 10.0) * 10)
        percent = max(50, min(180, int(percent)))
        self._zoom_percent = percent
        scale = percent / 100.0
        column_width = max(50, round(self._base_column_width * scale))
        row_height = max(22, round(self._base_row_height * scale))
        self.horizontalHeader().setDefaultSectionSize(column_width)
        self.verticalHeader().setDefaultSectionSize(row_height)
        for column in range(self.columnCount()):
            self.setColumnWidth(column, column_width)
        self.setRowHeight(0, row_height)
        font = self.font()
        font.setPointSizeF(max(7.0, self._base_font_size * scale))
        self.setFont(font)
        header_font = self.horizontalHeader().font()
        header_font.setPointSizeF(max(7.0, self._base_font_size * scale))
        self.horizontalHeader().setFont(header_font)
        self.verticalHeader().setFont(header_font)
        preferred_height = max(76, row_height + 58)
        self.setMinimumHeight(preferred_height)
        self.setMaximumHeight(preferred_height + 10)
        self.zoomChanged.emit(percent)

    def zoom_in(self) -> None:
        self.set_zoom(self._zoom_percent + 10)

    def zoom_out(self) -> None:
        self.set_zoom(self._zoom_percent - 10)

    def fit_to_view(self) -> None:
        if self.columnCount() < 1:
            return
        low, high, best = 50, 180, 50
        while low <= high:
            candidate = (low + high) // 2
            self.set_zoom(candidate, snap_to_step=False)
            self.updateGeometries()
            self.updateGeometries()
            if self.horizontalHeader().length() <= self.viewport().width():
                best = candidate
                low = candidate + 1
            else:
                high = candidate - 1
        self.set_zoom(best, snap_to_step=False)
        self.updateGeometries()
        self.updateGeometries()

    def set_curve(
        self,
        curve: CurveData,
        extrapolated_mask: np.ndarray | None = None,
        *,
        diverging: bool = False,
        editable: bool = False,
        decimals: int = 3,
    ) -> None:
        self._updating = True
        self.blockSignals(True)
        try:
            self._curve = curve
            self._mask = (
                None
                if extrapolated_mask is None
                else np.asarray(extrapolated_mask, dtype=bool).reshape(-1)
            )
            self._diverging = diverging
            self._editable = editable
            self.clear()
            self.setRowCount(1)
            self.setColumnCount(curve.size)
            self.setVerticalHeaderLabels(["Value"])
            self.setHorizontalHeaderLabels([format_axis_label(value) for value in curve.x])
            self.setEditTriggers(
                QAbstractItemView.DoubleClicked | QAbstractItemView.EditKeyPressed
                if editable
                else QAbstractItemView.NoEditTriggers
            )
            for column, value in enumerate(curve.values):
                item = QTableWidgetItem(f"{float(value):.{decimals}f}")
                item.setData(Qt.UserRole, float(value))
                item.setTextAlignment(Qt.AlignCenter)
                if not editable:
                    item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                self.setItem(0, column, item)
        finally:
            self.blockSignals(False)
            self._updating = False
        self.set_zoom(self._zoom_percent)
        self.refresh_colors()

    def clear_curve(self) -> None:
        self._updating = True
        previous = self.signalsBlocked()
        self.blockSignals(True)
        try:
            self.clear()
            self.setRowCount(1)
            self.setColumnCount(0)
            self.setVerticalHeaderLabels(["Value"])
            self._curve = None
            self._mask = None
            self._diverging = False
            self._editable = False
        finally:
            self.blockSignals(previous)
            self._updating = False

    def current_curve(self) -> CurveData:
        if self._curve is None:
            raise MapValidationError("No 2D source curve has been loaded.")
        values = np.empty(self.columnCount(), dtype=float)
        for column in range(self.columnCount()):
            item = self.item(0, column)
            if item is None or not item.text().strip():
                raise MapValidationError(f"Curve value {column + 1} is blank.")
            stored = item.data(Qt.UserRole)
            try:
                values[column] = (
                    float(stored) if stored is not None else float(item.text().replace(",", "."))
                )
            except ValueError as exc:
                raise MapValidationError(f"Curve value {column + 1} is not numeric.") from exc
        return CurveData(self._curve.x, values, name=self._curve.name)

    def refresh_colors(self) -> None:
        if self._curve is None:
            return
        previous = self.signalsBlocked()
        self.blockSignals(True)
        try:
            display_values = []
            for column in range(self.columnCount()):
                try:
                    display_values.append(float(self.item(0, column).text().replace(",", ".")))
                except (AttributeError, ValueError):
                    pass
            if not display_values:
                return
            minimum, maximum = min(display_values), max(display_values)
            for column in range(self.columnCount()):
                item = self.item(0, column)
                try:
                    value = float(item.text().replace(",", "."))
                    outside = bool(self._mask is not None and self._mask[column])
                    color = (
                        QColor("#a36a18")
                        if outside
                        else palette_color(value, minimum, maximum, self._diverging)
                    )
                    item.setBackground(QBrush(color))
                    item.setForeground(QBrush(contrast_color(color)))
                    item.setToolTip(
                        "Extrapolated point — outside the source-axis range." if outside else ""
                    )
                except (AttributeError, ValueError):
                    item.setBackground(QBrush(QColor("#3a1f2b")))
        finally:
            self.blockSignals(previous)

    def selected_columns(self) -> list[int]:
        return sorted({index.column() for index in self.selectedIndexes()})

    def select_mask(self, mask: np.ndarray) -> None:
        self.clearSelection()
        for column in np.flatnonzero(np.asarray(mask, dtype=bool)):
            self.item(0, int(column)).setSelected(True)

    def keyPressEvent(self, event) -> None:  # noqa: N802 (Qt API)
        if event.modifiers() & Qt.ControlModifier:
            if event.key() in (Qt.Key_Plus, Qt.Key_Equal):
                self.zoom_in()
                event.accept()
                return
            if event.key() == Qt.Key_Minus:
                self.zoom_out()
                event.accept()
                return
            if event.key() == Qt.Key_0:
                self.set_zoom(100)
                event.accept()
                return
        if event.matches(QKeySequence.Copy):
            columns = self.selected_columns()
            if columns:
                QApplication.clipboard().setText(
                    "\t".join(self.item(0, column).text() for column in columns)
                )
            event.accept()
            return
        if event.matches(QKeySequence.Paste):
            self.pasteRequested.emit()
            event.accept()
            return
        super().keyPressEvent(event)

    def wheelEvent(self, event) -> None:  # noqa: N802 (Qt API)
        if event.modifiers() & Qt.ControlModifier:
            self.zoom_in() if event.angleDelta().y() > 0 else self.zoom_out()
            event.accept()
            return
        super().wheelEvent(event)

    def _item_changed(self, item: QTableWidgetItem) -> None:
        if self._updating or not self._editable:
            return
        self._updating = True
        try:
            item.setData(Qt.UserRole, float(item.text().replace(",", ".")))
        except ValueError:
            item.setData(Qt.UserRole, None)
        finally:
            self._updating = False
        self.refresh_colors()
        self.dataEdited.emit()


class CurvePanel(QWidget):
    def __init__(self, title: str, subtitle: str, parent=None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        header = QFrame()
        header.setObjectName("MapHeader")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(12, 10, 12, 10)
        header_layout.setSpacing(7)
        text_layout = QVBoxLayout()
        text_layout.setSpacing(2)
        self.title_label = QLabel(title)
        self.title_label.setObjectName("SectionTitle")
        self.subtitle_label = QLabel(subtitle)
        self.subtitle_label.setObjectName("Muted")
        text_layout.addWidget(self.title_label)
        text_layout.addWidget(self.subtitle_label)
        header_layout.addLayout(text_layout, 1)
        self.badge_layout = QHBoxLayout()
        self.badge_layout.setSpacing(4)
        header_layout.addLayout(self.badge_layout)
        layout.addWidget(header)

        self.action_bar = QFrame()
        self.action_bar.setObjectName("MapActions")
        self.action_layout = QHBoxLayout(self.action_bar)
        self.action_layout.setContentsMargins(12, 5, 12, 5)
        self.action_layout.setSpacing(5)
        self.action_layout.addStretch(1)
        layout.addWidget(self.action_bar)

        self.plot = CurvePlotWidget()
        layout.addWidget(self.plot, 1)
        self.table = CurveTableWidget()
        layout.addWidget(self.table)
        self.zoom_controls = TableZoomControls(self.table)
        layout.addWidget(self.zoom_controls)
        self.legend = HeatmapLegend()
        layout.addWidget(self.legend)
        self.table.itemSelectionChanged.connect(self._selection_changed)

    def add_action(self, widget: QWidget) -> None:
        self.action_layout.addWidget(widget)

    def set_badges(self, badges: Iterable[tuple[str, bool]]) -> None:
        while self.badge_layout.count():
            item = self.badge_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        for text, warning in badges:
            label = QLabel(text)
            label.setObjectName("WarningBadge" if warning else "Badge")
            self.badge_layout.addWidget(label)

    def set_curve(
        self,
        curve: CurveData,
        extrapolated_mask: np.ndarray | None = None,
        *,
        diverging: bool = False,
        editable: bool = False,
        decimals: int = 3,
    ) -> None:
        self.plot.set_curve(curve, extrapolated_mask, diverging=diverging)
        self.table.set_curve(
            curve,
            extrapolated_mask,
            diverging=diverging,
            editable=editable,
            decimals=decimals,
        )
        minimum, maximum = curve.value_range
        self.legend.set_range(minimum, maximum, diverging)

    def clear_curve(self) -> None:
        self.plot.clear_curve()
        self.table.clear_curve()
        self.set_badges([])
        self.legend.set_range(0.0, 1.0, False)

    def _selection_changed(self) -> None:
        self.plot.set_selected(self.table.selected_columns())
