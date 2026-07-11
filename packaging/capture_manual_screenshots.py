from __future__ import annotations

import os
from pathlib import Path
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from PyQt5.QtGui import QFontDatabase
from PyQt5.QtTest import QTest

from ecu_map_tool.app import create_application
from ecu_map_tool.curve_window import CurveWindow
from ecu_map_tool.features import build_safety_report
from ecu_map_tool.main_window import ECUMapMainWindow, SafetyReportDialog, SmoothingPreviewDialog
from ecu_map_tool.model import MapData
from ecu_map_tool.smoothing import smooth_entire_table
from ecu_map_tool.visualization import Map3DDialog, MapSliceDialog


OUTPUT = ROOT / "tmp" / "pdfs" / "screenshots"


def save_widget(widget, filename: str, wait_ms: int = 500) -> None:
    widget.show()
    QTest.qWait(wait_ms)
    destination = OUTPUT / filename
    if not widget.grab().save(str(destination)):
        raise RuntimeError(f"Unable to save {destination}")
    print(destination)


def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    app = create_application([])
    QFontDatabase.addApplicationFont("C:/Windows/Fonts/segoeui.ttf")

    window = ECUMapMainWindow()
    window.resize(1800, 1000)
    window.load_demo_map()
    save_widget(window, "01-main-source.png")

    window.column_count.setValue(20)
    window.row_count.setValue(16)
    window.x_min_edit.setText("500")
    window.x_max_edit.setText("7600")
    window.y_min_edit.setText("0.1")
    window.y_max_edit.setText("1.5")
    window.method_combo.setCurrentIndex(1)
    window.generate_result()
    window.tabs.setCurrentIndex(1)
    save_widget(window, "02-generated-result.png")

    window.result_panel.table.setCurrentCell(7, 9)
    slices = MapSliceDialog(
        window.result_panel,
        "Resampled map",
        window.result.extrapolated_mask,
        decimals=3,
    )
    slices.resize(1220, 690)
    save_widget(slices, "03-slice-plots.png")

    surface = Map3DDialog(
        window.result.map_data,
        "Resampled map",
        window.result.extrapolated_mask,
    )
    surface.resize(1100, 760)
    save_widget(surface, "04-3d-surface.png", wait_ms=1000)

    source = window.source_panel.table.current_map()
    damaged_values = source.z.copy()
    damaged_values[source.rows // 2, source.columns // 2] += 8.0
    damaged = MapData(source.x, source.y, damaged_values, "Example map with spike")
    proposed = smooth_entire_table(damaged)
    smoothing = SmoothingPreviewDialog(
        damaged,
        proposed,
        "WARNING: Smoothing changes calibration values and can alter engine behavior. "
        "Review the proposed map and every difference before applying.",
        3,
    )
    smoothing.resize(1180, 700)
    save_widget(smoothing, "05-smoothing-preview.png")

    report = build_safety_report(
        source,
        window.result.map_data,
        window.result.bilinear_reference,
        window.result.extrapolated_mask,
    )
    report_dialog = SafetyReportDialog(report.to_text())
    report_dialog.resize(650, 520)
    save_widget(report_dialog, "06-safety-report.png")

    curve = CurveWindow()
    curve.resize(1280, 790)
    curve.load_demo_curve()
    curve.point_count.setValue(20)
    curve.x_min_edit.setText("0.05")
    curve.x_max_edit.setText("1.6")
    curve.method_combo.setCurrentIndex(1)
    curve.generate_result()
    curve.tabs.setCurrentIndex(1)
    save_widget(curve, "07-2d-curve.png")

    for widget in (
        curve,
        report_dialog,
        smoothing,
        surface,
        slices,
        window,
    ):
        widget.close()
    app.processEvents()


if __name__ == "__main__":
    main()
