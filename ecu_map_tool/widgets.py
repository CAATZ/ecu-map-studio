from __future__ import annotations

import json
from typing import Iterable

import numpy as np
from PyQt5.QtCore import QByteArray, QMimeData, QSize, Qt, QRectF, pyqtSignal
from PyQt5.QtGui import QColor, QBrush, QKeySequence, QLinearGradient, QPainter, QPen
from PyQt5.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QStyledItemDelegate,
    QTabBar,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .model import MapData, MapValidationError, format_axis_label, format_number


VIRIDIS = (
    (0.00, QColor("#440154")),
    (0.25, QColor("#3b528b")),
    (0.50, QColor("#21918c")),
    (0.75, QColor("#5ec962")),
    (1.00, QColor("#fde725")),
)

DIVERGING = (
    (0.00, QColor("#2563eb")),
    (0.50, QColor("#263247")),
    (1.00, QColor("#ef4444")),
)


class ReadableTabBar(QTabBar):
    """Tab bar with extra width for high-DPI and semi-bold glyph rendering."""

    EXTRA_GLYPH_WIDTH = 18

    def tabSizeHint(self, index: int) -> QSize:  # noqa: N802 (Qt API)
        size = super().tabSizeHint(index)
        size.setWidth(size.width() + self.EXTRA_GLYPH_WIDTH)
        return size

    def minimumTabSizeHint(self, index: int) -> QSize:  # noqa: N802 (Qt API)
        return self.tabSizeHint(index)


class WheelSafeComboBox(QComboBox):
    """Leave mouse-wheel scrolling to the surrounding panel."""

    def wheelEvent(self, event) -> None:  # noqa: N802 (Qt API)
        event.ignore()


class ReadableTabWidget(QTabWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        bar = ReadableTabBar(self)
        bar.setElideMode(Qt.ElideNone)
        bar.setUsesScrollButtons(True)
        bar.setExpanding(False)
        bar.setDrawBase(False)
        bar.setFocusPolicy(Qt.NoFocus)
        self.setTabBar(bar)


def _interpolate_color(left: QColor, right: QColor, fraction: float) -> QColor:
    fraction = max(0.0, min(1.0, fraction))
    return QColor(
        round(left.red() + (right.red() - left.red()) * fraction),
        round(left.green() + (right.green() - left.green()) * fraction),
        round(left.blue() + (right.blue() - left.blue()) * fraction),
    )


def blend_color(base: QColor, overlay: QColor, fraction: float) -> QColor:
    return _interpolate_color(base, overlay, fraction)


def palette_color(value: float, minimum: float, maximum: float, diverging: bool) -> QColor:
    stops = DIVERGING if diverging else VIRIDIS
    if not np.isfinite(value):
        return QColor("#3a1f2b")
    if maximum <= minimum:
        position = 0.5
    elif diverging:
        extent = max(abs(minimum), abs(maximum))
        position = 0.5 if extent == 0 else 0.5 + 0.5 * value / extent
    else:
        position = (value - minimum) / (maximum - minimum)
    position = max(0.0, min(1.0, float(position)))

    for index in range(len(stops) - 1):
        left_position, left_color = stops[index]
        right_position, right_color = stops[index + 1]
        if left_position <= position <= right_position:
            local = (position - left_position) / (right_position - left_position)
            return _interpolate_color(left_color, right_color, local)
    return stops[-1][1]


def contrast_color(background: QColor) -> QColor:
    luminance = (
        0.2126 * background.redF() + 0.7152 * background.greenF() + 0.0722 * background.blueF()
    )
    return QColor("#07101b") if luminance > 0.56 else QColor("#f8fbff")


class HeatmapLegend(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.minimum = 0.0
        self.maximum = 1.0
        self.diverging = False
        self.setMinimumHeight(46)
        self.setMaximumHeight(46)

    def set_range(self, minimum: float, maximum: float, diverging: bool = False) -> None:
        self.minimum = float(minimum)
        self.maximum = float(maximum)
        self.diverging = diverging
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802 (Qt API)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        bar = QRectF(12, 7, max(20, self.width() - 24), 12)
        gradient = QLinearGradient(bar.left(), 0, bar.right(), 0)
        for position, color in DIVERGING if self.diverging else VIRIDIS:
            gradient.setColorAt(position, color)
        painter.setPen(QPen(QColor("#34435b"), 1))
        painter.setBrush(QBrush(gradient))
        painter.drawRoundedRect(bar, 4, 4)

        painter.setPen(QColor("#8e9cb1"))
        if self.diverging:
            extent = max(abs(self.minimum), abs(self.maximum))
            shown_minimum, shown_midpoint, shown_maximum = -extent, 0.0, extent
        else:
            shown_minimum = self.minimum
            shown_midpoint = (self.minimum + self.maximum) / 2.0
            shown_maximum = self.maximum
        minimum = format_number(shown_minimum, 6)
        maximum = format_number(shown_maximum, 6)
        midpoint = format_number(shown_midpoint, 6)
        painter.drawText(QRectF(12, 23, 100, 18), Qt.AlignLeft | Qt.AlignVCenter, minimum)
        painter.drawText(
            QRectF(self.width() / 2 - 50, 23, 100, 18),
            Qt.AlignCenter,
            midpoint,
        )
        painter.drawText(
            QRectF(self.width() - 112, 23, 100, 18),
            Qt.AlignRight | Qt.AlignVCenter,
            maximum,
        )


class TableZoomControls(QWidget):
    """Compact zoom controls shared by map and curve tables."""

    def __init__(self, table, parent=None) -> None:
        super().__init__(parent)
        self.table = table
        self.setObjectName("TableZoomBar")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 3, 8, 3)
        layout.setSpacing(5)
        label = QLabel("Table zoom")
        label.setObjectName("Muted")
        layout.addWidget(label)
        layout.addStretch(1)

        self.zoom_out_button = QPushButton("−")
        self.zoom_out_button.setToolTip("Zoom out (Ctrl+-)")
        self.zoom_out_button.clicked.connect(table.zoom_out)
        self.reset_button = QPushButton(f"{table.zoom_percent}%")
        self.reset_button.setToolTip("Reset table zoom to 100% (Ctrl+0)")
        self.reset_button.clicked.connect(lambda: table.set_zoom(100))
        self.zoom_in_button = QPushButton("+")
        self.zoom_in_button.setToolTip("Zoom in (Ctrl++)")
        self.zoom_in_button.clicked.connect(table.zoom_in)
        self.fit_button = QPushButton("Fit")
        self.fit_button.setToolTip("Fit all table cells inside the current viewport")
        self.fit_button.clicked.connect(table.fit_to_view)
        for button in (self.zoom_out_button, self.zoom_in_button):
            button.setFixedSize(28, 25)
        self.reset_button.setFixedSize(54, 25)
        self.fit_button.setFixedSize(48, 25)
        for button in (
            self.zoom_out_button,
            self.reset_button,
            self.zoom_in_button,
            self.fit_button,
        ):
            button.setObjectName("ZoomButton")
            layout.addWidget(button)
        table.zoomChanged.connect(lambda percent: self.reset_button.setText(f"{percent}%"))


class _MapCellDelegate(QStyledItemDelegate):
    def createEditor(self, parent, _option, _index):
        editor = QLineEdit(parent)
        editor.setFrame(False)
        editor.setAlignment(Qt.AlignCenter)
        editor.setStyleSheet("padding: 0 2px; border-radius: 0;")
        return editor

    def setEditorData(self, editor, index) -> None:
        editor.setText(str(index.data(Qt.EditRole)))
        editor.selectAll()

    def setModelData(self, editor, model, index) -> None:
        try:
            value = float(editor.text().strip().replace(",", "."))
        except ValueError:
            return
        view = self.parent()
        if np.isfinite(value) and isinstance(view, MapTableWidget):
            view.set_selected_value(value, edited_index=index)


class MapTableWidget(QTableWidget):
    CELL_MIME_TYPE = "application/x-ecu-map-studio-cells"
    pasteRequested = pyqtSignal()
    pasteRejected = pyqtSignal(str)
    dataEdited = pyqtSignal()
    zoomChanged = pyqtSignal(int)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._map_data: MapData | None = None
        self._mask: np.ndarray | None = None
        self._diverging = False
        self._decimals = 3
        self._editable = False
        self._updating = False
        self._base_column_width = 82
        self._base_row_height = 31
        self._base_header_width = 86
        self._base_font_size = max(8.0, self.font().pointSizeF())
        self._zoom_percent = 90

        self.setAlternatingRowColors(False)
        self.setItemDelegate(_MapCellDelegate(self))
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.setSelectionBehavior(QAbstractItemView.SelectItems)
        self.setShowGrid(True)
        self.setWordWrap(False)
        self.horizontalHeader().setSectionResizeMode(QHeaderView.Fixed)
        self.verticalHeader().setSectionResizeMode(QHeaderView.Fixed)
        self.horizontalHeader().setDefaultSectionSize(self._base_column_width)
        self.verticalHeader().setDefaultSectionSize(self._base_row_height)
        self.verticalHeader().setMinimumWidth(self._base_header_width)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
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
        column_width = max(44, round(self._base_column_width * scale))
        row_height = max(20, round(self._base_row_height * scale))
        self.horizontalHeader().setDefaultSectionSize(column_width)
        self.verticalHeader().setDefaultSectionSize(row_height)
        self.verticalHeader().setMinimumWidth(max(58, round(self._base_header_width * scale)))
        for column in range(self.columnCount()):
            self.setColumnWidth(column, column_width)
        for row in range(self.rowCount()):
            self.setRowHeight(row, row_height)
        font = self.font()
        font.setPointSizeF(max(7.0, self._base_font_size * scale))
        self.setFont(font)
        header_font = self.horizontalHeader().font()
        header_font.setPointSizeF(max(7.0, self._base_font_size * scale))
        self.horizontalHeader().setFont(header_font)
        self.verticalHeader().setFont(header_font)
        self.zoomChanged.emit(percent)

    def zoom_in(self) -> None:
        self.set_zoom(self._zoom_percent + 10)

    def zoom_out(self) -> None:
        self.set_zoom(self._zoom_percent - 10)

    def fit_to_view(self) -> None:
        if self.rowCount() < 1 or self.columnCount() < 1:
            return
        low, high, best = 50, 180, 50
        while low <= high:
            candidate = (low + high) // 2
            self.set_zoom(candidate, snap_to_step=False)
            # Two geometry passes settle both scrollbars after section sizes change.
            self.updateGeometries()
            self.updateGeometries()
            fits = (
                self.horizontalHeader().length() <= self.viewport().width()
                and self.verticalHeader().length() <= self.viewport().height()
            )
            if fits:
                best = candidate
                low = candidate + 1
            else:
                high = candidate - 1
        self.set_zoom(best, snap_to_step=False)
        self.updateGeometries()
        self.updateGeometries()

    def clear_map(self) -> None:
        self._updating = True
        self.clear()
        self.setRowCount(0)
        self.setColumnCount(0)
        self._map_data = None
        self._mask = None
        self._updating = False

    def set_map(
        self,
        map_data: MapData,
        extrapolated_mask: np.ndarray | None = None,
        *,
        diverging: bool = False,
        editable: bool = False,
        decimals: int = 3,
    ) -> None:
        self._updating = True
        self._map_data = map_data
        self._mask = (
            None if extrapolated_mask is None else np.asarray(extrapolated_mask, dtype=bool)
        )
        self._diverging = diverging
        self._decimals = decimals
        self._editable = editable

        self.clear()
        self.setRowCount(map_data.rows)
        self.setColumnCount(map_data.columns)
        self.setHorizontalHeaderLabels([format_axis_label(value) for value in map_data.x])
        self.setVerticalHeaderLabels([format_axis_label(value) for value in map_data.y])
        self.setEditTriggers(
            QAbstractItemView.DoubleClicked | QAbstractItemView.AnyKeyPressed
            if editable
            else QAbstractItemView.NoEditTriggers
        )

        for row in range(map_data.rows):
            for column in range(map_data.columns):
                value = float(map_data.z[row, column])
                item = QTableWidgetItem(f"{value:.{decimals}f}")
                item.setData(Qt.UserRole, value)
                item.setTextAlignment(Qt.AlignCenter)
                if not editable:
                    item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                self.setItem(row, column, item)
        self._updating = False
        self.set_zoom(self._zoom_percent)
        self.refresh_colors()

    def current_map(self) -> MapData:
        if self._map_data is None:
            raise MapValidationError("No source table has been loaded.")
        values = np.empty((self.rowCount(), self.columnCount()), dtype=float)
        for row in range(self.rowCount()):
            for column in range(self.columnCount()):
                item = self.item(row, column)
                if item is None or not item.text().strip():
                    raise MapValidationError(
                        f"Z cell at row {row + 1}, column {column + 1} is blank."
                    )
                try:
                    stored_value = item.data(Qt.UserRole)
                    values[row, column] = (
                        float(stored_value)
                        if stored_value is not None
                        else float(item.text().strip().replace(",", "."))
                    )
                except ValueError as exc:
                    raise MapValidationError(
                        f"Z cell at row {row + 1}, column {column + 1} is not a number."
                    ) from exc
        return MapData(
            self._map_data.x,
            self._map_data.y,
            values,
            name=self._map_data.name,
        )

    def refresh_colors(self) -> None:
        if self._map_data is None:
            return
        previous_updating = self._updating
        previous_blocked = self.signalsBlocked()
        self._updating = True
        self.blockSignals(True)
        try:
            values: list[float] = []
            for row in range(self.rowCount()):
                for column in range(self.columnCount()):
                    item = self.item(row, column)
                    try:
                        values.append(float(item.text().replace(",", ".")))
                    except (AttributeError, ValueError):
                        pass
            if not values:
                return
            minimum, maximum = min(values), max(values)
            amber = QColor("#f59e0b")
            for row in range(self.rowCount()):
                for column in range(self.columnCount()):
                    item = self.item(row, column)
                    try:
                        value = float(item.text().replace(",", "."))
                        color = palette_color(value, minimum, maximum, self._diverging)
                        outside = bool(self._mask is not None and self._mask[row, column])
                        if outside:
                            color = blend_color(color, amber, 0.36)
                            item.setToolTip(
                                "Extrapolated cell — outside at least one source-axis boundary."
                            )
                        else:
                            item.setToolTip("")
                        item.setBackground(QBrush(color))
                        item.setForeground(QBrush(contrast_color(color)))
                    except (AttributeError, ValueError):
                        item.setBackground(QBrush(QColor("#3a1f2b")))
                        item.setForeground(QBrush(QColor("#ffd1dc")))
        finally:
            self.blockSignals(previous_blocked)
            self._updating = previous_updating

    def selected_values_as_tsv(self) -> str:
        selected = self.selectedIndexes()
        if not selected:
            return ""
        rows = sorted({index.row() for index in selected})
        columns = sorted({index.column() for index in selected})
        selected_pairs = {(index.row(), index.column()) for index in selected}
        output: list[str] = []
        for row in rows:
            output.append(
                "\t".join(
                    self.item(row, column).text()
                    if (row, column) in selected_pairs and self.item(row, column)
                    else ""
                    for column in columns
                )
            )
        return "\r\n".join(output)

    def set_selected_value(self, value: float, *, edited_index=None) -> bool:
        if not self._editable or not np.isfinite(value):
            return False
        selected = sorted({(index.row(), index.column()) for index in self.selectedIndexes()})
        if edited_index is None:
            coordinates = selected
        else:
            coordinate = (edited_index.row(), edited_index.column())
            coordinates = selected if coordinate in selected and len(selected) > 1 else [coordinate]
        if not coordinates:
            return False
        changed = False
        previous_blocked = self.signalsBlocked()
        previous_updating = self._updating
        self._updating = True
        self.blockSignals(True)
        try:
            for row, column in coordinates:
                item = self.item(row, column)
                previous = item.data(Qt.UserRole)
                if previous is not None and float(previous) == value:
                    continue
                item.setText(f"{value:.{self._decimals}f}")
                item.setData(Qt.UserRole, value)
                changed = True
        finally:
            self.blockSignals(previous_blocked)
            self._updating = previous_updating
        if changed:
            self.refresh_colors()
            self.dataEdited.emit()
        return changed

    def copy_selected_cells(self) -> bool:
        selected = self.selectedIndexes()
        if not selected:
            return False
        rows = sorted({index.row() for index in selected})
        columns = sorted({index.column() for index in selected})
        row_offset = rows[0]
        column_offset = columns[0]
        selected_pairs = {(index.row(), index.column()) for index in selected}
        values: list[list[float | None]] = []
        for row in range(rows[0], rows[-1] + 1):
            output_row: list[float | None] = []
            for column in range(columns[0], columns[-1] + 1):
                if (row, column) not in selected_pairs:
                    output_row.append(None)
                    continue
                item = self.item(row, column)
                stored = item.data(Qt.UserRole) if item is not None else None
                try:
                    output_row.append(
                        float(stored)
                        if stored is not None
                        else float(item.text().strip().replace(",", "."))
                    )
                except (AttributeError, TypeError, ValueError):
                    output_row.append(None)
            values.append(output_row)

        payload = {
            "rows": rows[-1] - row_offset + 1,
            "columns": columns[-1] - column_offset + 1,
            "values": values,
        }
        mime = QMimeData()
        mime.setText(self.selected_values_as_tsv())
        mime.setData(
            self.CELL_MIME_TYPE,
            QByteArray(json.dumps(payload, separators=(",", ":")).encode("utf-8")),
        )
        QApplication.clipboard().setMimeData(mime)
        return True

    def paste_copied_cells(self) -> bool:
        if not self._editable:
            self.pasteRejected.emit("This table is read-only.")
            return False
        mime = QApplication.clipboard().mimeData()
        if not mime.hasFormat(self.CELL_MIME_TYPE):
            return False
        try:
            payload = json.loads(bytes(mime.data(self.CELL_MIME_TYPE)).decode("utf-8"))
            rows = int(payload["rows"])
            columns = int(payload["columns"])
            values = payload["values"]
            if rows < 1 or columns < 1 or len(values) != rows:
                raise ValueError
            if any(not isinstance(row, list) or len(row) != columns for row in values):
                raise ValueError
        except (KeyError, TypeError, ValueError, json.JSONDecodeError, UnicodeDecodeError):
            self.pasteRejected.emit("The copied cell block is invalid.")
            return False

        selected = self.selectedIndexes()
        start_row = min((index.row() for index in selected), default=self.currentRow())
        start_column = min((index.column() for index in selected), default=self.currentColumn())
        start_row = max(0, start_row)
        start_column = max(0, start_column)
        if start_row + rows > self.rowCount() or start_column + columns > self.columnCount():
            self.pasteRejected.emit(
                f"The {columns} × {rows} copied block does not fit from the selected cell."
            )
            return False

        normalized: list[list[float | None]] = []
        try:
            for row_values in values:
                normalized_row: list[float | None] = []
                for raw_value in row_values:
                    if raw_value is None:
                        normalized_row.append(None)
                        continue
                    value = float(raw_value)
                    if not np.isfinite(value):
                        raise ValueError
                    normalized_row.append(value)
                normalized.append(normalized_row)
        except (TypeError, ValueError):
            self.pasteRejected.emit("The copied block contains an invalid numeric value.")
            return False

        previous_blocked = self.signalsBlocked()
        self._updating = True
        self.blockSignals(True)
        changed = False
        pasted_cells: list[tuple[int, int]] = []
        try:
            for row_offset, row_values in enumerate(normalized):
                for column_offset, raw_value in enumerate(row_values):
                    if raw_value is None:
                        continue
                    value = raw_value
                    row = start_row + row_offset
                    column = start_column + column_offset
                    item = self.item(row, column)
                    previous = item.data(Qt.UserRole)
                    changed = changed or previous is None or float(previous) != value
                    item.setText(f"{value:.{self._decimals}f}")
                    item.setData(Qt.UserRole, value)
                    pasted_cells.append((row, column))
        finally:
            self.blockSignals(previous_blocked)
            self._updating = False
        self.refresh_colors()
        self.clearSelection()
        for row, column in pasted_cells:
            self.item(row, column).setSelected(True)
        if changed:
            self.dataEdited.emit()
        return True

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
            self.copy_selected_cells()
            event.accept()
            return
        if event.matches(QKeySequence.Paste):
            if not self.paste_copied_cells():
                mime = QApplication.clipboard().mimeData()
                if not mime.hasFormat(self.CELL_MIME_TYPE):
                    self.pasteRequested.emit()
            event.accept()
            return
        text = event.text()
        command_modifier = Qt.ControlModifier | Qt.AltModifier
        direct_value_key = (
            bool(text)
            and not (event.modifiers() & command_modifier)
            and (text.isdigit() or text in {"-", "+", ".", ","})
        )
        if direct_value_key and self._editable and self.currentIndex().isValid():
            if self.edit(self.currentIndex(), QAbstractItemView.AnyKeyPressed, event):
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
            item.setData(Qt.UserRole, float(item.text().strip().replace(",", ".")))
        except ValueError:
            item.setData(Qt.UserRole, None)
        finally:
            self._updating = False
        self.refresh_colors()
        self.dataEdited.emit()


class MapPanel(QWidget):
    def __init__(self, title: str, subtitle: str, parent=None) -> None:
        super().__init__(parent)
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

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
        root.addWidget(header)

        self.action_bar = QFrame()
        self.action_bar.setObjectName("MapActions")
        self.action_layout = QHBoxLayout(self.action_bar)
        self.action_layout.setContentsMargins(12, 5, 12, 5)
        self.action_layout.setSpacing(5)
        self.action_layout.addStretch(1)
        root.addWidget(self.action_bar)

        self.table = MapTableWidget()
        root.addWidget(self.table, 1)
        self.zoom_controls = TableZoomControls(self.table)
        root.addWidget(self.zoom_controls)
        self.legend = HeatmapLegend()
        root.addWidget(self.legend)

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

    def set_map(
        self,
        map_data: MapData,
        extrapolated_mask: np.ndarray | None = None,
        *,
        diverging: bool = False,
        editable: bool = False,
        decimals: int = 3,
    ) -> None:
        self.table.set_map(
            map_data,
            extrapolated_mask,
            diverging=diverging,
            editable=editable,
            decimals=decimals,
        )
        minimum, maximum = map_data.value_range
        self.legend.set_range(minimum, maximum, diverging)

    def clear_map(self) -> None:
        self.table.clear_map()
        self.set_badges([])
        self.legend.set_range(0.0, 1.0, False)


def card_frame() -> tuple[QFrame, QVBoxLayout]:
    card = QFrame()
    card.setObjectName("Card")
    layout = QVBoxLayout(card)
    layout.setContentsMargins(15, 15, 15, 15)
    layout.setSpacing(10)
    return card, layout


def section_header(step: int, title: str) -> QHBoxLayout:
    layout = QHBoxLayout()
    layout.setSpacing(9)
    pill = QLabel(str(step))
    pill.setObjectName("StepPill")
    pill.setAlignment(Qt.AlignCenter)
    label = QLabel(title)
    label.setObjectName("SectionTitle")
    layout.addWidget(pill)
    layout.addWidget(label)
    layout.addStretch(1)
    return layout
