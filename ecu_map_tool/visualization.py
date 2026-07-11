from __future__ import annotations

import numpy as np
from PyQt5.QtCore import QSize, Qt
from PyQt5.QtGui import QColor, QIcon, QPainter, QPixmap
from PyQt5.QtWidgets import (
    QCheckBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSplitter,
    QToolButton,
    QVBoxLayout,
)

from .curve_widgets import CurvePanel
from .model import (
    CurveData,
    MapData,
    MapValidationError,
    collapse_duplicate_map,
    format_number,
)
from .widgets import MapPanel


class MapSliceDialog(QDialog):
    """Live X/Y cross-sections through the selected heat-map cell."""

    def __init__(
        self,
        source_panel: MapPanel,
        title: str,
        extrapolated_mask: np.ndarray | None = None,
        *,
        diverging: bool = False,
        decimals: int = 3,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WA_DeleteOnClose, True)
        self.setWindowTitle(f"{title} — Slice Plot")
        self.resize(1220, 690)
        self.setMinimumSize(900, 560)
        self.source_panel = source_panel
        self.extrapolated_mask = (
            None if extrapolated_mask is None else np.asarray(extrapolated_mask, dtype=bool)
        )
        self.diverging = diverging
        self.decimals = decimals
        # Validate padded coordinates up front so the caller can show a clear
        # error instead of opening an empty plot for an ambiguous surface.
        collapse_duplicate_map(self.source_panel.table.current_map())

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)
        header = QFrame()
        header.setObjectName("MapHeader")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(16, 10, 16, 10)
        heading = QLabel(f"{title} cross-sections")
        heading.setObjectName("SectionTitle")
        header_layout.addWidget(heading)
        header_layout.addStretch(1)
        self.selection_label = QLabel()
        self.selection_label.setObjectName("Badge")
        header_layout.addWidget(self.selection_label)
        layout.addWidget(header)

        splitter = QSplitter(Qt.Horizontal)
        self.x_panel = CurvePanel("X slice", "Z values across X at the currently selected Y row.")
        self.y_panel = CurvePanel(
            "Y slice", "Z values across Y at the currently selected X column."
        )
        splitter.addWidget(self.x_panel)
        splitter.addWidget(self.y_panel)
        splitter.setSizes([610, 610])
        layout.addWidget(splitter, 1)

        table = self.source_panel.table
        table.itemSelectionChanged.connect(self.update_slices)
        table.dataEdited.connect(self.update_slices)
        self.update_slices()

    def update_slices(self) -> None:
        try:
            original_map = self.source_panel.table.current_map()
            collapsed = collapse_duplicate_map(original_map)
        except MapValidationError:
            return
        original_row = self.source_panel.table.currentRow()
        original_column = self.source_panel.table.currentColumn()
        if original_row < 0:
            original_row = original_map.rows // 2
        if original_column < 0:
            original_column = original_map.columns // 2
        original_row = min(max(original_row, 0), original_map.rows - 1)
        original_column = min(max(original_column, 0), original_map.columns - 1)
        row = int(collapsed.y_inverse[original_row])
        column = int(collapsed.x_inverse[original_column])
        map_data = collapsed.map_data

        mask = self.extrapolated_mask
        if mask is not None:
            if mask.shape == original_map.z.shape:
                mask = collapsed.collapse_mask(mask)
            elif mask.shape != map_data.z.shape:
                mask = None
        x_mask = None if mask is None else mask[row, :]
        y_mask = None if mask is None else mask[:, column]
        x_curve = CurveData(
            map_data.x,
            map_data.z[row, :],
            name=f"X slice at Y={format_number(map_data.y[row], 8)}",
        )
        y_curve = CurveData(
            map_data.y,
            map_data.z[:, column],
            name=f"Y slice at X={format_number(map_data.x[column], 8)}",
        )
        self.x_panel.title_label.setText(x_curve.name)
        self.y_panel.title_label.setText(y_curve.name)
        self.x_panel.set_curve(
            x_curve,
            x_mask,
            diverging=self.diverging,
            decimals=self.decimals,
        )
        self.y_panel.set_curve(
            y_curve,
            y_mask,
            diverging=self.diverging,
            decimals=self.decimals,
        )
        x_outside = int(np.count_nonzero(x_mask)) if x_mask is not None else 0
        y_outside = int(np.count_nonzero(y_mask)) if y_mask is not None else 0
        self.x_panel.set_badges(
            [(f"{x_curve.size} points", False), (f"{x_outside} extrapolated", x_outside > 0)]
        )
        self.y_panel.set_badges(
            [(f"{y_curve.size} points", False), (f"{y_outside} extrapolated", y_outside > 0)]
        )
        self.selection_label.setText(
            f"X {format_number(original_map.x[original_column], 7)}  •  "
            f"Y {format_number(original_map.y[original_row], 7)}  •  "
            f"Z {format_number(original_map.z[original_row, original_column], 7)}"
        )


class Map3DDialog(QDialog):
    """Interactive Matplotlib 3D surface viewer for a map snapshot."""

    def __init__(
        self,
        map_data: MapData,
        title: str,
        extrapolated_mask: np.ndarray | None = None,
        *,
        diverging: bool = False,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WA_DeleteOnClose, True)
        self.setWindowTitle(f"{title} — 3D Surface")
        self.resize(1100, 760)
        self.setMinimumSize(820, 600)
        collapsed = collapse_duplicate_map(map_data)
        self.map_data = collapsed.map_data
        if extrapolated_mask is None:
            self.mask = None
        else:
            supplied_mask = np.asarray(extrapolated_mask, dtype=bool)
            self.mask = (
                collapsed.collapse_mask(supplied_mask)
                if supplied_mask.shape == map_data.z.shape
                else supplied_mask
            )
        self.diverging = diverging
        self._elevation = 28
        self._azimuth = -135

        from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg, NavigationToolbar2QT
        from matplotlib.figure import Figure

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        controls = QHBoxLayout()
        title_label = QLabel(title)
        title_label.setObjectName("SectionTitle")
        controls.addWidget(title_label)
        controls.addStretch(1)
        instructions = QLabel("Drag to rotate  •  Scroll to zoom")
        instructions.setObjectName("Muted")
        controls.addWidget(instructions)
        for label, elevation, azimuth in (
            ("Isometric", 28, -135),
            ("Top", 90, -90),
            ("X side", 0, -90),
            ("Y side", 0, 0),
        ):
            button = QPushButton(label)
            button.setObjectName("GhostButton")
            button.clicked.connect(
                lambda _checked=False, e=elevation, a=azimuth: self.set_view(e, a)
            )
            controls.addWidget(button)
        self.wireframe = QCheckBox("Grid lines")
        self.wireframe.setChecked(True)
        self.wireframe.stateChanged.connect(self.redraw)
        controls.addWidget(self.wireframe)
        layout.addLayout(controls)

        self.figure = Figure(figsize=(10, 7), facecolor="#0a101b")
        self.canvas = FigureCanvasQTAgg(self.figure)
        self.toolbar = NavigationToolbar2QT(self.canvas, self)
        self.toolbar.setObjectName("Map3DToolbar")
        self._tint_toolbar_icons()
        layout.addWidget(self.toolbar)
        layout.addWidget(self.canvas, 1)
        self.axes = None
        self.redraw()

    def _tint_toolbar_icons(self) -> None:
        """Make Matplotlib's normally black toolbar glyphs readable on the dark UI."""
        for button in self.toolbar.findChildren(QToolButton):
            source_icon = button.icon()
            if source_icon.isNull():
                continue
            sizes = source_icon.availableSizes() or [QSize(24, 24)]
            tinted_icon = QIcon()
            for size in sizes:
                for mode, color in (
                    (QIcon.Normal, QColor("#cbd6e5")),
                    (QIcon.Active, QColor("#f4f7fb")),
                    (QIcon.Disabled, QColor("#5f6b7d")),
                ):
                    source = source_icon.pixmap(size, mode)
                    tinted = QPixmap(source.size())
                    tinted.fill(Qt.transparent)
                    painter = QPainter(tinted)
                    painter.drawPixmap(0, 0, source)
                    painter.setCompositionMode(QPainter.CompositionMode_SourceIn)
                    painter.fillRect(tinted.rect(), color)
                    painter.end()
                    tinted_icon.addPixmap(tinted, mode)
            button.setIcon(tinted_icon)

    def redraw(self) -> None:
        from matplotlib.colors import Normalize

        self.figure.clear()
        axes = self.figure.add_subplot(111, projection="3d")
        self.axes = axes
        x_grid, y_grid = np.meshgrid(self.map_data.x, self.map_data.y)
        minimum, maximum = self.map_data.value_range
        if self.diverging:
            extent = max(abs(minimum), abs(maximum), np.finfo(float).eps)
            normalizer = Normalize(vmin=-extent, vmax=extent)
            cmap = "coolwarm"
        else:
            if maximum <= minimum:
                maximum = minimum + 1.0
            normalizer = Normalize(vmin=minimum, vmax=maximum)
            cmap = "viridis"
        edge_color = "#152033" if self.wireframe.isChecked() else "none"
        surface = axes.plot_surface(
            x_grid,
            y_grid,
            self.map_data.z,
            cmap=cmap,
            norm=normalizer,
            edgecolor=edge_color,
            linewidth=0.45,
            antialiased=True,
            alpha=0.96,
        )
        if self.mask is not None and self.mask.shape == self.map_data.z.shape and np.any(self.mask):
            z_range = max(float(np.ptp(self.map_data.z)), 1.0)
            axes.scatter(
                x_grid[self.mask],
                y_grid[self.mask],
                self.map_data.z[self.mask] + 0.015 * z_range,
                color="#f59e0b",
                edgecolors="#fff0c2",
                linewidths=0.5,
                s=28,
                depthshade=False,
                label="Extrapolated",
            )
            legend = axes.legend(loc="upper right", frameon=True)
            legend.get_frame().set_facecolor("#111827")
            legend.get_frame().set_edgecolor("#34435b")
            for text in legend.get_texts():
                text.set_color("#e8eef8")

        axes.set_xlabel("X axis", color="#cbd6e5", labelpad=10)
        axes.set_ylabel("Y axis", color="#cbd6e5", labelpad=10)
        axes.set_zlabel("Z value", color="#cbd6e5", labelpad=10)
        axes.tick_params(colors="#9aa9bd", labelsize=8)
        axes.set_facecolor("#0a101b")
        for axis in (axes.xaxis, axes.yaxis, axes.zaxis):
            axis.set_pane_color((0.06, 0.09, 0.15, 1.0))
            axis._axinfo["grid"]["color"] = (0.18, 0.24, 0.34, 0.55)
        axes.set_box_aspect((1.55, 1.15, 0.82))
        axes.view_init(elev=self._elevation, azim=self._azimuth)
        colorbar = self.figure.colorbar(surface, ax=axes, shrink=0.68, pad=0.08)
        colorbar.ax.tick_params(colors="#9aa9bd", labelsize=8)
        colorbar.outline.set_edgecolor("#34435b")
        self.figure.subplots_adjust(left=0.02, right=0.91, bottom=0.03, top=0.98)
        self.canvas.draw_idle()

    def set_view(self, elevation: float, azimuth: float) -> None:
        self._elevation = elevation
        self._azimuth = azimuth
        if self.axes is not None:
            self.axes.view_init(elev=elevation, azim=azimuth)
            self.canvas.draw_idle()
