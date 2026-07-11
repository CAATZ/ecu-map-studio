import os
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtWidgets import QApplication, QDialog, QMessageBox

from ecu_map_tool.app import create_application
from ecu_map_tool.clipboard import format_romraider_curve
from ecu_map_tool.curve_window import CurveSmoothingPreviewDialog, CurveWindow
from ecu_map_tool.main_window import ECUMapMainWindow, SmoothingPreviewDialog
from ecu_map_tool.model import CurveData
from ecu_map_tool.visualization import Map3DDialog, MapSliceDialog


class GuiSmokeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or create_application([])
        cls.live_routing_windows = []

    @classmethod
    def tearDownClass(cls):
        for window in reversed(cls.live_routing_windows):
            window.close()
        cls.app.processEvents()

    def test_demo_can_generate_and_copy_romraider_result(self):
        window = ECUMapMainWindow()
        window.load_demo_map()
        window.method_combo.setCurrentIndex(1)
        window.generate_result()
        self.app.processEvents()

        self.assertIsNotNone(window.result)
        self.assertEqual(window.result.map_data.z.shape, (16, 20))
        self.assertTrue(window.tabs.isTabEnabled(1))
        self.assertTrue(window.tabs.isTabEnabled(2))

        window.copy_result_romraider()
        self.assertTrue(QApplication.clipboard().text().startswith("[Table3D]"))
        window.close()

    def test_new_map_session_clears_everything_and_can_be_reused(self):
        window = ECUMapMainWindow()
        window.load_demo_map()
        window.generate_result()
        window.open_slice_plot("source")
        self.app.processEvents()
        self.assertEqual(len(window.visual_windows), 1)

        QApplication.clipboard().setText("clipboard must survive reset")
        self.assertTrue(window.new_session(confirm=False))
        self.app.processEvents()

        self.assertIsNone(window.source_data)
        self.assertIsNone(window.result)
        self.assertEqual(window.source_panel.table.rowCount(), 0)
        self.assertEqual(window.result_panel.table.rowCount(), 0)
        self.assertEqual(window.delta_panel.table.rowCount(), 0)
        self.assertFalse(window.tabs.isTabEnabled(1))
        self.assertFalse(window.tabs.isTabEnabled(2))
        self.assertFalse(window.copy_source_button.isEnabled())
        self.assertFalse(window.generate_button.isEnabled())
        self.assertEqual(window.visual_windows, [])
        self.assertEqual(QApplication.clipboard().text(), "clipboard must survive reset")

        fixture = Path(__file__).parent / "fixtures" / "romraider_12x16_table.txt"
        QApplication.clipboard().setText(fixture.read_text(encoding="utf-8"))
        window.paste_from_clipboard()
        self.app.processEvents()
        self.assertEqual(window.source_panel.table.rowCount(), 16)
        self.assertEqual(window.source_panel.table.columnCount(), 12)
        self.assertTrue(window.clear_session_button.isEnabled())
        window.close()

    def test_new_session_cancel_keeps_loaded_map(self):
        window = ECUMapMainWindow()
        window.load_demo_map()
        with patch.object(QMessageBox, "question", return_value=QMessageBox.Cancel):
            self.assertFalse(window.new_session())
        self.assertIsNotNone(window.source_data)
        self.assertGreater(window.source_panel.table.rowCount(), 0)
        window.close()

    def test_new_curve_session_clears_and_can_be_reused(self):
        window = CurveWindow()
        window.load_demo_curve()
        window.generate_result()

        self.assertTrue(window.new_session(confirm=False))
        self.app.processEvents()
        self.assertIsNone(window.source_data)
        self.assertIsNone(window.result)
        self.assertEqual(window.source_panel.table.columnCount(), 0)
        self.assertFalse(window.tabs.isTabEnabled(1))
        self.assertFalse(window.copy_source_button.isEnabled())
        self.assertFalse(window.generate_button.isEnabled())

        curve = CurveData([0.0, 1.0, 2.0], [10.0, 20.0, 30.0])
        QApplication.clipboard().setText(format_romraider_curve(curve))
        window.paste_from_clipboard()
        self.app.processEvents()
        self.assertEqual(window.source_panel.table.columnCount(), 3)
        self.assertTrue(window.clear_session_button.isEnabled())
        window.close()

    def test_real_romraider_paste_and_recolor_do_not_recurse(self):
        fixture = Path(__file__).parent / "fixtures" / "romraider_12x16_table.txt"
        QApplication.clipboard().setText(fixture.read_text(encoding="utf-8"))

        window = ECUMapMainWindow()
        edit_events = []
        window.source_panel.table.dataEdited.connect(lambda: edit_events.append(True))
        window.paste_from_clipboard()
        self.app.processEvents()

        self.assertEqual(window.source_panel.table.rowCount(), 16)
        self.assertEqual(window.source_panel.table.columnCount(), 12)
        self.assertEqual(edit_events, [])

        window.source_panel.table.item(0, 0).setText("0.95")
        self.app.processEvents()
        self.assertEqual(len(edit_events), 1)
        self.assertAlmostEqual(window.source_panel.table.current_map().z[0, 0], 0.95)

        window.column_count.setValue(20)
        window.row_count.setValue(20)
        window.create_even_axes()
        window.method_combo.setCurrentIndex(1)
        window.generate_result()
        self.app.processEvents()
        self.assertEqual(window.result.map_data.z.shape, (20, 20))
        self.assertEqual(window.result.extrapolated_cells, 0)
        window.close()

    def test_extended_20x20_romraider_table_preserves_padded_bins_and_generates(self):
        unique_x = [25, 70, 109, 175, 239, 309, 370, 414, 459, 545, 609, 695]
        unique_y = [
            450,
            900,
            1100,
            1400,
            1900,
            2400,
            2800,
            3100,
            3400,
            3900,
            4100,
            4600,
            5100,
            5400,
            5900,
            6437,
        ]
        x = unique_x + [unique_x[-1]] * 8
        y = unique_y + [unique_y[-1]] * 4
        rows = ["[Table3D]", "\t".join(str(value) for value in x)]
        for y_value in y:
            z = [0.01 * x_value + 0.001 * y_value for x_value in x]
            rows.append("\t".join([str(y_value)] + [f"{value:.8g}" for value in z]))
        QApplication.clipboard().setText("\n".join(rows))

        window = ECUMapMainWindow()
        with patch.object(QMessageBox, "information", return_value=QMessageBox.Ok) as notice:
            window.paste_from_clipboard()
        self.app.processEvents()

        source = window.source_panel.table.current_map()
        self.assertEqual(source.z.shape, (20, 20))
        self.assertEqual(source.x[-1], source.x[-2])
        self.assertEqual(source.y[-1], source.y[-2])
        notice.assert_called_once()

        window.copy_source_romraider()
        self.assertIn("695\t695\t695", QApplication.clipboard().text())
        window.generate_result()
        self.app.processEvents()
        self.assertEqual(window.result.map_data.z.shape, (20, 20))
        self.assertTrue(np.all(np.diff(window.result.map_data.x) > 0))
        self.assertTrue(np.all(np.diff(window.result.map_data.y) > 0))
        window.close()

    def test_automatic_range_can_expand_source_with_constant_spacing(self):
        window = ECUMapMainWindow()
        window.load_demo_map()
        window.column_count.setValue(20)
        window.row_count.setValue(20)
        window.x_min_edit.setText("500")
        window.x_max_edit.setText("8000")
        window.y_min_edit.setText("0.1")
        window.y_max_edit.setText("1.5")

        x, y = window._selected_target_axes()
        self.assertEqual((x.size, y.size), (20, 20))
        self.assertEqual((x[0], x[-1]), (500.0, 8000.0))
        self.assertEqual((y[0], y[-1]), (0.1, 1.5))
        self.assertTrue((abs(np.diff(x) - np.diff(x)[0]) < 1e-12).all())
        self.assertTrue((abs(np.diff(y) - np.diff(y)[0]) < 1e-12).all())

        window.generate_result()
        self.app.processEvents()
        self.assertEqual(window.result.map_data.z.shape, (20, 20))
        self.assertGreater(window.result.extrapolated_cells, 0)
        window.close()

    def test_custom_axes_mode_is_preserved(self):
        window = ECUMapMainWindow()
        window.load_demo_map()
        window.target_mode_tabs.setCurrentIndex(1)
        window.target_x_edit.setPlainText("800, 2200, 4000, 7000")
        window.target_y_edit.setPlainText("0.2, 0.55, 0.95, 1.35")
        window.generate_result()
        self.app.processEvents()

        self.assertEqual(window.result.map_data.z.shape, (4, 4))
        np.testing.assert_allclose(window.result.map_data.x, [800, 2200, 4000, 7000])
        np.testing.assert_allclose(window.result.map_data.y, [0.2, 0.55, 0.95, 1.35])
        window.close()

    def test_anomaly_detection_selects_candidates_without_changing_values(self):
        fixture = Path(__file__).parent / "fixtures" / "romraider_12x16_table.txt"
        QApplication.clipboard().setText(fixture.read_text(encoding="utf-8"))
        window = ECUMapMainWindow()
        window.paste_from_clipboard()
        before = window.source_panel.table.current_map().z.copy()

        window.detect_source_anomalies()
        self.app.processEvents()
        self.assertGreater(len(window.source_panel.table.selectedIndexes()), 0)
        np.testing.assert_array_equal(window.source_panel.table.current_map().z, before)
        window.close()

    def test_selected_region_repair_preview_apply_and_undo(self):
        window = ECUMapMainWindow()
        window.load_demo_map()
        item = window.source_panel.table.item(3, 3)
        original = window.source_panel.table.current_map().z.copy()
        item.setText("100")
        item.setSelected(True)

        with patch.object(SmoothingPreviewDialog, "exec_", return_value=QDialog.Accepted):
            window.repair_source_selection()
        repaired = window.source_panel.table.current_map().z.copy()
        self.assertNotEqual(repaired[3, 3], 100.0)
        self.assertTrue(window.undo_smoothing_action.isEnabled())

        window.undo_smoothing()
        undone = window.source_panel.table.current_map().z
        expected = original.copy()
        expected[3, 3] = 100.0
        np.testing.assert_allclose(undone, expected)
        window.close()

    def test_whole_table_smoothing_requires_warning_and_supports_undo(self):
        window = ECUMapMainWindow()
        window.load_demo_map()
        original = window.source_panel.table.current_map().z.copy()

        with (
            patch.object(QMessageBox, "warning", return_value=QMessageBox.Yes),
            patch.object(SmoothingPreviewDialog, "exec_", return_value=QDialog.Accepted),
        ):
            window.smooth_source_table()
        smoothed = window.source_panel.table.current_map().z.copy()
        self.assertFalse(np.allclose(smoothed, original))
        self.assertTrue(window.undo_smoothing_action.isEnabled())

        window.undo_smoothing()
        np.testing.assert_allclose(window.source_panel.table.current_map().z, original)
        window.close()

    def test_table2d_curve_window_generates_and_copies_romraider_curve(self):
        source = CurveData([0.1, 0.3, 0.7, 1.2], [1.0, 1.6, 3.0, 5.2])
        window = CurveWindow(source)
        window.point_count.setValue(20)
        window.x_min_edit.setText("0")
        window.x_max_edit.setText("1.5")
        window.method_combo.setCurrentIndex(1)
        window.generate_result()
        self.app.processEvents()

        self.assertEqual(window.result.curve_data.size, 20)
        self.assertGreater(window.result.extrapolated_points, 0)
        self.assertTrue(np.isfinite(window.result.curve_data.values).all())
        window.copy_result()
        self.assertTrue(QApplication.clipboard().text().startswith("[Table2D]"))
        window.close()

    def test_table2d_selection_applies_from_selected_curve_point(self):
        source = CurveData([0, 1, 2, 3], [10, 20, 30, 40])
        window = CurveWindow(source)
        window.source_panel.table.item(0, 1).setSelected(True)
        QApplication.clipboard().setText("[Selection1D]\n99\tx")
        window.paste_from_clipboard()
        values = window.source_panel.table.current_curve().values
        np.testing.assert_allclose(values, [10, 99, 30, 40])
        window.close()

    def test_curve_smoothing_preview_apply_and_undo(self):
        source = CurveData([0, 1, 2, 3, 4], [1, 2, 20, 4, 5])
        window = CurveWindow(source)
        window.source_panel.table.item(0, 2).setSelected(True)
        with patch.object(CurveSmoothingPreviewDialog, "exec_", return_value=QDialog.Accepted):
            window.repair_selection()
        self.assertNotEqual(window.source_panel.table.current_curve().values[2], 20)
        self.assertTrue(window.undo_action.isEnabled())
        window.undo_smoothing()
        np.testing.assert_allclose(window.source_panel.table.current_curve().values, source.values)
        window.close()

    def test_main_window_routes_table2d_clipboard_to_curve_tool(self):
        curve = CurveData([0.1, 0.5, 1.0], [1.2, 2.4, 4.0])
        QApplication.clipboard().setText(format_romraider_curve(curve))
        window = ECUMapMainWindow()
        window.paste_from_clipboard()
        self.app.processEvents()

        self.assertEqual(len(window.curve_windows), 1)
        opened = window.curve_windows[0]
        np.testing.assert_allclose(opened.source_panel.table.current_curve().x, curve.x)
        np.testing.assert_allclose(opened.source_panel.table.current_curve().values, curve.values)
        # Closing the application's last routed top-level window makes some Qt
        # builds enter shutdown state. Keep these alive until tearDownClass so
        # later headless regression cases can safely create widgets.
        self.__class__.live_routing_windows.extend([opened, window])

    def test_live_slice_plot_tracks_selected_map_cell(self):
        window = ECUMapMainWindow()
        window.load_demo_map()
        window.source_panel.table.setCurrentCell(2, 3)
        dialog = MapSliceDialog(window.source_panel, "Source map", decimals=3)
        self.app.processEvents()

        source = window.source_panel.table.current_map()
        np.testing.assert_allclose(dialog.x_panel.table.current_curve().x, source.x)
        np.testing.assert_allclose(dialog.x_panel.table.current_curve().values, source.z[2, :])
        np.testing.assert_allclose(dialog.y_panel.table.current_curve().x, source.y)
        np.testing.assert_allclose(dialog.y_panel.table.current_curve().values, source.z[:, 3])

        window.source_panel.table.setCurrentCell(4, 5)
        self.app.processEvents()
        np.testing.assert_allclose(dialog.x_panel.table.current_curve().values, source.z[4, :])
        np.testing.assert_allclose(dialog.y_panel.table.current_curve().values, source.z[:, 5])
        dialog.close()
        window.close()

    def test_interactive_3d_surface_builds_and_changes_camera(self):
        window = ECUMapMainWindow()
        window.load_demo_map()
        source = window.source_panel.table.current_map()
        mask = np.zeros_like(source.z, dtype=bool)
        mask[:, -1] = True
        dialog = Map3DDialog(source, "Source map", mask)
        self.app.processEvents()

        self.assertIsNotNone(dialog.axes)
        self.assertGreaterEqual(len(dialog.axes.collections), 2)
        self.assertIsNotNone(dialog.axes.get_legend())
        dialog.set_view(90, -90)
        self.assertEqual(dialog.axes.elev, 90)
        self.assertEqual(dialog.axes.azim, -90)
        dialog.close()
        window.close()

    def test_main_visualization_actions_open_slice_and_surface(self):
        window = ECUMapMainWindow()
        window.load_demo_map()
        self.assertTrue(window.source_visualize_button.isEnabled())
        window.open_slice_plot("source")
        window.open_3d_surface("source")
        self.app.processEvents()
        self.assertEqual(len(window.visual_windows), 2)
        self.__class__.live_routing_windows.extend([window] + window.visual_windows)


if __name__ == "__main__":
    unittest.main()
