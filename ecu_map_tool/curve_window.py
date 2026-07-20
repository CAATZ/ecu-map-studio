from __future__ import annotations

from pathlib import Path

import numpy as np
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QKeySequence
from PyQt5.QtWidgets import (
    QAction,
    QApplication,
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
    QSizePolicy,
    QSpinBox,
    QSplitter,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from .clipboard import (
    ClipboardFormatError,
    format_excel_curve,
    format_romraider_curve,
    parse_clipboard,
)
from .curve import (
    CURVE_METHOD_LABELS,
    CurveResampleResult,
    detect_curve_anomalies,
    repair_curve_selection,
    resample_curve,
    smooth_entire_curve,
)
from .curve_widgets import CurvePanel
from .features import MATH_OPERATIONS, apply_curve_math
from .history import UndoHistory
from .interpolation import EXTRAPOLATION_LABELS
from .model import (
    CurveData,
    MapValidationError,
    axis_to_text,
    format_number,
    generate_even_axis,
    parse_axis_text,
    parse_number_text,
)
from .project import (
    curve_from_dict,
    curve_result_from_dict,
    curve_result_to_dict,
    curve_to_dict,
    load_project,
    save_project,
)
from .widgets import ReadableTabWidget, WheelSafeComboBox, card_frame, section_header


def _curves_equal(left: CurveData, right: CurveData) -> bool:
    return (
        left.name == right.name
        and np.array_equal(left.x, right.x)
        and np.array_equal(left.values, right.values)
    )


class CurveDataDialog(QDialog):
    def __init__(self, curve: CurveData | None = None, parent=None) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WA_DeleteOnClose, True)
        self.setWindowTitle("Define 2D curve")
        self.setMinimumWidth(620)
        self.curve_data: CurveData | None = None
        self._curve_name = curve.name if curve is not None else "Manual curve"

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        intro = QLabel("Enter the X breakpoints and one corresponding curve value for each point.")
        intro.setObjectName("Muted")
        intro.setWordWrap(True)
        layout.addWidget(intro)

        layout.addWidget(QLabel("X axis"))
        self.x_edit = QPlainTextEdit(axis_to_text(curve.x, 6) if curve is not None else "0, 1")
        self.x_edit.setMaximumHeight(86)
        layout.addWidget(self.x_edit)
        layout.addWidget(QLabel("Values"))
        self.values_edit = QPlainTextEdit(
            axis_to_text(curve.values) if curve is not None else "0, 0"
        )
        self.values_edit.setMaximumHeight(86)
        layout.addWidget(self.values_edit)

        buttons = QDialogButtonBox(QDialogButtonBox.Cancel | QDialogButtonBox.Ok)
        buttons.accepted.connect(self._accept_data)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _accept_data(self) -> None:
        try:
            x = parse_axis_text(self.x_edit.toPlainText(), "X")
            raw_values = self.values_edit.toPlainText().strip()
            if not raw_values:
                raise MapValidationError("Curve values are empty.")
            import re

            tokens = [token for token in re.split(r"[,;\s]+", raw_values) if token]
            values = np.asarray([float(token) for token in tokens], dtype=float)
            self.curve_data = CurveData(
                x,
                values,
                name=self._curve_name,
            )
        except (MapValidationError, ValueError) as exc:
            QMessageBox.warning(self, "Invalid curve", str(exc))
            return
        self.accept()


class CurveSmoothingPreviewDialog(QDialog):
    def __init__(
        self,
        source: CurveData,
        proposed: CurveData,
        warning: str,
        decimals: int,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Review curve smoothing")
        self.resize(1120, 650)
        self.setMinimumSize(880, 520)
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

        delta = CurveData(source.x, proposed.values - source.values, "Smoothing difference")
        changed = int(np.count_nonzero(~np.isclose(delta.values, 0.0, atol=1e-12)))
        maximum = float(np.max(np.abs(delta.values)))
        splitter = QSplitter(Qt.Horizontal)
        self.proposed_panel = CurvePanel(
            "Proposed curve", "Values after the deterministic smoothing operation."
        )
        self.proposed_panel.set_curve(proposed, decimals=decimals)
        self.proposed_panel.set_badges([(f"{changed} changed", changed > 0)])
        self.difference_panel = CurvePanel(
            "Smoothing difference", "Blue decreases values; red increases values."
        )
        self.difference_panel.set_curve(delta, diverging=True, decimals=decimals)
        self.difference_panel.set_badges([(f"Max Δ {maximum:.6g}", maximum > 0)])
        splitter.addWidget(self.proposed_panel)
        splitter.addWidget(self.difference_panel)
        splitter.setSizes([560, 560])
        layout.addWidget(splitter, 1)

        buttons = QDialogButtonBox(QDialogButtonBox.Cancel | QDialogButtonBox.Apply)
        buttons.button(QDialogButtonBox.Apply).setText("Apply smoothing")
        buttons.button(QDialogButtonBox.Apply).setObjectName("PrimaryButton")
        buttons.button(QDialogButtonBox.Apply).clicked.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)


class CurveSelectionMathDialog(QDialog):
    def __init__(self, selected_count: int, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Curve selection math")
        self.setMinimumWidth(430)
        layout = QVBoxLayout(self)
        note = QLabel(
            f"Apply one operation to {selected_count} selected curve points. "
            "The change can be undone with Ctrl+Z."
        )
        note.setObjectName("Muted")
        note.setWordWrap(True)
        layout.addWidget(note)
        form = QFormLayout()
        self.operation = WheelSafeComboBox()
        for key, label in MATH_OPERATIONS.items():
            self.operation.addItem(label, key)
        self.value = QDoubleSpinBox()
        self.value.setRange(-1e12, 1e12)
        self.value.setDecimals(4)
        self.second_value = QDoubleSpinBox()
        self.second_value.setRange(-1e12, 1e12)
        self.second_value.setDecimals(4)
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
        buttons.button(QDialogButtonBox.Apply).clicked.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _operation_changed(self) -> None:
        clamp = self.operation.currentData() == "clamp"
        self.second_label.setVisible(clamp)
        self.second_value.setVisible(clamp)


class CurveWindow(QMainWindow):
    def __init__(self, curve: CurveData | None = None, parent=None) -> None:
        super().__init__(parent)
        self.source_data: CurveData | None = None
        self.result: CurveResampleResult | None = None
        self.result_stale = False
        self.history = UndoHistory[CurveData](_curves_equal)
        self.project_path: str | None = None

        self.setWindowTitle("ECU Map Studio — 2D Curve")
        self.resize(1280, 790)
        self.setMinimumSize(980, 650)
        self._build_ui()
        self._build_menu()
        self.statusBar().showMessage("Ready — paste a RomRaider [Table2D] curve to begin.")
        if curve is not None:
            self.set_source_curve(curve)

    def _build_ui(self) -> None:
        root = QWidget()
        root.setObjectName("AppRoot")
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._top_bar())

        self.main_splitter = QSplitter(Qt.Horizontal)
        self.main_splitter.setChildrenCollapsible(False)
        self.main_splitter.setOpaqueResize(False)
        self.main_splitter.addWidget(self._sidebar())
        self.main_splitter.addWidget(self._workspace())
        self.main_splitter.setSizes([400, 880])
        self.main_splitter.setStretchFactor(0, 0)
        self.main_splitter.setStretchFactor(1, 1)
        layout.addWidget(self.main_splitter, 1)

    def _top_bar(self) -> QWidget:
        bar = QFrame()
        bar.setObjectName("TopBar")
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(24, 13, 24, 13)
        layout.setSpacing(13)
        logo = QLabel("2D")
        logo.setAlignment(Qt.AlignCenter)
        logo.setFixedSize(48, 42)
        logo.setStyleSheet(
            "background:#35d0df;color:#061017;border-radius:12px;font-size:14pt;font-weight:900;"
        )
        layout.addWidget(logo)
        titles = QVBoxLayout()
        titles.setSpacing(0)
        title = QLabel("2D Curve Studio")
        title.setObjectName("AppTitle")
        subtitle = QLabel("One axis  •  One value series  •  RomRaider [Table2D]")
        subtitle.setObjectName("AppSubtitle")
        titles.addWidget(title)
        titles.addWidget(subtitle)
        layout.addLayout(titles)
        layout.addStretch(1)
        badge = QLabel("X → VALUE")
        badge.setObjectName("Badge")
        layout.addWidget(badge)
        return bar

    def _sidebar(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setMinimumWidth(380)
        scroll.setMaximumWidth(560)
        body = QWidget()
        body.setObjectName("SidebarBody")
        body.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        layout = QVBoxLayout(body)
        layout.setContentsMargins(14, 14, 14, 18)
        layout.setSpacing(12)
        layout.addWidget(self._source_card())
        layout.addWidget(self._target_card())
        layout.addWidget(self._method_card())
        layout.addStretch(1)
        note = QLabel(
            "Curve extrapolation and smoothing can alter engine behavior. Review the plot, "
            "values, and differences before copying."
        )
        note.setObjectName("FieldHint")
        note.setWordWrap(True)
        layout.addWidget(note)
        scroll.setWidget(body)
        return scroll

    def _source_card(self) -> QWidget:
        card, layout = card_frame()
        layout.addLayout(section_header(1, "Source curve"))
        paste_button = QPushButton("Paste RomRaider [Table2D]")
        paste_button.setObjectName("PrimaryButton")
        paste_button.clicked.connect(self.paste_from_clipboard)
        layout.addWidget(paste_button)
        row = QHBoxLayout()
        new_button = QPushButton("New blank")
        new_button.setObjectName("GhostButton")
        new_button.clicked.connect(self.new_blank_curve)
        demo_button = QPushButton("Load demo")
        demo_button.setObjectName("GhostButton")
        demo_button.clicked.connect(self.load_demo_curve)
        row.addWidget(new_button)
        row.addWidget(demo_button)
        layout.addLayout(row)
        self.clear_session_button = QPushButton("Clear curve / New session")
        self.clear_session_button.setObjectName("GhostButton")
        self.clear_session_button.setEnabled(False)
        self.clear_session_button.clicked.connect(self.new_session)
        layout.addWidget(self.clear_session_button)
        self.source_summary = QLabel("No curve loaded")
        self.source_summary.setObjectName("Muted")
        self.source_summary.setWordWrap(True)
        layout.addWidget(self.source_summary)
        return card

    def _target_card(self) -> QWidget:
        card, layout = card_frame()
        layout.addLayout(section_header(2, "Target axis"))
        self.target_mode_tabs = QTabWidget()
        self.target_mode_tabs.setObjectName("ModeTabs")

        automatic = QWidget()
        automatic_layout = QVBoxLayout(automatic)
        automatic_layout.setContentsMargins(8, 10, 8, 8)
        automatic_layout.setSpacing(9)
        automatic_note = QLabel(
            "Set the target limits and point count. Endpoints are included with constant spacing."
        )
        automatic_note.setObjectName("FieldHint")
        automatic_note.setWordWrap(True)
        automatic_layout.addWidget(automatic_note)
        row = QGridLayout()
        row.addWidget(QLabel("Points"), 0, 0)
        row.addWidget(QLabel("Minimum"), 0, 1)
        row.addWidget(QLabel("Maximum"), 0, 2)
        self.point_count = QSpinBox()
        self.point_count.setRange(2, 512)
        self.point_count.setValue(20)
        self.x_min_edit = QLineEdit()
        self.x_max_edit = QLineEdit()
        row.addWidget(self.point_count, 1, 0)
        row.addWidget(self.x_min_edit, 1, 1)
        row.addWidget(self.x_max_edit, 1, 2)
        row.setColumnStretch(1, 1)
        row.setColumnStretch(2, 1)
        automatic_layout.addLayout(row)
        self.spacing_preview = QLabel("Enter a valid minimum and maximum.")
        self.spacing_preview.setObjectName("FieldHint")
        self.spacing_preview.setWordWrap(True)
        automatic_layout.addWidget(self.spacing_preview)
        reset_button = QPushButton("Reset limits to source curve")
        reset_button.setObjectName("GhostButton")
        reset_button.clicked.connect(self.reset_auto_range)
        automatic_layout.addWidget(reset_button)

        custom = QWidget()
        custom_layout = QVBoxLayout(custom)
        custom_layout.setContentsMargins(8, 10, 8, 8)
        custom_layout.setSpacing(9)
        custom_layout.addWidget(QLabel("Target X breakpoints"))
        self.target_x_edit = QPlainTextEdit()
        self.target_x_edit.setPlaceholderText("Paste or enter target X values…")
        self.target_x_edit.setMaximumHeight(92)
        custom_layout.addWidget(self.target_x_edit)
        source_button = QPushButton("Use source axis")
        source_button.setObjectName("GhostButton")
        source_button.clicked.connect(self.use_source_axis)
        custom_layout.addWidget(source_button)

        self.target_mode_tabs.addTab(automatic, "AUTOMATIC RANGE")
        self.target_mode_tabs.addTab(custom, "CUSTOM AXIS")
        layout.addWidget(self.target_mode_tabs)
        self.point_count.valueChanged.connect(self._update_spacing_preview)
        self.x_min_edit.textChanged.connect(self._update_spacing_preview)
        self.x_max_edit.textChanged.connect(self._update_spacing_preview)
        self.x_min_edit.textEdited.connect(
            lambda _text: self._clear_exact_axis_value(self.x_min_edit)
        )
        self.x_max_edit.textEdited.connect(
            lambda _text: self._clear_exact_axis_value(self.x_max_edit)
        )
        return card

    def _method_card(self) -> QWidget:
        card, layout = card_frame()
        layout.addLayout(section_header(3, "Resampling"))
        layout.addWidget(QLabel("Interpolation method"))
        self.method_combo = WheelSafeComboBox()
        self.method_combo.addItem("Linear", "linear")
        self.method_combo.addItem("PCHIP", "pchip")
        self.method_combo.addItem("Nearest", "nearest")
        layout.addWidget(self.method_combo)
        layout.addWidget(QLabel("Outside the source axis"))
        self.extrapolation_combo = WheelSafeComboBox()
        self.extrapolation_combo.addItem("Hold", "hold")
        self.extrapolation_combo.addItem("Linear", "linear")
        self.extrapolation_combo.addItem("Disabled", "disallow")
        self.extrapolation_combo.currentIndexChanged.connect(self._extrapolation_changed)
        layout.addWidget(self.extrapolation_combo)
        self.limit_row = QWidget()
        limit_layout = QHBoxLayout(self.limit_row)
        limit_layout.setContentsMargins(0, 0, 0, 0)
        limit_layout.addWidget(QLabel("Maximum edge intervals"))
        self.edge_limit = QDoubleSpinBox()
        self.edge_limit.setRange(0.1, 10.0)
        self.edge_limit.setValue(1.0)
        self.edge_limit.setSingleStep(0.25)
        limit_layout.addWidget(self.edge_limit)
        self.limit_row.setVisible(False)
        layout.addWidget(self.limit_row)
        decimals_row = QHBoxLayout()
        decimals_row.addWidget(QLabel("Displayed decimals"))
        self.decimals = QSpinBox()
        self.decimals.setRange(0, 8)
        self.decimals.setValue(3)
        self.decimals.valueChanged.connect(self._refresh_precision)
        decimals_row.addWidget(self.decimals)
        layout.addLayout(decimals_row)
        self.generate_button = QPushButton("Generate resampled curve")
        self.generate_button.setObjectName("GenerateButton")
        self.generate_button.setEnabled(False)
        self.generate_button.clicked.connect(self.generate_result)
        layout.addWidget(self.generate_button)
        return card

    def _workspace(self) -> QWidget:
        container = QWidget()
        container.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Expanding)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(10, 12, 16, 12)
        layout.setSpacing(0)
        self.tabs = ReadableTabWidget()
        self.source_panel = CurvePanel(
            "Source curve", "Double-click a value cell to edit it before resampling."
        )
        self.result_panel = CurvePanel(
            "Resampled curve", "Amber points are outside the original source-axis range."
        )
        self.delta_panel = CurvePanel(
            "Difference vs linear", "Blue is lower; red is higher than linear interpolation."
        )

        self.smoothing_button = QPushButton("Smooth")
        self.smoothing_button.setObjectName("GhostButton")
        self.smoothing_button.setEnabled(False)
        smoothing_menu = QMenu(self.smoothing_button)
        smoothing_menu.addAction("Detect suspicious points", self.detect_anomalies)
        smoothing_menu.addAction("Repair selected points…", self.repair_selection)
        smoothing_menu.addAction("Smooth entire curve…", self.smooth_curve)
        smoothing_menu.addSeparator()
        self.undo_action = smoothing_menu.addAction("Undo last source change", self.undo_smoothing)
        self.undo_action.setEnabled(False)
        self.smoothing_button.setMenu(smoothing_menu)
        self.source_panel.add_action(self.smoothing_button)
        self.math_button = QPushButton("Math")
        self.math_button.setObjectName("GhostButton")
        self.math_button.setToolTip("Apply math to selected curve points")
        self.math_button.setEnabled(False)
        self.math_button.clicked.connect(self.open_selection_math)
        self.source_panel.add_action(self.math_button)
        edit_button = QPushButton("Edit")
        edit_button.setObjectName("GhostButton")
        edit_button.setToolTip("Edit the source axis and values")
        edit_button.clicked.connect(self.edit_source_data)
        self.source_panel.add_action(edit_button)
        self.copy_source_button = QPushButton("Copy")
        self.copy_source_button.setObjectName("GhostButton")
        self.copy_source_button.setToolTip("Copy the source curve for RomRaider")
        self.copy_source_button.setEnabled(False)
        self.copy_source_button.clicked.connect(self.copy_source)
        self.source_panel.add_action(self.copy_source_button)

        self.copy_tsv_button = QPushButton("TSV")
        self.copy_tsv_button.setToolTip("Copy the result as tab-separated values")
        self.copy_tsv_button.setEnabled(False)
        self.copy_tsv_button.clicked.connect(self.copy_result_tsv)
        self.result_panel.add_action(self.copy_tsv_button)
        self.copy_result_button = QPushButton("Copy RR")
        self.copy_result_button.setObjectName("PrimaryButton")
        self.copy_result_button.setToolTip("Copy the complete curve for RomRaider")
        self.copy_result_button.setEnabled(False)
        self.copy_result_button.clicked.connect(self.copy_result)
        self.result_panel.add_action(self.copy_result_button)

        self.source_panel.table.pasteRequested.connect(self.paste_from_clipboard)
        self.source_panel.table.dataEdited.connect(self._source_edited)
        self.tabs.addTab(self.source_panel, "SOURCE")
        self.tabs.addTab(self.result_panel, "RESULT")
        self.tabs.addTab(self.delta_panel, "VS LINEAR")
        self.tabs.setTabToolTip(0, "Editable source curve")
        self.tabs.setTabToolTip(1, "Generated curve")
        self.tabs.setTabToolTip(2, "Generated curve minus the linear reference")
        self.tabs.setTabEnabled(1, False)
        self.tabs.setTabEnabled(2, False)
        layout.addWidget(self.tabs)
        return container

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
        new_session_action = QAction("New session / Clear curve", self)
        new_session_action.setShortcut(QKeySequence("Ctrl+N"))
        new_session_action.triggered.connect(self.new_session)
        file_menu.addAction(new_session_action)
        file_menu.addSeparator()
        paste_action = QAction("Paste 2D curve", self)
        paste_action.triggered.connect(self.paste_from_clipboard)
        file_menu.addAction(paste_action)
        copy_action = QAction("Copy result for RomRaider", self)
        copy_action.setShortcut(QKeySequence("Ctrl+Shift+C"))
        copy_action.triggered.connect(self.copy_result)
        file_menu.addAction(copy_action)
        file_menu.addSeparator()
        close_action = QAction("Close curve tool", self)
        close_action.triggered.connect(self.close)
        file_menu.addAction(close_action)

        edit_menu = self.menuBar().addMenu("Edit")
        self.undo_action.setShortcut(QKeySequence.Undo)
        edit_menu.addAction(self.undo_action)
        self.redo_action = QAction("Redo", self)
        self.redo_action.setShortcut(QKeySequence.Redo)
        self.redo_action.setEnabled(False)
        self.redo_action.triggered.connect(self.redo_source)
        edit_menu.addAction(self.redo_action)
        edit_menu.addSeparator()
        math_action = QAction("Selection math…", self)
        math_action.triggered.connect(self.open_selection_math)
        edit_menu.addAction(math_action)

    def set_source_curve(
        self,
        curve: CurveData,
        reset_target: bool = True,
        *,
        history_mode: str | None = None,
    ) -> None:
        if history_mode is None:
            history_mode = "reset" if reset_target or self.source_data is None else "record"
        if history_mode == "reset":
            self.history.reset(curve)
        elif history_mode == "record":
            self.history.record(curve)
        elif history_mode != "preserve":
            raise ValueError(f"Unknown history mode: {history_mode}")
        self.source_data = curve
        self.source_panel.set_curve(curve, editable=True, decimals=self.decimals.value())
        minimum, maximum = curve.value_range
        self.source_panel.set_badges(
            [(f"{curve.size} points", False), (f"V {minimum:.4g}…{maximum:.4g}", False)]
        )
        self.source_summary.setText(
            f"Loaded {curve.size} points\nX: {curve.x[0]:.7g} → {curve.x[-1]:.7g}  •  "
            f"Values: {minimum:.5g} → {maximum:.5g}"
        )
        self.copy_source_button.setEnabled(True)
        self.clear_session_button.setEnabled(True)
        self.generate_button.setEnabled(True)
        self.smoothing_button.setEnabled(True)
        self.math_button.setEnabled(True)
        self.save_project_action.setEnabled(True)
        self.save_project_as_action.setEnabled(True)
        if reset_target:
            self.target_mode_tabs.setCurrentIndex(0)
            self.point_count.setValue(curve.size)
            self.use_source_axis()
        self._invalidate_result("Source curve loaded — configure the target axis and generate.")
        self.tabs.setCurrentIndex(0)
        self._update_history_actions()

    def new_session(self, _checked: bool = False, *, confirm: bool = True) -> bool:
        """Return the curve workspace to its initial empty state."""
        has_session_data = self.source_data is not None or self.result is not None
        if confirm and has_session_data:
            answer = QMessageBox.question(
                self,
                "Start a new curve session?",
                "This clears the source curve, generated result, difference curve, target "
                "axis, and smoothing undo history. It does not alter the clipboard or "
                "RomRaider. Continue?",
                QMessageBox.Yes | QMessageBox.Cancel,
                QMessageBox.Cancel,
            )
            if answer != QMessageBox.Yes:
                return False

        self.source_data = None
        self.result = None
        self.result_stale = False
        self.history.clear()
        self.project_path = None
        self.setWindowTitle("ECU Map Studio — 2D Curve")
        self._update_history_actions()

        self.source_panel.clear_curve()
        self.result_panel.clear_curve()
        self.delta_panel.clear_curve()
        self.source_panel.subtitle_label.setText(
            "Double-click a value cell to edit it before resampling."
        )
        self.result_panel.subtitle_label.setText(
            "Amber points are outside the original source-axis range."
        )
        self.delta_panel.subtitle_label.setText(
            "Blue is lower; red is higher than linear interpolation."
        )
        self.source_summary.setText("No curve loaded")

        self.target_mode_tabs.setCurrentIndex(0)
        self.point_count.setValue(20)
        self.x_min_edit.clear()
        self.x_max_edit.clear()
        self.target_x_edit.clear()
        self.method_combo.setCurrentIndex(0)
        self.extrapolation_combo.setCurrentIndex(0)
        self.edge_limit.setValue(1.0)
        self.spacing_preview.setText("Enter a valid minimum and maximum.")
        self.spacing_preview.setStyleSheet("")

        self.tabs.setTabEnabled(1, False)
        self.tabs.setTabEnabled(2, False)
        self.tabs.setCurrentIndex(0)
        self.copy_source_button.setEnabled(False)
        self.copy_result_button.setEnabled(False)
        self.copy_tsv_button.setEnabled(False)
        self.clear_session_button.setEnabled(False)
        self.generate_button.setEnabled(False)
        self.smoothing_button.setEnabled(False)
        self.math_button.setEnabled(False)
        self.save_project_action.setEnabled(False)
        self.save_project_as_action.setEnabled(False)
        self.statusBar().showMessage(
            "New curve session ready — paste [Table2D] or create a blank curve.", 7000
        )
        return True

    def paste_from_clipboard(self) -> None:
        text = QApplication.clipboard().text()
        if not text.strip():
            self._error("Clipboard is empty.", "Nothing to paste")
            return
        try:
            payload = parse_clipboard(text, name="Clipboard 2D curve")
            if payload.kind == "curve" and payload.curve_data is not None:
                self.set_source_curve(payload.curve_data)
                self.statusBar().showMessage("RomRaider [Table2D] curve imported.", 5000)
                return
            if payload.kind == "curve_selection" and payload.selection is not None:
                self._apply_selection(payload.selection)
                return
            raise ClipboardFormatError(
                "Clipboard contains a 3D map. Paste it in the main ECU Map Studio window."
            )
        except (ClipboardFormatError, MapValidationError) as exc:
            self._error(str(exc), "Clipboard format not recognized")

    def _apply_selection(self, selection: np.ndarray) -> None:
        if self.source_data is None:
            raise ClipboardFormatError(
                "[Selection1D] contains values but no X axis. Load a full [Table2D] first."
            )
        source = self.source_panel.table.current_curve()
        selected_columns = self.source_panel.table.selected_columns()
        start = selected_columns[0] if selected_columns else 0
        stop = start + selection.size
        if stop > source.size:
            raise ClipboardFormatError("The 1D selection does not fit from the selected point.")
        values = source.values.copy()
        numeric = np.isfinite(selection)
        destination = values[start:stop]
        destination[numeric] = selection[numeric]
        self.set_source_curve(CurveData(source.x, values, source.name), reset_target=False)

    def new_blank_curve(self) -> None:
        dialog = CurveDataDialog(parent=self)
        if dialog.exec_() == QDialog.Accepted and dialog.curve_data is not None:
            self.set_source_curve(dialog.curve_data)

    def edit_source_data(self) -> None:
        try:
            source = self.source_panel.table.current_curve()
        except MapValidationError as exc:
            self._error(str(exc), "Nothing to edit")
            return
        dialog = CurveDataDialog(source, self)
        if dialog.exec_() == QDialog.Accepted and dialog.curve_data is not None:
            self.set_source_curve(dialog.curve_data, history_mode="record")

    def load_demo_curve(self) -> None:
        x = np.asarray([0.10, 0.20, 0.35, 0.50, 0.70, 0.90, 1.10, 1.30, 1.50])
        values = np.asarray([1.15, 1.35, 1.72, 2.15, 2.85, 3.70, 4.65, 5.75, 7.0])
        self.set_source_curve(CurveData(x, values, "Demo load-to-injection curve"))
        self.point_count.setValue(20)
        self.statusBar().showMessage("Demo curve loaded. It is not calibration data.", 6000)

    def use_source_axis(self) -> None:
        if self.source_data is None:
            return
        self.target_x_edit.setPlainText(axis_to_text(self.source_data.x, 6))
        self.point_count.setValue(self.source_data.size)
        self.reset_auto_range()

    def reset_auto_range(self) -> None:
        if self.source_data is None:
            return
        self._set_exact_axis_value(self.x_min_edit, np.min(self.source_data.x))
        self._set_exact_axis_value(self.x_max_edit, np.max(self.source_data.x))
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

    def _automatic_axis(self) -> np.ndarray:
        minimum = self._axis_input_value(self.x_min_edit, "X minimum")
        maximum = self._axis_input_value(self.x_max_edit, "X maximum")
        return generate_even_axis(minimum, maximum, self.point_count.value(), "Target X")

    def _selected_target_axis(self) -> np.ndarray:
        if self.target_mode_tabs.currentIndex() == 0:
            axis = self._automatic_axis()
            self.target_x_edit.setPlainText(axis_to_text(axis, 6))
            return axis
        return parse_axis_text(self.target_x_edit.toPlainText(), "Target X")

    def _update_spacing_preview(self) -> None:
        if not hasattr(self, "spacing_preview"):
            return
        try:
            axis = self._automatic_axis()
            extends = False
            if self.source_data is not None:
                extends = axis[0] < np.min(self.source_data.x) or axis[-1] > np.max(
                    self.source_data.x
                )
            suffix = " • extends beyond source limits" if extends else " • inside source limits"
            self.spacing_preview.setText(f"Spacing: {format_number(axis[1] - axis[0], 6)}{suffix}")
            self.spacing_preview.setStyleSheet("color:#f5b942;" if extends else "color:#8e9cb1;")
        except MapValidationError as exc:
            self.spacing_preview.setText(str(exc))
            self.spacing_preview.setStyleSheet("color:#f5b942;")

    def generate_result(self) -> None:
        try:
            source = self.source_panel.table.current_curve()
            target = self._selected_target_axis()
            result = resample_curve(
                source,
                target,
                method=self.method_combo.currentData(),
                extrapolation=self.extrapolation_combo.currentData(),
                maximum_edge_intervals=self.edge_limit.value(),
            )
        except (MapValidationError, ValueError) as exc:
            self._error(str(exc), "Unable to generate curve")
            return
        self.source_data = source
        self.result = result
        self.result_stale = False
        decimals = self.decimals.value()
        self.result_panel.set_curve(result.curve_data, result.extrapolated_mask, decimals=decimals)
        self.delta_panel.set_curve(
            result.delta_vs_linear,
            result.extrapolated_mask,
            diverging=True,
            decimals=decimals,
        )
        method = CURVE_METHOD_LABELS[result.method]
        warnings = result.extrapolated_points
        self.result_panel.set_badges(
            [
                (f"{result.curve_data.size} points", False),
                (method, False),
                (f"{warnings} extrapolated", warnings > 0),
            ]
        )
        self.result_panel.subtitle_label.setText(
            f"{method} interpolation • {EXTRAPOLATION_LABELS[result.extrapolation]}"
        )
        self.tabs.setTabEnabled(1, True)
        self.tabs.setTabEnabled(2, result.method != "linear")
        self.tabs.setCurrentIndex(1)
        self.copy_result_button.setEnabled(True)
        self.copy_tsv_button.setEnabled(True)
        self.statusBar().showMessage(
            f"Generated {result.curve_data.size}-point curve; {warnings} extrapolated points.",
            7000,
        )

    def detect_anomalies(self) -> None:
        try:
            source = self.source_panel.table.current_curve()
        except MapValidationError as exc:
            self._error(str(exc), "Cannot inspect curve")
            return
        result = detect_curve_anomalies(source)
        self.source_panel.table.select_mask(result.mask)
        self.tabs.setCurrentIndex(0)
        self.source_panel.set_badges(
            [(f"{source.size} points", False), (f"{result.count} suspicious", result.count > 0)]
        )
        self.statusBar().showMessage(
            f"Selected {result.count} statistically suspicious interior points; no values changed.",
            8000,
        )

    def repair_selection(self) -> None:
        try:
            source = self.source_panel.table.current_curve()
        except MapValidationError as exc:
            self._error(str(exc), "Cannot repair curve")
            return
        columns = self.source_panel.table.selected_columns()
        if not columns:
            self._error("Select curve values to reconstruct first.", "No points selected")
            return
        mask = np.zeros(source.size, dtype=bool)
        mask[columns] = True
        if mask[0] or mask[-1]:
            answer = QMessageBox.warning(
                self,
                "Selection touches a curve edge",
                "Edge repair requires one-sided extrapolation from the nearest unchanged "
                "points and is less constrained. Continue to preview?",
                QMessageBox.Yes | QMessageBox.Cancel,
                QMessageBox.Cancel,
            )
            if answer != QMessageBox.Yes:
                return
        try:
            proposed = repair_curve_selection(source, mask)
        except MapValidationError as exc:
            self._error(str(exc), "Cannot repair selection")
            return
        self._preview_smoothing(
            source,
            proposed,
            "Only selected curve points will change. Unselected points remain fixed.",
            "Selected-point repair",
        )

    def smooth_curve(self) -> None:
        try:
            source = self.source_panel.table.current_curve()
        except MapValidationError as exc:
            self._error(str(exc), "Cannot smooth curve")
            return
        answer = QMessageBox.warning(
            self,
            "Smooth the entire curve?",
            "Whole-curve smoothing changes calibration values and can alter engine behavior "
            "positively or adversely. Continue to a difference preview?",
            QMessageBox.Yes | QMessageBox.Cancel,
            QMessageBox.Cancel,
        )
        if answer != QMessageBox.Yes:
            return
        self._preview_smoothing(
            source,
            smooth_entire_curve(source),
            "WARNING: one deterministic local-line smoothing pass will affect the complete curve.",
            "Whole-curve smoothing",
        )

    def _preview_smoothing(
        self,
        source: CurveData,
        proposed: CurveData,
        warning: str,
        operation: str,
    ) -> None:
        dialog = CurveSmoothingPreviewDialog(source, proposed, warning, self.decimals.value(), self)
        if dialog.exec_() != QDialog.Accepted:
            self.statusBar().showMessage("Smoothing cancelled; no values changed.", 5000)
            return
        self.set_source_curve(proposed, reset_target=False)
        changed = int(np.count_nonzero(~np.isclose(proposed.values, source.values, atol=1e-12)))
        self.statusBar().showMessage(
            f"{operation} applied to {changed} points. Undo is available with Ctrl+Z.",
            8000,
        )

    def undo_smoothing(self) -> None:
        self.undo_source()

    def _update_history_actions(self) -> None:
        if hasattr(self, "undo_action"):
            self.undo_action.setEnabled(self.history.can_undo)
        if hasattr(self, "redo_action"):
            self.redo_action.setEnabled(self.history.can_redo)

    def undo_source(self) -> None:
        previous = self.history.undo()
        if previous is None:
            return
        self.set_source_curve(previous, reset_target=False, history_mode="preserve")
        self._update_history_actions()
        self.statusBar().showMessage("Curve source change undone.", 5000)

    def redo_source(self) -> None:
        following = self.history.redo()
        if following is None:
            return
        self.set_source_curve(following, reset_target=False, history_mode="preserve")
        self._update_history_actions()
        self.statusBar().showMessage("Curve source change redone.", 5000)

    def open_selection_math(self) -> None:
        if self.source_data is None:
            self._error("Load a source curve first.", "No source curve")
            return
        columns = self.source_panel.table.selected_columns()
        if not columns:
            self._error("Select one or more curve points first.", "No points selected")
            return
        dialog = CurveSelectionMathDialog(len(columns), self)
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
            source = self.source_panel.table.current_curve()
            mask = np.zeros(source.size, dtype=bool)
            mask[self.source_panel.table.selected_columns()] = True
            proposed = apply_curve_math(source, mask, operation, value, second_value)
        except MapValidationError as exc:
            self._error(str(exc), "Cannot apply curve selection math")
            return
        changed = int(np.count_nonzero(~np.isclose(source.values, proposed.values, atol=1e-12)))
        self.set_source_curve(proposed, reset_target=False)
        self.source_panel.set_badges(
            [(f"{proposed.size} points", False), (f"{changed} changed", changed > 0)]
        )
        self.statusBar().showMessage(
            f"{MATH_OPERATIONS[operation]} applied to {int(np.count_nonzero(mask))} points; "
            "Ctrl+Z restores the previous values.",
            7000,
        )

    def _project_document(self) -> dict:
        source = self.source_panel.table.current_curve()
        settings = {
            "target_mode": self.target_mode_tabs.currentIndex(),
            "points": self.point_count.value(),
            "x_min": self.x_min_edit.text(),
            "x_max": self.x_max_edit.text(),
            "target_x": self.target_x_edit.toPlainText(),
            "method": self.method_combo.currentData(),
            "extrapolation": self.extrapolation_combo.currentData(),
            "edge_limit": self.edge_limit.value(),
            "decimals": self.decimals.value(),
        }
        return {
            "kind": "curve",
            "source": curve_to_dict(source),
            "result": (
                curve_result_to_dict(self.result)
                if self.result is not None and not self.result_stale
                else None
            ),
            "settings": settings,
        }

    def save_project_file(
        self, _checked: bool = False, *, save_as: bool = False, path=None
    ) -> bool:
        if self.source_data is None:
            self._error("Load a source curve before saving a project.", "Nothing to save")
            return False
        destination = str(path) if path else (None if save_as else self.project_path)
        if not destination:
            destination, _ = QFileDialog.getSaveFileName(
                self,
                "Save ECU Map Studio curve project",
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
        self.setWindowTitle(f"ECU Map Studio — 2D Curve — {Path(destination).name}")
        self.statusBar().showMessage(f"Curve project saved to {destination}", 7000)
        return True

    def open_project_file(self, _checked: bool = False, *, path=None) -> bool:
        source_path = str(path) if path else ""
        if not source_path:
            source_path, _ = QFileDialog.getOpenFileName(
                self,
                "Open ECU Map Studio curve project",
                "",
                "ECU Map Studio projects (*.ecumap *.json)",
            )
        if not source_path:
            return False
        try:
            document = load_project(source_path)
            if document["kind"] != "curve":
                raise MapValidationError("This project contains a 3D map, not a 2D curve.")
            source = curve_from_dict(document["source"])
            restored_result = (
                curve_result_from_dict(document["result"])
                if document.get("result") is not None
                else None
            )
            settings = document.get("settings", {})
        except (KeyError, MapValidationError) as exc:
            self._error(str(exc), "Unable to open project")
            return False
        self.new_session(confirm=False)
        self.set_source_curve(source, history_mode="reset")
        self.decimals.setValue(int(settings.get("decimals", self.decimals.value())))
        self.point_count.setValue(int(settings.get("points", source.size)))
        self.x_min_edit.setText(str(settings.get("x_min", self.x_min_edit.text())))
        self.x_max_edit.setText(str(settings.get("x_max", self.x_max_edit.text())))
        self.target_x_edit.setPlainText(str(settings.get("target_x", "")))
        self.target_mode_tabs.setCurrentIndex(int(settings.get("target_mode", 0)))
        method_index = self.method_combo.findData(settings.get("method", "linear"))
        self.method_combo.setCurrentIndex(max(0, method_index))
        extrapolation_index = self.extrapolation_combo.findData(
            settings.get("extrapolation", "hold")
        )
        self.extrapolation_combo.setCurrentIndex(max(0, extrapolation_index))
        self.edge_limit.setValue(float(settings.get("edge_limit", 1.0)))
        if restored_result is not None:
            self._restore_result(restored_result)
        self.project_path = source_path
        self.setWindowTitle(f"ECU Map Studio — 2D Curve — {Path(source_path).name}")
        self.statusBar().showMessage(f"Curve project opened from {source_path}", 7000)
        return True

    def _restore_result(self, result: CurveResampleResult) -> None:
        self.result = result
        self.result_stale = False
        decimals = self.decimals.value()
        self.result_panel.set_curve(result.curve_data, result.extrapolated_mask, decimals=decimals)
        self.delta_panel.set_curve(
            result.delta_vs_linear,
            result.extrapolated_mask,
            diverging=True,
            decimals=decimals,
        )
        warnings = result.extrapolated_points
        self.result_panel.set_badges(
            [
                (f"{result.curve_data.size} points", False),
                (CURVE_METHOD_LABELS[result.method], False),
                (f"{warnings} extrapolated", warnings > 0),
            ]
        )
        self.tabs.setTabEnabled(1, True)
        self.tabs.setTabEnabled(2, result.method != "linear")
        self.copy_result_button.setEnabled(True)
        self.copy_tsv_button.setEnabled(True)

    def copy_source(self) -> None:
        try:
            curve = self.source_panel.table.current_curve()
        except MapValidationError as exc:
            self._error(str(exc), "Nothing to copy")
            return
        QApplication.clipboard().setText(format_romraider_curve(curve, precision=10))
        self.statusBar().showMessage("Source [Table2D] copied for RomRaider.", 5000)

    def _current_result(self) -> CurveData:
        if self.result is None or self.result_stale:
            raise MapValidationError("Generate an up-to-date curve first.")
        return self.result.curve_data

    def copy_result(self) -> None:
        try:
            curve = self._current_result()
        except MapValidationError as exc:
            self._error(str(exc), "Nothing to copy")
            return
        QApplication.clipboard().setText(format_romraider_curve(curve, precision=10))
        self.statusBar().showMessage("Complete [Table2D] result copied for RomRaider.", 5000)

    def copy_result_tsv(self) -> None:
        try:
            curve = self._current_result()
        except MapValidationError as exc:
            self._error(str(exc), "Nothing to copy")
            return
        QApplication.clipboard().setText(format_excel_curve(curve, precision=10))
        self.statusBar().showMessage("Two-row curve copied as TSV.", 5000)

    def _source_edited(self) -> None:
        try:
            current = self.source_panel.table.current_curve()
        except MapValidationError:
            current = None
        if current is not None:
            self.source_data = current
            self.history.record(current)
            self._update_history_actions()
        self._invalidate_result("Source curve changed — generate the result again.")
        self.source_panel.set_badges([("Edited", True)])

    def _invalidate_result(self, message: str) -> None:
        if self.result is not None:
            self.result_stale = True
            self.result_panel.set_badges([("Out of date", True)])
        self.copy_result_button.setEnabled(False)
        self.copy_tsv_button.setEnabled(False)
        self.statusBar().showMessage(message, 5000)

    def _refresh_precision(self) -> None:
        decimals = self.decimals.value()
        try:
            if self.source_data is not None:
                source = self.source_panel.table.current_curve()
                self.source_panel.set_curve(source, editable=True, decimals=decimals)
            if self.result is not None and not self.result_stale:
                self.result_panel.set_curve(
                    self.result.curve_data,
                    self.result.extrapolated_mask,
                    decimals=decimals,
                )
                self.delta_panel.set_curve(
                    self.result.delta_vs_linear,
                    self.result.extrapolated_mask,
                    diverging=True,
                    decimals=decimals,
                )
        except MapValidationError:
            pass

    def _extrapolation_changed(self) -> None:
        self.limit_row.setVisible(self.extrapolation_combo.currentData() == "linear")

    def _error(self, message: str, title: str) -> None:
        QMessageBox.warning(self, title, message)
        self.statusBar().showMessage(message, 7000)
