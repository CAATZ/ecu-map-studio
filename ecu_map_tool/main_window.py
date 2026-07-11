from __future__ import annotations

from pathlib import Path

import numpy as np
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QKeySequence
from PyQt5.QtWidgets import (
    QAction,
    QApplication,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QSplitter,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from .clipboard import (
    ClipboardFormatError,
    format_excel_table,
    format_romraider_table,
    parse_clipboard,
)
from .interpolation import (
    EXTRAPOLATION_LABELS,
    METHOD_LABELS,
    ResampleResult,
    resample_map,
)
from .features import (
    MATH_OPERATIONS,
    MapComparison,
    apply_map_math,
    build_safety_report,
    compare_maps,
    merge_comparison,
)
from .history import UndoHistory
from .model import (
    MapData,
    MapValidationError,
    axis_to_text,
    collapse_duplicate_map,
    format_number,
    generate_even_axis,
    parse_axis_text,
    parse_map_axis_text,
    parse_number_text,
)
from .smoothing import detect_anomalies, repair_selected_region, smooth_entire_table
from .project import (
    load_project,
    map_from_dict,
    map_result_from_dict,
    map_result_to_dict,
    map_to_dict,
    save_project,
)
from .widgets import MapPanel, ReadableTabWidget, card_frame, section_header


def _maps_equal(left: MapData, right: MapData) -> bool:
    return (
        left.name == right.name
        and np.array_equal(left.x, right.x)
        and np.array_equal(left.y, right.y)
        and np.array_equal(left.z, right.z)
    )


class AxisDialog(QDialog):
    def __init__(self, x=None, y=None, title: str = "Define source axes", parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(560)
        self.x_values: np.ndarray | None = None
        self.y_values: np.ndarray | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        intro = QLabel(
            "Enter ascending or descending breakpoints. Repeated values are accepted for "
            "padded RomRaider bins. Commas, tabs, spaces, and new lines are accepted."
        )
        intro.setObjectName("Muted")
        intro.setWordWrap(True)
        layout.addWidget(intro)

        layout.addWidget(QLabel("X axis — columns"))
        self.x_edit = QPlainTextEdit(axis_to_text(x) if x is not None else "0, 1")
        self.x_edit.setMaximumHeight(82)
        layout.addWidget(self.x_edit)

        layout.addWidget(QLabel("Y axis — rows"))
        self.y_edit = QPlainTextEdit(axis_to_text(y) if y is not None else "0, 1")
        self.y_edit.setMaximumHeight(82)
        layout.addWidget(self.y_edit)

        buttons = QDialogButtonBox(QDialogButtonBox.Cancel | QDialogButtonBox.Ok)
        buttons.accepted.connect(self._accept_axes)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _accept_axes(self) -> None:
        try:
            self.x_values = parse_map_axis_text(self.x_edit.toPlainText(), "X")
            self.y_values = parse_map_axis_text(self.y_edit.toPlainText(), "Y")
        except MapValidationError as exc:
            QMessageBox.warning(self, "Invalid axes", str(exc))
            return
        self.accept()


class SmoothingPreviewDialog(QDialog):
    def __init__(
        self,
        source: MapData,
        proposed: MapData,
        warning: str,
        decimals: int,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Review smoothing changes")
        self.resize(1180, 700)
        self.setMinimumSize(900, 560)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        warning_label = QLabel(warning)
        warning_label.setWordWrap(True)
        warning_label.setStyleSheet(
            "color:#ffd98a;background:#2d2414;border:1px solid #6c4c16;"
            "border-radius:8px;padding:10px;"
        )
        layout.addWidget(warning_label)

        delta = MapData(
            source.x,
            source.y,
            proposed.z - source.z,
            name="Smoothing difference",
        )
        changed = int(np.count_nonzero(~np.isclose(delta.z, 0.0, atol=1e-12)))
        maximum_change = float(np.max(np.abs(delta.z)))

        splitter = QSplitter(Qt.Horizontal)
        self.proposed_panel = MapPanel(
            "Proposed map", "Values after applying the deterministic smoothing operation."
        )
        self.proposed_panel.set_map(proposed, decimals=decimals)
        self.proposed_panel.set_badges([(f"{changed} changed", changed > 0)])
        self.difference_panel = MapPanel(
            "Smoothing difference", "Blue decreases values; red increases values."
        )
        self.difference_panel.set_map(delta, diverging=True, decimals=decimals)
        self.difference_panel.set_badges([(f"Max Δ {maximum_change:.6g}", maximum_change > 0)])
        splitter.addWidget(self.proposed_panel)
        splitter.addWidget(self.difference_panel)
        splitter.setSizes([590, 590])
        layout.addWidget(splitter, 1)

        buttons = QDialogButtonBox(QDialogButtonBox.Cancel | QDialogButtonBox.Apply)
        buttons.button(QDialogButtonBox.Apply).setText("Apply smoothing")
        buttons.button(QDialogButtonBox.Apply).setObjectName("PrimaryButton")
        buttons.button(QDialogButtonBox.Apply).clicked.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)


class SelectionMathDialog(QDialog):
    def __init__(self, selected_count: int, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Selection math")
        self.setMinimumWidth(430)
        layout = QVBoxLayout(self)
        note = QLabel(
            f"Apply one deterministic operation to {selected_count} selected source cells. "
            "The change can be undone with Ctrl+Z."
        )
        note.setWordWrap(True)
        note.setObjectName("Muted")
        layout.addWidget(note)
        form = QFormLayout()
        self.operation = QComboBox()
        for key, label in MATH_OPERATIONS.items():
            self.operation.addItem(label, key)
        self.value = QDoubleSpinBox()
        self.value.setRange(-1e12, 1e12)
        self.value.setDecimals(8)
        self.value.setValue(0.0)
        self.second_value = QDoubleSpinBox()
        self.second_value.setRange(-1e12, 1e12)
        self.second_value.setDecimals(8)
        self.second_value.setValue(100.0)
        self.second_label = QLabel("Maximum")
        form.addRow("Operation", self.operation)
        form.addRow("Value / minimum", self.value)
        form.addRow(self.second_label, self.second_value)
        layout.addLayout(form)
        self.operation.currentIndexChanged.connect(self._operation_changed)
        self._operation_changed()
        buttons = QDialogButtonBox(QDialogButtonBox.Cancel | QDialogButtonBox.Apply)
        buttons.button(QDialogButtonBox.Apply).setText("Apply to selection")
        buttons.button(QDialogButtonBox.Apply).setObjectName("PrimaryButton")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _operation_changed(self) -> None:
        clamp = self.operation.currentData() == "clamp"
        self.second_label.setVisible(clamp)
        self.second_value.setVisible(clamp)


class SafetyReportDialog(QDialog):
    def __init__(self, report_text: str, parent=None) -> None:
        super().__init__(parent)
        self.report_text = report_text
        self.setWindowTitle("Pre-export safety report")
        self.resize(650, 520)
        layout = QVBoxLayout(self)
        heading = QLabel(
            "Review these numerical checks before copying the generated table. "
            "They do not determine whether a calibration is mechanically safe."
        )
        heading.setWordWrap(True)
        heading.setStyleSheet(
            "color:#ffd98a;background:#2d2414;border:1px solid #6c4c16;"
            "border-radius:8px;padding:10px;"
        )
        layout.addWidget(heading)
        self.text = QPlainTextEdit(report_text)
        self.text.setReadOnly(True)
        layout.addWidget(self.text, 1)
        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        copy_button = buttons.addButton("Copy report", QDialogButtonBox.ActionRole)
        copy_button.clicked.connect(lambda: QApplication.clipboard().setText(self.report_text))
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)


class MapComparisonDialog(QDialog):
    def __init__(self, comparison: MapComparison, decimals: int, parent=None) -> None:
        super().__init__(parent)
        self.comparison = comparison
        self.merge_mask: np.ndarray | None = None
        self.setWindowTitle("Compare and merge maps")
        self.resize(1480, 720)
        self.setMinimumSize(900, 560)
        layout = QVBoxLayout(self)
        alignment = (
            "resampled to the source axes" if comparison.resampled else "axes matched exactly"
        )
        note = QLabel(
            f"Candidate {alignment}. Select cells in the difference map and choose "
            "Merge selected cells. Amber cells required held-edge alignment."
        )
        note.setObjectName("Muted")
        note.setWordWrap(True)
        layout.addWidget(note)
        splitter = QSplitter(Qt.Horizontal)
        self.candidate_panel = MapPanel("Aligned candidate", "Values available for merging.")
        self.candidate_panel.set_map(
            comparison.candidate,
            comparison.extrapolated_mask,
            decimals=decimals,
        )
        self.delta_panel = MapPanel(
            "Candidate minus source", "Select cells here to merge into the source map."
        )
        self.delta_panel.set_map(
            comparison.delta,
            comparison.extrapolated_mask,
            diverging=True,
            decimals=decimals,
        )
        maximum = float(np.max(np.abs(comparison.delta.z)))
        changed = int(np.count_nonzero(~np.isclose(comparison.delta.z, 0.0, atol=1e-12)))
        self.delta_panel.set_badges(
            [(f"{changed} changed", changed > 0), (f"Max Δ {maximum:.6g}", maximum > 0)]
        )
        percent_map = MapData(
            comparison.base.x,
            comparison.base.y,
            comparison.percent_delta,
            name="Percentage difference",
        )
        self.percent_panel = MapPanel(
            "Percentage difference", "Difference divided by the absolute source value."
        )
        self.percent_panel.set_map(
            percent_map,
            comparison.extrapolated_mask,
            diverging=True,
            decimals=decimals,
        )
        splitter.addWidget(self.candidate_panel)
        splitter.addWidget(self.delta_panel)
        splitter.addWidget(self.percent_panel)
        splitter.setSizes([490, 500, 490])
        layout.addWidget(splitter, 1)
        buttons = QDialogButtonBox(QDialogButtonBox.Cancel | QDialogButtonBox.Apply)
        buttons.button(QDialogButtonBox.Apply).setText("Merge selected cells")
        buttons.button(QDialogButtonBox.Apply).setObjectName("PrimaryButton")
        buttons.button(QDialogButtonBox.Apply).clicked.connect(self._accept_selection)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _accept_selection(self) -> None:
        indexes = self.delta_panel.table.selectedIndexes()
        if not indexes:
            QMessageBox.warning(self, "No cells selected", "Select difference-map cells to merge.")
            return
        self.merge_mask = np.zeros_like(self.comparison.base.z, dtype=bool)
        for index in indexes:
            self.merge_mask[index.row(), index.column()] = True
        self.accept()


class ECUMapMainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.source_data: MapData | None = None
        self.result: ResampleResult | None = None
        self.result_stale = False
        self.history = UndoHistory[MapData](_maps_equal)
        self.result_history = UndoHistory[MapData](_maps_equal)
        self.project_path: str | None = None
        self.curve_windows: list[QMainWindow] = []
        self.visual_windows: list[QDialog] = []

        self.setWindowTitle("ECU Map Studio")
        self.resize(1420, 900)
        self.setMinimumSize(1050, 700)
        self._build_ui()
        self._build_menu()
        self.statusBar().showMessage("Ready — paste a full RomRaider table to begin.")

    def _build_ui(self) -> None:
        root = QWidget()
        root.setObjectName("AppRoot")
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._top_bar())

        splitter = QSplitter(Qt.Horizontal)
        splitter.setChildrenCollapsible(False)
        splitter.addWidget(self._sidebar())
        splitter.addWidget(self._workspace())
        splitter.setSizes([380, 1040])
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        layout.addWidget(splitter, 1)

    def _top_bar(self) -> QWidget:
        bar = QFrame()
        bar.setObjectName("TopBar")
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(24, 13, 24, 13)
        layout.setSpacing(13)

        logo = QLabel("M")
        logo.setAlignment(Qt.AlignCenter)
        logo.setFixedSize(42, 42)
        logo.setStyleSheet(
            "background:#35d0df;color:#061017;border-radius:12px;font-size:17pt;font-weight:900;"
        )
        layout.addWidget(logo)

        titles = QVBoxLayout()
        titles.setSpacing(0)
        title = QLabel("ECU Map Studio")
        title.setObjectName("AppTitle")
        subtitle = QLabel("Interpolation  •  Extrapolation  •  RomRaider clipboard")
        subtitle.setObjectName("AppSubtitle")
        titles.addWidget(title)
        titles.addWidget(subtitle)
        layout.addLayout(titles)
        layout.addStretch(1)

        curve_button = QPushButton("Open 2D Curve Tool")
        curve_button.setObjectName("GhostButton")
        curve_button.setToolTip("Open the one-axis RomRaider [Table2D] curve editor.")
        curve_button.clicked.connect(self.open_curve_tool)
        layout.addWidget(curve_button)

        safety = QLabel("CALIBRATION TOOL")
        safety.setObjectName("Badge")
        safety.setToolTip("Numerical output still requires calibration review and validation.")
        layout.addWidget(safety)
        return bar

    def _sidebar(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setMinimumWidth(350)
        scroll.setMaximumWidth(470)

        body = QWidget()
        body.setObjectName("SidebarBody")
        layout = QVBoxLayout(body)
        layout.setContentsMargins(14, 14, 14, 18)
        layout.setSpacing(12)

        layout.addWidget(self._source_card())
        layout.addWidget(self._target_card())
        layout.addWidget(self._method_card())
        layout.addStretch(1)

        note = QLabel(
            "Extrapolated cells are marked amber. Interpolation cannot determine whether "
            "a calibration is safe for an engine."
        )
        note.setObjectName("FieldHint")
        note.setWordWrap(True)
        layout.addWidget(note)
        scroll.setWidget(body)
        return scroll

    def _source_card(self) -> QWidget:
        card, layout = card_frame()
        layout.addLayout(section_header(1, "Source map"))

        self.paste_button = QPushButton("Paste RomRaider / Excel table")
        self.paste_button.setObjectName("PrimaryButton")
        self.paste_button.setToolTip(
            "Paste [Table3D] data copied with RomRaider's Copy Table command."
        )
        self.paste_button.clicked.connect(self.paste_from_clipboard)
        layout.addWidget(self.paste_button)

        row = QHBoxLayout()
        self.new_button = QPushButton("New blank")
        self.new_button.setObjectName("GhostButton")
        self.new_button.clicked.connect(self.new_blank_map)
        demo_button = QPushButton("Load demo")
        demo_button.setObjectName("GhostButton")
        demo_button.clicked.connect(self.load_demo_map)
        row.addWidget(self.new_button)
        row.addWidget(demo_button)
        layout.addLayout(row)

        self.clear_session_button = QPushButton("Clear table / New session")
        self.clear_session_button.setObjectName("GhostButton")
        self.clear_session_button.setToolTip(
            "Clear the source, generated maps, target axes, and map visualizers."
        )
        self.clear_session_button.setEnabled(False)
        self.clear_session_button.clicked.connect(self.new_session)
        layout.addWidget(self.clear_session_button)

        self.source_summary = QLabel("No table loaded")
        self.source_summary.setObjectName("Muted")
        self.source_summary.setWordWrap(True)
        layout.addWidget(self.source_summary)

        help_text = QLabel(
            "Tip: a RomRaider [Selection3D] contains no axes. It can update an already "
            "loaded map; use Copy Table for a one-step import."
        )
        help_text.setObjectName("FieldHint")
        help_text.setWordWrap(True)
        layout.addWidget(help_text)
        return card

    def _target_card(self) -> QWidget:
        card, layout = card_frame()
        layout.addLayout(section_header(2, "Target grid"))

        self.target_mode_tabs = QTabWidget()
        self.target_mode_tabs.setObjectName("ModeTabs")

        automatic = QWidget()
        automatic_layout = QVBoxLayout(automatic)
        automatic_layout.setContentsMargins(8, 10, 8, 8)
        automatic_layout.setSpacing(9)

        automatic_note = QLabel(
            "Set the new limits and table size. Both endpoints are included and all "
            "breakpoints use constant spacing."
        )
        automatic_note.setObjectName("FieldHint")
        automatic_note.setWordWrap(True)
        automatic_layout.addWidget(automatic_note)

        dimensions = QGridLayout()
        dimensions.setHorizontalSpacing(8)
        dimensions.addWidget(QLabel("Columns (X)"), 0, 0)
        dimensions.addWidget(QLabel("Rows (Y)"), 0, 1)
        self.column_count = QSpinBox()
        self.column_count.setRange(2, 128)
        self.column_count.setValue(20)
        self.row_count = QSpinBox()
        self.row_count.setRange(2, 128)
        self.row_count.setValue(20)
        dimensions.addWidget(self.column_count, 1, 0)
        dimensions.addWidget(self.row_count, 1, 1)
        automatic_layout.addLayout(dimensions)

        ranges = QGridLayout()
        ranges.setHorizontalSpacing(7)
        ranges.setVerticalSpacing(7)
        ranges.addWidget(QLabel(""), 0, 0)
        minimum_label = QLabel("Minimum")
        minimum_label.setObjectName("FieldHint")
        maximum_label = QLabel("Maximum")
        maximum_label.setObjectName("FieldHint")
        ranges.addWidget(minimum_label, 0, 1)
        ranges.addWidget(maximum_label, 0, 2)
        ranges.addWidget(QLabel("X"), 1, 0)
        ranges.addWidget(QLabel("Y"), 2, 0)
        self.x_min_edit = QLineEdit()
        self.x_max_edit = QLineEdit()
        self.y_min_edit = QLineEdit()
        self.y_max_edit = QLineEdit()
        self.x_min_edit.setPlaceholderText("X minimum")
        self.x_max_edit.setPlaceholderText("X maximum")
        self.y_min_edit.setPlaceholderText("Y minimum")
        self.y_max_edit.setPlaceholderText("Y maximum")
        ranges.addWidget(self.x_min_edit, 1, 1)
        ranges.addWidget(self.x_max_edit, 1, 2)
        ranges.addWidget(self.y_min_edit, 2, 1)
        ranges.addWidget(self.y_max_edit, 2, 2)
        ranges.setColumnStretch(1, 1)
        ranges.setColumnStretch(2, 1)
        automatic_layout.addLayout(ranges)

        self.spacing_preview = QLabel("Enter a valid minimum and maximum for each axis.")
        self.spacing_preview.setObjectName("FieldHint")
        self.spacing_preview.setWordWrap(True)
        automatic_layout.addWidget(self.spacing_preview)

        reset_range_button = QPushButton("Reset limits to source map")
        reset_range_button.setObjectName("GhostButton")
        reset_range_button.clicked.connect(self.reset_auto_range)
        automatic_layout.addWidget(reset_range_button)

        custom = QWidget()
        custom_layout = QVBoxLayout(custom)
        custom_layout.setContentsMargins(8, 10, 8, 8)
        custom_layout.setSpacing(9)

        custom_note = QLabel(
            "Paste or enter every breakpoint when the target axes are not evenly spaced."
        )
        custom_note.setObjectName("FieldHint")
        custom_note.setWordWrap(True)
        custom_layout.addWidget(custom_note)

        custom_layout.addWidget(QLabel("Target X axis"))
        self.target_x_edit = QPlainTextEdit()
        self.target_x_edit.setPlaceholderText("Paste or enter column breakpoints…")
        self.target_x_edit.setMaximumHeight(64)
        custom_layout.addWidget(self.target_x_edit)

        custom_layout.addWidget(QLabel("Target Y axis"))
        self.target_y_edit = QPlainTextEdit()
        self.target_y_edit.setPlaceholderText("Paste or enter row breakpoints…")
        self.target_y_edit.setMaximumHeight(64)
        custom_layout.addWidget(self.target_y_edit)

        source_axes_button = QPushButton("Use source axes")
        source_axes_button.setObjectName("GhostButton")
        source_axes_button.clicked.connect(self.use_source_axes)
        custom_layout.addWidget(source_axes_button)

        self.target_mode_tabs.addTab(automatic, "AUTOMATIC RANGE")
        self.target_mode_tabs.addTab(custom, "CUSTOM AXES")
        layout.addWidget(self.target_mode_tabs)

        self.column_count.valueChanged.connect(self._update_spacing_preview)
        self.row_count.valueChanged.connect(self._update_spacing_preview)
        for range_edit in (
            self.x_min_edit,
            self.x_max_edit,
            self.y_min_edit,
            self.y_max_edit,
        ):
            range_edit.textChanged.connect(self._update_spacing_preview)
            range_edit.textEdited.connect(
                lambda _text, editor=range_edit: self._clear_exact_axis_value(editor)
            )
        return card

    def _method_card(self) -> QWidget:
        card, layout = card_frame()
        layout.addLayout(section_header(3, "Resampling"))

        layout.addWidget(QLabel("Interpolation method"))
        self.method_combo = QComboBox()
        self.method_combo.addItem("Bilinear — predictable default", "bilinear")
        self.method_combo.addItem("PCHIP — smooth and shape-preserving", "pchip")
        self.method_combo.addItem("Nearest — switches and categorical maps", "nearest")
        self.method_combo.currentIndexChanged.connect(self._method_changed)
        layout.addWidget(self.method_combo)

        self.method_hint = QLabel()
        self.method_hint.setObjectName("FieldHint")
        self.method_hint.setWordWrap(True)
        layout.addWidget(self.method_hint)
        self._method_changed()

        layout.addWidget(QLabel("Outside the source axes"))
        self.extrapolation_combo = QComboBox()
        self.extrapolation_combo.addItem("Hold edge values — recommended", "hold")
        self.extrapolation_combo.addItem("Limited linear edge slope", "linear")
        self.extrapolation_combo.addItem("Do not extrapolate", "disallow")
        self.extrapolation_combo.currentIndexChanged.connect(self._extrapolation_changed)
        layout.addWidget(self.extrapolation_combo)

        self.limit_row = QWidget()
        limit_layout = QHBoxLayout(self.limit_row)
        limit_layout.setContentsMargins(0, 0, 0, 0)
        limit_layout.addWidget(QLabel("Maximum edge intervals"))
        self.edge_limit = QDoubleSpinBox()
        self.edge_limit.setRange(0.1, 10.0)
        self.edge_limit.setSingleStep(0.25)
        self.edge_limit.setValue(1.0)
        self.edge_limit.setDecimals(2)
        limit_layout.addWidget(self.edge_limit)
        self.limit_row.setVisible(False)
        layout.addWidget(self.limit_row)

        precision_row = QHBoxLayout()
        precision_row.addWidget(QLabel("Displayed decimals"))
        self.decimals = QSpinBox()
        self.decimals.setRange(0, 8)
        self.decimals.setValue(3)
        self.decimals.valueChanged.connect(self._refresh_display_precision)
        precision_row.addWidget(self.decimals)
        layout.addLayout(precision_row)

        self.generate_button = QPushButton("Generate resampled map")
        self.generate_button.setObjectName("GenerateButton")
        self.generate_button.setEnabled(False)
        self.generate_button.clicked.connect(self.generate_result)
        layout.addWidget(self.generate_button)
        return card

    def _workspace(self) -> QWidget:
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(10, 12, 16, 12)
        layout.setSpacing(0)

        self.tabs = ReadableTabWidget()
        self.source_panel = MapPanel(
            "Source heat map", "Double-click a Z cell to edit it before resampling."
        )
        self.result_panel = MapPanel(
            "Resampled heat map",
            "Double-click to fine-tune generated values; amber cells are extrapolated.",
        )
        self.delta_panel = MapPanel(
            "Difference vs bilinear",
            "Blue is lower, red is higher; this isolates the selected method's effect.",
        )

        self.source_visualize_button = self._visualize_button("source")
        self.source_visualize_button.setEnabled(False)
        self.source_panel.add_action(self.source_visualize_button)

        self.smoothing_button = QPushButton("Smoothing")
        self.smoothing_button.setObjectName("GhostButton")
        self.smoothing_button.setEnabled(False)
        smoothing_menu = QMenu(self.smoothing_button)
        detect_action = smoothing_menu.addAction("Detect suspicious cells")
        detect_action.triggered.connect(self.detect_source_anomalies)
        repair_action = smoothing_menu.addAction("Repair selected cells…")
        repair_action.triggered.connect(self.repair_source_selection)
        whole_table_action = smoothing_menu.addAction("Smooth entire table…")
        whole_table_action.triggered.connect(self.smooth_source_table)
        smoothing_menu.addSeparator()
        self.undo_smoothing_action = smoothing_menu.addAction("Undo last source change")
        self.undo_smoothing_action.setEnabled(False)
        self.undo_smoothing_action.triggered.connect(self.undo_smoothing)
        self.smoothing_button.setMenu(smoothing_menu)
        self.source_panel.add_action(self.smoothing_button)

        self.math_button = QPushButton("Selection math")
        self.math_button.setObjectName("GhostButton")
        self.math_button.setEnabled(False)
        self.math_button.clicked.connect(self.open_selection_math)
        self.source_panel.add_action(self.math_button)

        self.compare_button = QPushButton("Compare clipboard")
        self.compare_button.setObjectName("GhostButton")
        self.compare_button.setEnabled(False)
        self.compare_button.setToolTip("Compare with a full map currently on the clipboard.")
        self.compare_button.clicked.connect(self.compare_clipboard_map)
        self.source_panel.add_action(self.compare_button)

        edit_axes_button = QPushButton("Edit axes")
        edit_axes_button.setObjectName("GhostButton")
        edit_axes_button.clicked.connect(self.edit_source_axes)
        self.source_panel.add_action(edit_axes_button)

        self.copy_source_button = QPushButton("Copy source")
        self.copy_source_button.setObjectName("GhostButton")
        self.copy_source_button.setEnabled(False)
        self.copy_source_button.clicked.connect(self.copy_source_romraider)
        self.source_panel.add_action(self.copy_source_button)

        self.copy_excel_button = QPushButton("Copy TSV")
        self.copy_excel_button.setEnabled(False)
        self.copy_excel_button.clicked.connect(self.copy_result_excel)
        self.result_panel.add_action(self.copy_excel_button)

        self.copy_result_button = QPushButton("Copy to RR")
        self.copy_result_button.setObjectName("PrimaryButton")
        self.copy_result_button.setToolTip("Copy the complete result for RomRaider")
        self.copy_result_button.setEnabled(False)
        self.copy_result_button.clicked.connect(self.copy_result_romraider)
        self.result_panel.add_action(self.copy_result_button)

        self.safety_report_button = QPushButton("Safety report")
        self.safety_report_button.setObjectName("GhostButton")
        self.safety_report_button.setToolTip("Open the pre-export numerical safety report")
        self.safety_report_button.setEnabled(False)
        self.safety_report_button.clicked.connect(self.show_safety_report)
        self.result_panel.add_action(self.safety_report_button)

        self.result_visualize_button = self._visualize_button("result")
        self.result_visualize_button.setEnabled(False)
        self.result_panel.add_action(self.result_visualize_button)

        self.delta_visualize_button = self._visualize_button("difference")
        self.delta_visualize_button.setEnabled(False)
        self.delta_panel.add_action(self.delta_visualize_button)

        self.source_panel.table.pasteRequested.connect(self.paste_from_clipboard)
        self.source_panel.table.dataEdited.connect(self._source_edited)
        self.source_panel.table.pasteRejected.connect(
            lambda message: self._error(message, "Cannot paste cells")
        )
        self.result_panel.table.dataEdited.connect(self._result_edited)
        self.result_panel.table.pasteRejected.connect(
            lambda message: self._error(message, "Cannot paste cells")
        )

        self.tabs.addTab(self.source_panel, "SOURCE")
        self.tabs.addTab(self.result_panel, "RESULT")
        self.tabs.addTab(self.delta_panel, "VS BILINEAR")
        self.tabs.setTabToolTip(0, "Editable source map")
        self.tabs.setTabToolTip(1, "Editable generated result")
        self.tabs.setTabToolTip(2, "Generated result minus the bilinear reference")
        self.tabs.setTabEnabled(1, False)
        self.tabs.setTabEnabled(2, False)
        self.tabs.currentChanged.connect(self._update_history_actions)
        layout.addWidget(self.tabs)
        return container

    def _visualize_button(self, kind: str) -> QPushButton:
        button = QPushButton("Visualize")
        button.setObjectName("GhostButton")
        button.setToolTip("Open slice plots or an interactive 3D surface")
        menu = QMenu(button)
        slice_action = menu.addAction("Live X / Y slice plot")
        slice_action.triggered.connect(
            lambda _checked=False, target=kind: self.open_slice_plot(target)
        )
        surface_action = menu.addAction("Interactive 3D surface")
        surface_action.triggered.connect(
            lambda _checked=False, target=kind: self.open_3d_surface(target)
        )
        button.setMenu(menu)
        return button

    def _build_menu(self) -> None:
        file_menu = self.menuBar().addMenu("File")
        open_project_action = QAction("Open project…", self)
        open_project_action.setShortcut(QKeySequence("Ctrl+O"))
        open_project_action.triggered.connect(self.open_project_file)
        file_menu.addAction(open_project_action)
        self.save_project_action = QAction("Save project", self)
        self.save_project_action.setShortcut(QKeySequence("Ctrl+S"))
        self.save_project_action.setEnabled(False)
        self.save_project_action.triggered.connect(self.save_project_file)
        file_menu.addAction(self.save_project_action)
        self.save_project_as_action = QAction("Save project as…", self)
        self.save_project_as_action.setShortcut(QKeySequence("Ctrl+Shift+S"))
        self.save_project_as_action.setEnabled(False)
        self.save_project_as_action.triggered.connect(lambda: self.save_project_file(save_as=True))
        file_menu.addAction(self.save_project_as_action)
        file_menu.addSeparator()
        new_session_action = QAction("New session / Clear table", self)
        new_session_action.setShortcut(QKeySequence("Ctrl+N"))
        new_session_action.triggered.connect(self.new_session)
        file_menu.addAction(new_session_action)
        file_menu.addSeparator()

        paste_action = QAction("Paste RomRaider table", self)
        paste_action.triggered.connect(self.paste_from_clipboard)
        file_menu.addAction(paste_action)

        curve_action = QAction("Open 2D curve tool", self)
        curve_action.triggered.connect(self.open_curve_tool)
        file_menu.addAction(curve_action)

        copy_action = QAction("Copy result for RomRaider", self)
        copy_action.setShortcut(QKeySequence("Ctrl+Shift+C"))
        copy_action.triggered.connect(self.copy_result_romraider)
        file_menu.addAction(copy_action)
        file_menu.addSeparator()
        exit_action = QAction("Exit", self)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        edit_menu = self.menuBar().addMenu("Edit")
        self.undo_action = QAction("Undo", self)
        self.undo_action.setShortcut(QKeySequence.Undo)
        self.undo_action.setEnabled(False)
        self.undo_action.triggered.connect(self.undo_active)
        edit_menu.addAction(self.undo_action)
        self.redo_action = QAction("Redo", self)
        self.redo_action.setShortcut(QKeySequence.Redo)
        self.redo_action.setEnabled(False)
        self.redo_action.triggered.connect(self.redo_active)
        edit_menu.addAction(self.redo_action)
        edit_menu.addSeparator()
        math_action = QAction("Selection math…", self)
        math_action.triggered.connect(self.open_selection_math)
        edit_menu.addAction(math_action)

        tools_menu = self.menuBar().addMenu("Tools")
        compare_action = QAction("Compare clipboard map…", self)
        compare_action.triggered.connect(self.compare_clipboard_map)
        tools_menu.addAction(compare_action)
        report_action = QAction("Pre-export safety report…", self)
        report_action.triggered.connect(self.show_safety_report)
        tools_menu.addAction(report_action)

        help_menu = self.menuBar().addMenu("Help")
        clipboard_action = QAction("RomRaider clipboard guide", self)
        clipboard_action.triggered.connect(self.show_clipboard_guide)
        help_menu.addAction(clipboard_action)
        about_action = QAction("About ECU Map Studio", self)
        about_action.triggered.connect(self.show_about)
        help_menu.addAction(about_action)

    def set_source_map(
        self,
        map_data: MapData,
        reset_target: bool = True,
        *,
        history_mode: str | None = None,
    ) -> None:
        if history_mode is None:
            history_mode = "reset" if reset_target or self.source_data is None else "record"
        if history_mode == "reset":
            self.history.reset(map_data)
        elif history_mode == "record":
            self.history.record(map_data)
        elif history_mode != "preserve":
            raise ValueError(f"Unknown history mode: {history_mode}")
        self.source_data = map_data
        self.source_panel.set_map(
            map_data,
            editable=True,
            decimals=self.decimals.value(),
        )
        minimum, maximum = map_data.value_range
        badges = [
            (f"{map_data.columns} × {map_data.rows}", False),
            (f"Z {minimum:.3g}…{maximum:.3g}", False),
        ]
        repeated_x = int(map_data.columns - np.unique(map_data.x).size)
        repeated_y = int(map_data.rows - np.unique(map_data.y).size)
        padding_summary = ""
        if repeated_x or repeated_y:
            try:
                collapsed = collapse_duplicate_map(map_data)
            except MapValidationError:
                badges.append((f"padded X {repeated_x} / Y {repeated_y}: assign axes", True))
                padding_summary = (
                    f"\nPadded bins: {repeated_x} X and {repeated_y} Y; assign distinct "
                    "breakpoints before surface calculations"
                )
            else:
                badges.append((f"padded X {repeated_x} / Y {repeated_y}", True))
                padding_summary = (
                    f"\nCalculation surface: {collapsed.map_data.columns} columns × "
                    f"{collapsed.map_data.rows} rows until padded axes are assigned"
                )
        self.source_panel.set_badges(badges)
        self.source_summary.setText(
            f"Loaded {map_data.columns} columns × {map_data.rows} rows\n"
            f"X: {map_data.x[0]:.6g} → {map_data.x[-1]:.6g}  •  "
            f"Y: {map_data.y[0]:.6g} → {map_data.y[-1]:.6g}"
            f"{padding_summary}"
        )
        self.copy_source_button.setEnabled(True)
        self.source_visualize_button.setEnabled(True)
        self.clear_session_button.setEnabled(True)
        self.generate_button.setEnabled(True)
        self.smoothing_button.setEnabled(True)
        self.math_button.setEnabled(True)
        self.compare_button.setEnabled(True)
        self.save_project_action.setEnabled(True)
        self.save_project_as_action.setEnabled(True)
        if reset_target:
            self.target_mode_tabs.setCurrentIndex(0)
            self.column_count.setValue(map_data.columns)
            self.row_count.setValue(map_data.rows)
            self.use_source_axes()
        self._invalidate_result("Source loaded — configure the target grid and generate.")
        self.tabs.setCurrentIndex(0)
        self._update_history_actions()

    def new_session(self, _checked: bool = False, *, confirm: bool = True) -> bool:
        """Return the map workspace to its initial empty state."""
        has_session_data = self.source_data is not None or self.result is not None
        if confirm and has_session_data:
            answer = QMessageBox.question(
                self,
                "Start a new session?",
                "This clears the loaded source table, generated result, difference map, "
                "target axes, and smoothing undo history. It does not alter the clipboard "
                "or any RomRaider data. Continue?",
                QMessageBox.Yes | QMessageBox.Cancel,
                QMessageBox.Cancel,
            )
            if answer != QMessageBox.Yes:
                return False

        for window in list(self.visual_windows):
            try:
                window.close()
            except RuntimeError:
                pass
        self.visual_windows.clear()

        self.source_data = None
        self.result = None
        self.result_stale = False
        self.history.clear()
        self.result_history.clear()
        self.project_path = None
        self.setWindowTitle("ECU Map Studio")
        self._update_history_actions()

        self.source_panel.clear_map()
        self.result_panel.clear_map()
        self.delta_panel.clear_map()
        self.source_panel.subtitle_label.setText(
            "Double-click a Z cell to edit it before resampling."
        )
        self.result_panel.subtitle_label.setText(
            "Double-click to fine-tune generated values; amber cells are extrapolated."
        )
        self.delta_panel.subtitle_label.setText(
            "Blue is lower, red is higher; this isolates the selected method's effect."
        )
        self.source_summary.setText("No table loaded")

        self.target_mode_tabs.setCurrentIndex(0)
        self.column_count.setValue(20)
        self.row_count.setValue(20)
        for editor in (
            self.x_min_edit,
            self.x_max_edit,
            self.y_min_edit,
            self.y_max_edit,
        ):
            editor.clear()
        self.target_x_edit.clear()
        self.target_y_edit.clear()
        self.method_combo.setCurrentIndex(0)
        self.extrapolation_combo.setCurrentIndex(0)
        self.edge_limit.setValue(1.0)
        self.spacing_preview.setText("Enter a valid minimum and maximum for each axis.")
        self.spacing_preview.setStyleSheet("")

        self.tabs.setTabEnabled(1, False)
        self.tabs.setTabEnabled(2, False)
        self.tabs.setCurrentIndex(0)
        self.copy_source_button.setEnabled(False)
        self.source_visualize_button.setEnabled(False)
        self.copy_result_button.setEnabled(False)
        self.copy_excel_button.setEnabled(False)
        self.safety_report_button.setEnabled(False)
        self.result_visualize_button.setEnabled(False)
        self.delta_visualize_button.setEnabled(False)
        self.clear_session_button.setEnabled(False)
        self.generate_button.setEnabled(False)
        self.smoothing_button.setEnabled(False)
        self.math_button.setEnabled(False)
        self.compare_button.setEnabled(False)
        self.save_project_action.setEnabled(False)
        self.save_project_as_action.setEnabled(False)
        self.statusBar().showMessage(
            "New session ready — paste a RomRaider table or create a blank map.", 7000
        )
        return True

    def paste_from_clipboard(self) -> None:
        text = QApplication.clipboard().text()
        if not text.strip():
            self._error("Clipboard is empty.", "Nothing to paste")
            return
        try:
            payload = parse_clipboard(text)
            if payload.kind == "table" and payload.map_data is not None:
                self.set_source_map(payload.map_data)
                if payload.notice:
                    QMessageBox.information(
                        self,
                        "Repeated RomRaider breakpoints preserved",
                        payload.notice,
                    )
                    self.statusBar().showMessage(
                        "Full padded table imported and preserved. Repeated bins are ready "
                        "for new breakpoints.",
                        12000,
                    )
                else:
                    self.statusBar().showMessage("Full table imported from the clipboard.", 5000)
                return
            if payload.kind == "curve" and payload.curve_data is not None:
                self.open_curve_tool(payload.curve_data)
                self.statusBar().showMessage(
                    "RomRaider [Table2D] detected and opened in the 2D Curve Tool.", 6000
                )
                return
            if payload.kind == "curve_selection":
                if self.curve_windows:
                    self.curve_windows[-1].paste_from_clipboard()
                    self.curve_windows[-1].raise_()
                    self.curve_windows[-1].activateWindow()
                    return
                raise ClipboardFormatError(
                    "[Selection1D] has no axis. Open a full [Table2D] curve first."
                )
            if payload.kind == "selection" and payload.selection is not None:
                self._apply_selection(payload.selection)
                return
        except (ClipboardFormatError, MapValidationError) as exc:
            self._error(str(exc), "Clipboard format not recognized")

    def open_curve_tool(self, curve=None) -> None:
        from .curve_window import CurveWindow

        if isinstance(curve, bool):
            curve = None
        window = CurveWindow(curve, parent=self)
        self.curve_windows.append(window)

        def forget_window(*_):
            # The Qt C++ object is already being destroyed here. Use Python
            # identity only; wrapper equality can touch the deleted Qt object.
            self.curve_windows[:] = [
                candidate for candidate in self.curve_windows if candidate is not window
            ]

        window.destroyed.connect(forget_window)
        window.show()
        window.raise_()
        window.activateWindow()

    def _apply_selection(self, selection: np.ndarray) -> None:
        if self.source_data is None:
            raise ClipboardFormatError(
                "[Selection3D] contains Z values but no X or Y axes. First import a full "
                "[Table3D] map, or use RomRaider's Copy Table command."
            )
        current = self.source_panel.table.current_map()
        selected_indexes = self.source_panel.table.selectedIndexes()
        start_row = min((index.row() for index in selected_indexes), default=0)
        start_column = min((index.column() for index in selected_indexes), default=0)
        end_row = start_row + selection.shape[0]
        end_column = start_column + selection.shape[1]
        if end_row > current.rows or end_column > current.columns:
            raise ClipboardFormatError(
                "The RomRaider selection does not fit in the source table from the selected cell."
            )

        values = current.z.copy()
        destination = values[start_row:end_row, start_column:end_column]
        numeric = np.isfinite(selection)
        destination[numeric] = selection[numeric]
        updated = MapData(current.x, current.y, values, name=current.name)
        self.set_source_map(updated, reset_target=False)
        self.statusBar().showMessage("RomRaider selection applied to the source map.", 5000)

    def new_blank_map(self) -> None:
        dialog = AxisDialog(parent=self)
        if dialog.exec_() != QDialog.Accepted:
            return
        assert dialog.x_values is not None and dialog.y_values is not None
        data = MapData(
            dialog.x_values,
            dialog.y_values,
            np.zeros((dialog.y_values.size, dialog.x_values.size)),
            name="Blank map",
        )
        self.set_source_map(data)

    def edit_source_axes(self) -> None:
        if self.source_data is None:
            self.new_blank_map()
            return
        try:
            current = self.source_panel.table.current_map()
        except MapValidationError as exc:
            self._error(str(exc), "Cannot edit axes")
            return
        dialog = AxisDialog(current.x, current.y, "Edit source axes", self)
        if dialog.exec_() != QDialog.Accepted:
            return
        assert dialog.x_values is not None and dialog.y_values is not None
        if dialog.x_values.size != current.columns or dialog.y_values.size != current.rows:
            self._error(
                "Edited axes must keep the current number of columns and rows. "
                "Create a blank map if you need different source dimensions.",
                "Axis dimensions changed",
            )
            return
        self.set_source_map(
            MapData(dialog.x_values, dialog.y_values, current.z, name=current.name),
            reset_target=False,
        )

    def detect_source_anomalies(self) -> None:
        try:
            source = self.source_panel.table.current_map()
            result = detect_anomalies(source)
        except MapValidationError as exc:
            self._error(str(exc), "Cannot inspect source map")
            return
        self.source_panel.table.clearSelection()
        for row, column in np.argwhere(result.mask):
            self.source_panel.table.item(int(row), int(column)).setSelected(True)
        self.tabs.setCurrentIndex(0)
        self.source_panel.set_badges(
            [
                (f"{source.columns} × {source.rows}", False),
                (f"{result.count} suspicious", result.count > 0),
            ]
        )
        if result.count:
            self.statusBar().showMessage(
                f"Selected {result.count} statistically suspicious interior cells. "
                "Review them before using Repair selected cells.",
                9000,
            )
        else:
            self.statusBar().showMessage(
                "No strong isolated interior anomalies were detected. No values changed.",
                7000,
            )

    def repair_source_selection(self) -> None:
        try:
            source = self.source_panel.table.current_map()
        except MapValidationError as exc:
            self._error(str(exc), "Cannot smooth selection")
            return

        indexes = self.source_panel.table.selectedIndexes()
        if not indexes:
            self._error(
                "Select the source cells that should be reconstructed first.",
                "No cells selected",
            )
            return
        mask = np.zeros_like(source.z, dtype=bool)
        for index in indexes:
            mask[index.row(), index.column()] = True

        touches_edge = (
            np.any(mask[0, :]) or np.any(mask[-1, :]) or np.any(mask[:, 0]) or np.any(mask[:, -1])
        )
        if touches_edge:
            answer = QMessageBox.warning(
                self,
                "Selection touches a table edge",
                "This selection has fewer surrounding reference cells because it touches "
                "an outer edge. The reconstruction is less constrained. Continue to preview?",
                QMessageBox.Yes | QMessageBox.Cancel,
                QMessageBox.Cancel,
            )
            if answer != QMessageBox.Yes:
                return

        try:
            proposed = repair_selected_region(source, mask)
        except MapValidationError as exc:
            self._error(str(exc), "Cannot repair selection")
            return
        self._preview_smoothing(
            source,
            proposed,
            "Only the selected cells will change. Surrounding cells remain fixed and "
            "define the reconstructed surface.",
            "Selected-region repair",
        )

    def smooth_source_table(self) -> None:
        try:
            source = self.source_panel.table.current_map()
        except MapValidationError as exc:
            self._error(str(exc), "Cannot smooth source table")
            return

        answer = QMessageBox.warning(
            self,
            "Smooth the entire table?",
            "Whole-table smoothing changes calibration values across the map and can alter "
            "engine behavior positively or adversely. It is not a safety calculation. "
            "Continue to a before/after difference preview?",
            QMessageBox.Yes | QMessageBox.Cancel,
            QMessageBox.Cancel,
        )
        if answer != QMessageBox.Yes:
            return

        try:
            proposed = smooth_entire_table(source)
        except MapValidationError as exc:
            self._error(str(exc), "Cannot smooth source table")
            return
        self._preview_smoothing(
            source,
            proposed,
            "WARNING: this proposal applies one axis-aware local-surface smoothing pass "
            "to the entire table. Review every change and validate the resulting calibration.",
            "Whole-table smoothing",
        )

    def _preview_smoothing(
        self,
        source: MapData,
        proposed: MapData,
        warning: str,
        operation_name: str,
    ) -> None:
        preview = SmoothingPreviewDialog(
            source,
            proposed,
            warning,
            self.decimals.value(),
            self,
        )
        if preview.exec_() != QDialog.Accepted:
            self.statusBar().showMessage("Smoothing preview cancelled; no values changed.", 5000)
            return

        self.set_source_map(proposed, reset_target=False)
        changed = int(np.count_nonzero(~np.isclose(proposed.z, source.z, atol=1e-12)))
        self.source_panel.set_badges(
            [(f"{proposed.columns} × {proposed.rows}", False), (f"{changed} changed", True)]
        )
        self.statusBar().showMessage(
            f"{operation_name} applied to {changed} cells. Undo is available with Ctrl+Z.",
            8000,
        )

    def undo_smoothing(self) -> None:
        self.undo_source()

    def _result_history_active(self) -> bool:
        return (
            hasattr(self, "tabs")
            and self.tabs.currentIndex() == 1
            and self.result is not None
            and not self.result_stale
        )

    def _update_history_actions(self, *_args) -> None:
        if hasattr(self, "undo_action"):
            active = self.result_history if self._result_history_active() else self.history
            target = "result" if self._result_history_active() else "source"
            self.undo_action.setText(f"Undo {target} change")
            self.redo_action.setText(f"Redo {target} change")
            self.undo_action.setEnabled(active.can_undo)
            self.redo_action.setEnabled(active.can_redo)
        if hasattr(self, "undo_smoothing_action"):
            self.undo_smoothing_action.setText("Undo last source change")
            self.undo_smoothing_action.setEnabled(self.history.can_undo)

    def undo_active(self) -> None:
        if self._result_history_active():
            self.undo_result()
        else:
            self.undo_source()

    def redo_active(self) -> None:
        if self._result_history_active():
            self.redo_result()
        else:
            self.redo_source()

    def undo_source(self) -> None:
        previous = self.history.undo()
        if previous is None:
            return
        self.set_source_map(previous, reset_target=False, history_mode="preserve")
        self._update_history_actions()
        self.statusBar().showMessage("Source change undone.", 5000)

    def redo_source(self) -> None:
        following = self.history.redo()
        if following is None:
            return
        self.set_source_map(following, reset_target=False, history_mode="preserve")
        self._update_history_actions()
        self.statusBar().showMessage("Source change redone.", 5000)

    def undo_result(self) -> None:
        previous = self.result_history.undo()
        if previous is None:
            return
        self._set_edited_result(previous, refresh_table=True)
        self._update_history_actions()
        self.statusBar().showMessage("Generated-result change undone.", 5000)

    def redo_result(self) -> None:
        following = self.result_history.redo()
        if following is None:
            return
        self._set_edited_result(following, refresh_table=True)
        self._update_history_actions()
        self.statusBar().showMessage("Generated-result change redone.", 5000)

    def open_selection_math(self) -> None:
        if self.source_data is None:
            self._error("Load a source map first.", "No source map")
            return
        indexes = self.source_panel.table.selectedIndexes()
        if not indexes:
            self._error("Select one or more source cells first.", "No cells selected")
            return
        dialog = SelectionMathDialog(len(indexes), self)
        if dialog.exec_() != QDialog.Accepted:
            return
        self.apply_selection_math(
            dialog.operation.currentData(),
            dialog.value.value(),
            dialog.second_value.value() if dialog.operation.currentData() == "clamp" else None,
        )

    def apply_selection_math(
        self, operation: str, value: float, second_value: float | None = None
    ) -> None:
        try:
            source = self.source_panel.table.current_map()
            mask = np.zeros_like(source.z, dtype=bool)
            for index in self.source_panel.table.selectedIndexes():
                mask[index.row(), index.column()] = True
            proposed = apply_map_math(source, mask, operation, value, second_value)
        except MapValidationError as exc:
            self._error(str(exc), "Cannot apply selection math")
            return
        changed = int(np.count_nonzero(~np.isclose(source.z, proposed.z, atol=1e-12)))
        self.set_source_map(proposed, reset_target=False)
        self.source_panel.set_badges(
            [(f"{proposed.columns} × {proposed.rows}", False), (f"{changed} changed", changed > 0)]
        )
        self.statusBar().showMessage(
            f"{MATH_OPERATIONS[operation]} applied to {int(np.count_nonzero(mask))} cells; "
            "Ctrl+Z restores the previous values.",
            7000,
        )

    def compare_clipboard_map(self) -> None:
        if self.source_data is None:
            self._error("Load a source map first.", "No source map")
            return
        try:
            payload = parse_clipboard(QApplication.clipboard().text(), name="Comparison map")
            if payload.kind != "table" or payload.map_data is None:
                raise ClipboardFormatError(
                    "Copy a full RomRaider [Table3D] or Excel-style map for comparison."
                )
            source = self.source_panel.table.current_map()
            comparison = compare_maps(source, payload.map_data)
        except (ClipboardFormatError, MapValidationError, ValueError) as exc:
            self._error(str(exc), "Cannot compare maps")
            return
        dialog = MapComparisonDialog(comparison, self.decimals.value(), self)
        if dialog.exec_() != QDialog.Accepted or dialog.merge_mask is None:
            self.statusBar().showMessage("Map comparison closed; source values unchanged.", 5000)
            return
        try:
            merged = merge_comparison(comparison, dialog.merge_mask)
        except MapValidationError as exc:
            self._error(str(exc), "Cannot merge comparison")
            return
        count = int(np.count_nonzero(dialog.merge_mask))
        self.set_source_map(merged, reset_target=False)
        self.statusBar().showMessage(
            f"Merged {count} comparison cells. Ctrl+Z restores the previous source map.",
            7000,
        )

    def show_safety_report(self) -> None:
        try:
            source = self.source_panel.table.current_map()
            result = self._current_result_map()
            assert self.result is not None
            report = build_safety_report(
                source,
                result,
                self.result.bilinear_reference,
                self.result.extrapolated_mask,
                "bilinear output on the same target grid",
            )
        except (MapValidationError, AssertionError) as exc:
            self._error(str(exc) or "Generate an up-to-date result first.", "No report available")
            return
        SafetyReportDialog(report.to_text(), self).exec_()

    def _project_document(self) -> dict:
        source = self.source_panel.table.current_map()
        settings = {
            "target_mode": self.target_mode_tabs.currentIndex(),
            "columns": self.column_count.value(),
            "rows": self.row_count.value(),
            "x_min": self.x_min_edit.text(),
            "x_max": self.x_max_edit.text(),
            "y_min": self.y_min_edit.text(),
            "y_max": self.y_max_edit.text(),
            "target_x": self.target_x_edit.toPlainText(),
            "target_y": self.target_y_edit.toPlainText(),
            "method": self.method_combo.currentData(),
            "extrapolation": self.extrapolation_combo.currentData(),
            "edge_limit": self.edge_limit.value(),
            "decimals": self.decimals.value(),
        }
        return {
            "kind": "map",
            "source": map_to_dict(source),
            "result": (
                map_result_to_dict(self.result)
                if self.result is not None and not self.result_stale
                else None
            ),
            "settings": settings,
        }

    def save_project_file(
        self, _checked: bool = False, *, save_as: bool = False, path=None
    ) -> bool:
        if self.source_data is None:
            self._error("Load a source map before saving a project.", "Nothing to save")
            return False
        destination = str(path) if path else (None if save_as else self.project_path)
        if not destination:
            destination, _ = QFileDialog.getSaveFileName(
                self,
                "Save ECU Map Studio project",
                "",
                "ECU Map Studio projects (*.ecumap);;JSON files (*.json)",
            )
        if not destination:
            return False
        if not Path(destination).suffix:
            destination += ".ecumap"
        try:
            save_project(destination, self._project_document())
        except (OSError, TypeError, ValueError, MapValidationError) as exc:
            self._error(str(exc), "Unable to save project")
            return False
        self.project_path = destination
        self.setWindowTitle(f"ECU Map Studio — {Path(destination).name}")
        self.statusBar().showMessage(f"Project saved to {destination}", 7000)
        return True

    def open_project_file(self, _checked: bool = False, *, path=None) -> bool:
        source_path = str(path) if path else ""
        if not source_path:
            source_path, _ = QFileDialog.getOpenFileName(
                self,
                "Open ECU Map Studio project",
                "",
                "ECU Map Studio projects (*.ecumap *.json)",
            )
        if not source_path:
            return False
        try:
            document = load_project(source_path)
            if document["kind"] != "map":
                raise MapValidationError("This project contains a 2D curve, not a 3D map.")
            source = map_from_dict(document["source"])
            restored_result = (
                map_result_from_dict(document["result"])
                if document.get("result") is not None
                else None
            )
            settings = document.get("settings", {})
        except (KeyError, MapValidationError) as exc:
            self._error(str(exc), "Unable to open project")
            return False

        self.new_session(confirm=False)
        self.set_source_map(source, history_mode="reset")
        self.decimals.setValue(int(settings.get("decimals", self.decimals.value())))
        self.column_count.setValue(int(settings.get("columns", source.columns)))
        self.row_count.setValue(int(settings.get("rows", source.rows)))
        self.x_min_edit.setText(str(settings.get("x_min", self.x_min_edit.text())))
        self.x_max_edit.setText(str(settings.get("x_max", self.x_max_edit.text())))
        self.y_min_edit.setText(str(settings.get("y_min", self.y_min_edit.text())))
        self.y_max_edit.setText(str(settings.get("y_max", self.y_max_edit.text())))
        self.target_x_edit.setPlainText(str(settings.get("target_x", "")))
        self.target_y_edit.setPlainText(str(settings.get("target_y", "")))
        self.target_mode_tabs.setCurrentIndex(int(settings.get("target_mode", 0)))
        method_index = self.method_combo.findData(settings.get("method", "bilinear"))
        self.method_combo.setCurrentIndex(max(0, method_index))
        extrapolation_index = self.extrapolation_combo.findData(
            settings.get("extrapolation", "hold")
        )
        self.extrapolation_combo.setCurrentIndex(max(0, extrapolation_index))
        self.edge_limit.setValue(float(settings.get("edge_limit", 1.0)))
        if restored_result is not None:
            self._restore_result(restored_result)
        self.project_path = source_path
        self.setWindowTitle(f"ECU Map Studio — {Path(source_path).name}")
        self.statusBar().showMessage(f"Project opened from {source_path}", 7000)
        return True

    def _restore_result(self, result: ResampleResult) -> None:
        self.result = result
        self.result_stale = False
        self.result_history.reset(result.map_data)
        decimals = self.decimals.value()
        self.result_panel.set_map(
            result.map_data,
            result.extrapolated_mask,
            editable=True,
            decimals=decimals,
        )
        self.delta_panel.set_map(
            result.delta_vs_bilinear,
            result.extrapolated_mask,
            diverging=True,
            decimals=decimals,
        )
        warnings = result.extrapolated_cells
        self.result_panel.set_badges(
            [
                (f"{result.map_data.columns} × {result.map_data.rows}", False),
                (METHOD_LABELS[result.method], False),
                (f"{warnings} extrapolated", warnings > 0),
            ]
        )
        self.tabs.setTabEnabled(1, True)
        has_difference = bool(np.any(~np.isclose(result.delta_vs_bilinear.z, 0.0, atol=1e-12)))
        self.tabs.setTabEnabled(2, result.method != "bilinear" or has_difference)
        self.copy_result_button.setEnabled(True)
        self.copy_excel_button.setEnabled(True)
        self.safety_report_button.setEnabled(True)
        self.result_visualize_button.setEnabled(True)
        self.delta_visualize_button.setEnabled(result.method != "bilinear" or has_difference)
        self._update_history_actions()

    def load_demo_map(self) -> None:
        x = np.asarray([800, 1400, 2200, 3000, 4000, 5000, 6000, 7000], dtype=float)
        y = np.asarray([0.20, 0.35, 0.55, 0.75, 0.95, 1.15, 1.35], dtype=float)
        yy, xx = np.meshgrid(y, x, indexing="ij")
        rpm_shape = 12.0 * np.exp(-(((xx - 3300.0) / 2400.0) ** 2))
        load_retard = 14.0 * (yy - 0.2) / 1.15
        knock_bowl = 3.5 * np.exp(-(((xx - 4300.0) / 900.0) ** 2) - ((yy - 1.1) / 0.25) ** 2)
        z = 25.0 + rpm_shape - load_retard - knock_bowl
        self.set_source_map(MapData(x, y, z, name="Demo ignition-style map"))
        self.column_count.setValue(20)
        self.row_count.setValue(16)
        self.create_even_axes()
        self.statusBar().showMessage("Demo map loaded. It is sample data, not a calibration.", 6000)

    def use_source_axes(self) -> None:
        if self.source_data is None:
            return
        self.target_x_edit.setPlainText(axis_to_text(self.source_data.x))
        self.target_y_edit.setPlainText(axis_to_text(self.source_data.y))
        self.column_count.setValue(self.source_data.columns)
        self.row_count.setValue(self.source_data.rows)
        self.reset_auto_range()

    def reset_auto_range(self) -> None:
        if self.source_data is None:
            return
        self._set_exact_axis_value(self.x_min_edit, np.min(self.source_data.x))
        self._set_exact_axis_value(self.x_max_edit, np.max(self.source_data.x))
        self._set_exact_axis_value(self.y_min_edit, np.min(self.source_data.y))
        self._set_exact_axis_value(self.y_max_edit, np.max(self.source_data.y))
        self._update_spacing_preview()

    @staticmethod
    def _clear_exact_axis_value(editor: QLineEdit) -> None:
        editor.setProperty("exactAxisValue", None)
        editor.setProperty("exactAxisText", None)

    @staticmethod
    def _set_exact_axis_value(editor: QLineEdit, value: float) -> None:
        exact = float(value)
        display = format_number(exact, 6)
        editor.setProperty("exactAxisValue", exact)
        editor.setProperty("exactAxisText", display)
        editor.setText(display)

    @staticmethod
    def _axis_input_value(editor: QLineEdit, name: str) -> float:
        exact = editor.property("exactAxisValue")
        exact_text = editor.property("exactAxisText")
        if exact is not None and exact_text is not None and editor.text() == exact_text:
            return float(exact)
        return parse_number_text(editor.text(), name)

    def _automatic_axes(self) -> tuple[np.ndarray, np.ndarray]:
        x_minimum = self._axis_input_value(self.x_min_edit, "X minimum")
        x_maximum = self._axis_input_value(self.x_max_edit, "X maximum")
        y_minimum = self._axis_input_value(self.y_min_edit, "Y minimum")
        y_maximum = self._axis_input_value(self.y_max_edit, "Y maximum")
        x = generate_even_axis(x_minimum, x_maximum, self.column_count.value(), "Target X")
        y = generate_even_axis(y_minimum, y_maximum, self.row_count.value(), "Target Y")
        return x, y

    def _selected_target_axes(self) -> tuple[np.ndarray, np.ndarray]:
        if self.target_mode_tabs.currentIndex() == 0:
            x, y = self._automatic_axes()
            # Keep Custom Axes synchronized so users can inspect or fine-tune the
            # automatically generated breakpoints without re-entering them.
            self.target_x_edit.setPlainText(axis_to_text(x))
            self.target_y_edit.setPlainText(axis_to_text(y))
            return x, y
        return (
            parse_axis_text(self.target_x_edit.toPlainText(), "Target X"),
            parse_axis_text(self.target_y_edit.toPlainText(), "Target Y"),
        )

    def _update_spacing_preview(self) -> None:
        if not hasattr(self, "spacing_preview"):
            return
        try:
            x, y = self._automatic_axes()
            x_step = x[1] - x[0]
            y_step = y[1] - y[0]
            extension = False
            if self.source_data is not None:
                extension = (
                    x[0] < np.min(self.source_data.x)
                    or x[-1] > np.max(self.source_data.x)
                    or y[0] < np.min(self.source_data.y)
                    or y[-1] > np.max(self.source_data.y)
                )
            suffix = " • extends beyond source limits" if extension else " • inside source limits"
            self.spacing_preview.setText(
                f"Spacing: X {format_number(x_step, 6)}  •  Y {format_number(y_step, 6)}{suffix}"
            )
            self.spacing_preview.setStyleSheet("color:#f5b942;" if extension else "color:#8e9cb1;")
        except MapValidationError as exc:
            self.spacing_preview.setText(str(exc))
            self.spacing_preview.setStyleSheet("color:#f5b942;")

    def create_even_axes(self) -> None:
        try:
            x, y = self._automatic_axes()
        except MapValidationError as exc:
            self._error(str(exc), "Invalid automatic range")
            return
        self.target_x_edit.setPlainText(axis_to_text(x))
        self.target_y_edit.setPlainText(axis_to_text(y))
        self.statusBar().showMessage(
            f"Generated automatic {x.size} × {y.size} axes with constant spacing.", 4000
        )

    def generate_result(self) -> None:
        try:
            source = self.source_panel.table.current_map()
            target_x, target_y = self._selected_target_axes()
            result = resample_map(
                source,
                target_x,
                target_y,
                method=self.method_combo.currentData(),
                extrapolation=self.extrapolation_combo.currentData(),
                maximum_edge_intervals=self.edge_limit.value(),
            )
        except (MapValidationError, ValueError) as exc:
            self._error(str(exc), "Unable to generate map")
            return

        self.source_data = source
        self.result = result
        self.result_stale = False
        self.result_history.reset(result.map_data)
        decimals = self.decimals.value()
        self.result_panel.set_map(
            result.map_data,
            result.extrapolated_mask,
            editable=True,
            decimals=decimals,
        )
        self.delta_panel.set_map(
            result.delta_vs_bilinear,
            result.extrapolated_mask,
            diverging=True,
            decimals=decimals,
        )

        method = METHOD_LABELS[result.method]
        extrapolation = EXTRAPOLATION_LABELS[result.extrapolation]
        warnings = result.extrapolated_cells
        self.result_panel.set_badges(
            [
                (f"{result.map_data.columns} × {result.map_data.rows}", False),
                (method, False),
                (f"{warnings} extrapolated", warnings > 0),
            ]
        )
        self.delta_panel.set_badges([(f"{method} minus Bilinear", False)])
        self.result_panel.subtitle_label.setText(
            f"{method} interpolation • {extrapolation} outside source axes"
        )
        self.tabs.setTabEnabled(1, True)
        self.tabs.setTabEnabled(2, result.method != "bilinear")
        self.tabs.setCurrentIndex(1)
        self.copy_result_button.setEnabled(True)
        self.copy_excel_button.setEnabled(True)
        self.safety_report_button.setEnabled(True)
        self.result_visualize_button.setEnabled(True)
        self.delta_visualize_button.setEnabled(result.method != "bilinear")
        self._update_history_actions()
        self.statusBar().showMessage(
            f"Generated {result.map_data.columns} × {result.map_data.rows} map; "
            f"{warnings} extrapolated cells.",
            7000,
        )

    def _set_edited_result(self, map_data: MapData, *, refresh_table: bool) -> None:
        if self.result is None:
            return
        reference = self.result.bilinear_reference
        delta = MapData(
            map_data.x,
            map_data.y,
            map_data.z - reference.z,
            name="Result difference vs bilinear",
        )
        self.result = ResampleResult(
            map_data,
            self.result.extrapolated_mask,
            reference,
            delta,
            self.result.method,
            self.result.extrapolation,
        )
        decimals = self.decimals.value()
        if refresh_table:
            self.result_panel.set_map(
                map_data,
                self.result.extrapolated_mask,
                editable=True,
                decimals=decimals,
            )
        else:
            minimum, maximum = map_data.value_range
            self.result_panel.legend.set_range(minimum, maximum)
        self.delta_panel.set_map(
            delta,
            self.result.extrapolated_mask,
            diverging=True,
            decimals=decimals,
        )
        changed = int(np.count_nonzero(~np.isclose(delta.z, 0.0, atol=1e-12)))
        warnings = self.result.extrapolated_cells
        badges = [
            (f"{map_data.columns} × {map_data.rows}", False),
            (METHOD_LABELS[self.result.method], False),
            (f"{warnings} extrapolated", warnings > 0),
        ]
        if self.result_history.can_undo:
            badges.append(("Manually edited", True))
        self.result_panel.set_badges(badges)
        self.delta_panel.set_badges(
            [("Result minus Bilinear", False), (f"{changed} non-zero", changed > 0)]
        )
        has_difference = self.result.method != "bilinear" or changed > 0
        self.tabs.setTabEnabled(2, has_difference)
        self.delta_visualize_button.setEnabled(has_difference)

    def _result_edited(self) -> None:
        if self.result is None or self.result_stale:
            return
        try:
            current = self.result_panel.table.current_map()
        except MapValidationError as exc:
            self._error(str(exc), "Invalid generated value")
            return
        self.result_history.record(current)
        self._set_edited_result(current, refresh_table=False)
        self._update_history_actions()
        self.statusBar().showMessage(
            "Generated result edited — copy/export uses the updated values. Ctrl+Z undoes it.",
            7000,
        )

    def _source_edited(self) -> None:
        try:
            current = self.source_panel.table.current_map()
        except MapValidationError:
            current = None
        if current is not None:
            self.source_data = current
            self.history.record(current)
            self._update_history_actions()
        self._invalidate_result("Source values changed — generate the result again.")
        self.source_panel.set_badges([("Edited", True)])

    def _invalidate_result(self, message: str) -> None:
        if self.result is not None:
            self.result_stale = True
            self.result_panel.set_badges([("Out of date", True)])
        self.copy_result_button.setEnabled(False)
        self.copy_excel_button.setEnabled(False)
        self.safety_report_button.setEnabled(False)
        if hasattr(self, "result_visualize_button"):
            self.result_visualize_button.setEnabled(False)
            self.delta_visualize_button.setEnabled(False)
        self.statusBar().showMessage(message, 5000)

    def _visualization_context(self, kind: str):
        if kind == "source":
            return self.source_panel, None, "Source map", False
        if self.result is None or self.result_stale:
            raise MapValidationError("Generate an up-to-date result first.")
        if kind == "result":
            return (
                self.result_panel,
                self.result.extrapolated_mask,
                "Resampled map",
                False,
            )
        if kind == "difference":
            return (
                self.delta_panel,
                self.result.extrapolated_mask,
                "Difference vs bilinear",
                True,
            )
        raise MapValidationError("Unknown visualization target.")

    def _track_visual_window(self, window: QDialog) -> None:
        self.visual_windows.append(window)

        def forget_window(*_):
            self.visual_windows[:] = [
                candidate for candidate in self.visual_windows if candidate is not window
            ]

        window.destroyed.connect(forget_window)
        window.show()
        window.raise_()
        window.activateWindow()

    def open_slice_plot(self, kind: str) -> None:
        from .visualization import MapSliceDialog

        try:
            panel, mask, title, diverging = self._visualization_context(kind)
            panel.table.current_map()
            window = MapSliceDialog(
                panel,
                title,
                mask,
                diverging=diverging,
                decimals=self.decimals.value(),
                parent=self,
            )
        except MapValidationError as exc:
            self._error(str(exc), "Cannot open slice plot")
            return
        self._track_visual_window(window)

    def open_3d_surface(self, kind: str) -> None:
        try:
            panel, mask, title, diverging = self._visualization_context(kind)
            map_data = panel.table.current_map()
            from .visualization import Map3DDialog

            window = Map3DDialog(
                map_data,
                title,
                mask,
                diverging=diverging,
                parent=self,
            )
        except (MapValidationError, ImportError) as exc:
            self._error(
                f"{exc}\n\nInstall the project requirements if Matplotlib is unavailable.",
                "Cannot open 3D surface",
            )
            return
        self._track_visual_window(window)

    def _current_result_map(self) -> MapData:
        if self.result is None or self.result_stale:
            raise MapValidationError("Generate an up-to-date result first.")
        return self.result.map_data

    def copy_result_romraider(self) -> None:
        try:
            map_data = self._current_result_map()
        except MapValidationError as exc:
            self._error(str(exc), "Nothing to copy")
            return
        QApplication.clipboard().setText(format_romraider_table(map_data, precision=10))
        self.statusBar().showMessage("Complete [Table3D] result copied for RomRaider.", 5000)

    def copy_result_excel(self) -> None:
        try:
            map_data = self._current_result_map()
        except MapValidationError as exc:
            self._error(str(exc), "Nothing to copy")
            return
        QApplication.clipboard().setText(format_excel_table(map_data, precision=10))
        self.statusBar().showMessage("Complete table copied as Excel-compatible TSV.", 5000)

    def copy_source_romraider(self) -> None:
        try:
            source = self.source_panel.table.current_map()
        except MapValidationError as exc:
            self._error(str(exc), "Nothing to copy")
            return
        QApplication.clipboard().setText(format_romraider_table(source, precision=10))
        self.statusBar().showMessage("Source table copied for RomRaider.", 4000)

    def _refresh_display_precision(self) -> None:
        decimals = self.decimals.value()
        try:
            if self.source_data is not None:
                source = self.source_panel.table.current_map()
                self.source_panel.set_map(source, editable=True, decimals=decimals)
            if self.result is not None and not self.result_stale:
                self.result_panel.set_map(
                    self.result.map_data,
                    self.result.extrapolated_mask,
                    editable=True,
                    decimals=decimals,
                )
                self.delta_panel.set_map(
                    self.result.delta_vs_bilinear,
                    self.result.extrapolated_mask,
                    diverging=True,
                    decimals=decimals,
                )
        except MapValidationError:
            pass

    def _method_changed(self) -> None:
        hints = {
            "bilinear": "Local, predictable, and unable to overshoot inside a source cell.",
            "pchip": "Smoother inside the known domain; review VS BILINEAR before copying.",
            "nearest": "Preserves discrete levels. Avoid for normal fuel or ignition surfaces.",
        }
        if hasattr(self, "method_hint"):
            self.method_hint.setText(hints[self.method_combo.currentData()])

    def _extrapolation_changed(self) -> None:
        self.limit_row.setVisible(self.extrapolation_combo.currentData() == "linear")

    def show_clipboard_guide(self) -> None:
        QMessageBox.information(
            self,
            "RomRaider clipboard guide",
            "For a one-step import, use RomRaider's Copy Table command. The clipboard "
            "starts with [Table3D] and includes both axes.\n\n"
            "Ctrl+C on selected Z cells creates [Selection3D], which has no axes. ECU Map "
            "Studio can apply that selection after a full source table is already loaded.\n\n"
            "Excel-style TSV with a blank top-left cell, X values across the first row, and "
            "Y values down the first column is also accepted.\n\n"
            "RomRaider [Table2D] curves contain an X row and a value row. Pasting one in "
            "the main window opens it automatically in the dedicated 2D Curve Tool.",
        )

    def show_about(self) -> None:
        QMessageBox.about(
            self,
            "About ECU Map Studio",
            "<b>ECU Map Studio 1.0</b><br><br>"
            "Rectilinear X/Y/Z map and one-axis curve resampling with direct RomRaider "
            "clipboard support, heat maps, live cross-section plots, interactive 3D surfaces, "
            "conservative extrapolation controls, and deterministic smoothing.<br><br>"
            "Numerical output must be reviewed and "
            "validated by the tuner.",
        )

    def _error(self, message: str, title: str) -> None:
        QMessageBox.warning(self, title, message)
        self.statusBar().showMessage(message, 7000)
