import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtWidgets import QApplication, QDialog, QDialogButtonBox
from PyQt5.QtCore import Qt
from PyQt5.QtTest import QTest
from PyQt5.QtWidgets import QLineEdit

from ecu_map_tool.app import create_application
from ecu_map_tool.clipboard import parse_clipboard
from ecu_map_tool.curve_window import CurveSelectionMathDialog, CurveWindow
from ecu_map_tool.curve_widgets import CurveTableWidget
from ecu_map_tool.features import compare_maps, merge_comparison
from ecu_map_tool.main_window import (
    AxisDialog,
    ECUMapMainWindow,
    MapComparisonDialog,
    SafetyReportDialog,
    SelectionMathDialog,
)
from ecu_map_tool.model import CurveData, MapData
from ecu_map_tool.widgets import MapTableWidget


class WorkflowFeatureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or create_application([])

    def test_map_cell_edits_support_full_undo_and_redo(self):
        window = ECUMapMainWindow()
        window.load_demo_map()
        original = window.source_panel.table.current_map().z.copy()
        window.source_panel.table.item(1, 2).setText("99")
        self.app.processEvents()
        self.assertTrue(window.undo_action.isEnabled())
        self.assertEqual(window.source_panel.table.current_map().z[1, 2], 99)
        window.undo_source()
        np.testing.assert_allclose(window.source_panel.table.current_map().z, original)
        self.assertTrue(window.redo_action.isEnabled())
        window.redo_source()
        self.assertEqual(window.source_panel.table.current_map().z[1, 2], 99)
        window.close()

    def test_automatic_range_shows_compact_values_without_losing_exact_limits(self):
        source = MapData(
            [49.998489356832, 700.00004577706],
            [640.0, 6500.0],
            [[1.0, 2.0], [3.0, 4.0]],
            "Precise axes",
        )
        window = ECUMapMainWindow()
        window.set_source_map(source)
        self.assertEqual(window.x_min_edit.text(), "49.9985")
        self.assertEqual(window.x_max_edit.text(), "700")
        target_x, target_y = window._automatic_axes()
        self.assertEqual(target_x[0], source.x[0])
        self.assertEqual(target_x[-1], source.x[-1])
        self.assertEqual(target_y[0], source.y[0])
        self.assertEqual(target_y[-1], source.y[-1])
        window.close()

    def test_map_and_curve_tables_have_zoom_controls_and_unelided_tabs(self):
        window = ECUMapMainWindow()
        window.resize(1420, 900)
        window.load_demo_map()
        window.show()
        self.app.processEvents()
        table = window.source_panel.table
        self.assertEqual(table.zoom_percent, 90)
        self.assertEqual(table.columnWidth(0), 74)
        table.zoom_out()
        self.assertEqual(table.zoom_percent, 80)
        self.assertEqual(window.source_panel.zoom_controls.reset_button.text(), "80%")
        self.assertEqual(window.source_panel.zoom_controls.fit_button.size().width(), 48)
        self.assertEqual(window.source_panel.zoom_controls.fit_button.size().height(), 25)
        table.set_zoom(100)
        self.assertEqual(table.columnWidth(0), 82)
        self.assertEqual(window.tabs.tabBar().elideMode(), Qt.ElideNone)
        self.assertFalse(window.tabs.tabBar().drawBase())
        self.assertEqual(window.tabs.tabBar().focusPolicy(), Qt.NoFocus)
        self.assertEqual(window.tabs.tabText(2), "VS BILINEAR")
        self.assertEqual(window.tabs.tabBar().EXTRA_GLYPH_WIDTH, 18)
        self.assertGreater(window.tabs.tabBar().tabSizeHint(2).width(), 182)
        self.assertEqual(window.compare_button.text(), "Compare")
        self.assertEqual(window.copy_result_button.text(), "Copy RR")
        self.assertEqual(
            [window.method_combo.itemText(index) for index in range(3)],
            ["Bilinear", "PCHIP", "Nearest"],
        )
        self.assertEqual(
            [window.extrapolation_combo.itemText(index) for index in range(5)],
            ["Hold", "Linear", "Local trend (4 × 4)", "Global trend", "Disabled"],
        )
        for button in (
            window.source_visualize_button,
            window.smoothing_button,
            window.math_button,
            window.compare_button,
            window.copy_source_button,
        ):
            self.assertGreaterEqual(button.width(), button.minimumSizeHint().width())

        window.generate_result()
        self.app.processEvents()
        self.assertIn(
            "Interpolate selected region",
            [action.text() for action in window.smoothing_button.menu().actions()],
        )
        self.assertIn(
            "Interpolate selected region",
            [action.text() for action in window.result_smoothing_button.menu().actions()],
        )
        for button in (
            window.result_smoothing_button,
            window.result_math_button,
            window.result_compare_button,
            window.result_axes_button,
            window.copy_excel_button,
            window.copy_result_button,
            window.safety_report_button,
            window.result_visualize_button,
        ):
            self.assertGreaterEqual(button.width(), button.minimumSizeHint().width())
        window.close()

        curve = CurveWindow(CurveData([0, 1, 2], [10, 20, 30]))
        self.assertEqual(curve.source_panel.table.zoom_percent, 90)
        self.assertEqual(curve.source_panel.table.columnWidth(0), 90)
        self.assertEqual(curve.tabs.tabBar().elideMode(), Qt.ElideNone)
        self.assertEqual(curve.tabs.tabText(2), "VS LINEAR")
        self.assertEqual(
            [curve.method_combo.itemText(index) for index in range(3)],
            ["Linear", "PCHIP", "Nearest"],
        )
        self.assertEqual(
            [curve.extrapolation_combo.itemText(index) for index in range(3)],
            ["Hold", "Linear", "Disabled"],
        )
        curve.close()

    def test_table_axis_labels_are_coarse_and_fit_stays_inside_viewport(self):
        map_data = MapData(
            np.linspace(25.0098, 900.0, 20),
            np.linspace(450.25, 7200.0, 20),
            np.zeros((20, 20)),
        )
        map_table = MapTableWidget()
        map_table.resize(1050, 700)
        map_table.set_map(map_data)
        map_table.show()
        self.app.processEvents()
        map_table.fit_to_view()
        self.app.processEvents()

        self.assertEqual(map_table.horizontalHeaderItem(0).text(), "25")
        self.assertEqual(map_table.verticalHeaderItem(0).text(), "450")
        self.assertGreaterEqual(
            map_table.rowHeight(0), map_table.verticalHeader().sectionSizeHint(0)
        )
        np.testing.assert_allclose(map_table.current_map().x, map_data.x)
        np.testing.assert_allclose(map_table.current_map().y, map_data.y)
        self.assertLessEqual(map_table.horizontalHeader().length(), map_table.viewport().width())
        self.assertLessEqual(map_table.verticalHeader().length(), map_table.viewport().height())
        fitted_zoom = map_table.zoom_percent
        map_table.set_zoom(fitted_zoom + 1, snap_to_step=False)
        self.app.processEvents()
        self.assertTrue(
            map_table.horizontalHeader().length() > map_table.viewport().width()
            or map_table.verticalHeader().length() > map_table.viewport().height()
        )
        map_table.close()

        curve_data = CurveData(np.linspace(25.0098, 900.0, 20), np.zeros(20))
        curve_table = CurveTableWidget()
        curve_table.resize(1200, 100)
        curve_table.set_curve(curve_data)
        curve_table.show()
        self.app.processEvents()
        curve_table.fit_to_view()
        self.app.processEvents()

        self.assertEqual(curve_table.horizontalHeaderItem(0).text(), "25")
        np.testing.assert_allclose(curve_table.current_curve().x, curve_data.x)
        self.assertLessEqual(
            curve_table.horizontalHeader().length(), curve_table.viewport().width()
        )
        fitted_zoom = curve_table.zoom_percent
        curve_table.set_zoom(fitted_zoom + 1, snap_to_step=False)
        self.app.processEvents()
        self.assertGreater(curve_table.horizontalHeader().length(), curve_table.viewport().width())
        curve_table.close()

    def test_map_selection_math_is_one_undoable_change(self):
        window = ECUMapMainWindow()
        window.load_demo_map()
        original = window.source_panel.table.current_map().z.copy()
        window.source_panel.table.item(0, 0).setSelected(True)
        window.source_panel.table.item(2, 3).setSelected(True)
        window.apply_selection_math("add", 5)
        adjusted = window.source_panel.table.current_map().z
        self.assertAlmostEqual(adjusted[0, 0], original[0, 0] + 5)
        self.assertAlmostEqual(adjusted[2, 3], original[2, 3] + 5)
        window.undo_source()
        np.testing.assert_allclose(window.source_panel.table.current_map().z, original)
        window.close()

    def test_typing_a_value_updates_the_selected_map_cells_once(self):
        table = MapTableWidget()
        table.set_map(
            MapData([0, 1], [0, 1], [[1, 2], [3, 4]]),
            editable=True,
            decimals=3,
        )
        table.set_zoom(50)
        table.setCurrentCell(0, 0)
        table.item(0, 1).setSelected(True)
        table.item(1, 0).setSelected(True)
        edits = []
        table.dataEdited.connect(lambda: edits.append(True))
        table.show()
        table.setFocus()

        QTest.keyClick(table, Qt.Key_1)
        editor = table.findChild(QLineEdit)
        self.assertIsNotNone(editor)
        self.assertIn("padding: 0 2px", editor.styleSheet())
        QTest.keyClicks(editor, "2.5")
        QTest.keyClick(editor, Qt.Key_Return)
        self.app.processEvents()

        np.testing.assert_allclose(table.current_map().z, [[12.5, 12.5], [12.5, 4]])
        self.assertEqual(edits, [True])
        table.close()

    def test_selection_math_apply_buttons_accept_the_dialogs(self):
        for dialog in (SelectionMathDialog(1), CurveSelectionMathDialog(1)):
            buttons = dialog.findChild(QDialogButtonBox)
            buttons.button(QDialogButtonBox.Apply).click()
            self.assertEqual(dialog.result(), QDialog.Accepted)

    def test_axis_and_math_inputs_use_compact_precision(self):
        x = np.asarray([25.00984206912337, 75.0083314259556])
        y = np.asarray([450.123456789, 900.987654321])
        axes = AxisDialog(x, y)
        self.assertEqual(axes.x_edit.toPlainText(), "25.0098, 75.0083")
        self.assertEqual(axes.y_edit.toPlainText(), "450.123, 900.988")

        window = ECUMapMainWindow()
        window.set_source_map(MapData(x, y, np.ones((2, 2))))
        window.use_source_axes()
        self.assertEqual(window.target_x_edit.toPlainText(), "25.0098, 75.0083")
        self.assertEqual(window.target_y_edit.toPlainText(), "450.123, 900.988")

        map_math = SelectionMathDialog(1)
        curve_math = CurveSelectionMathDialog(1)
        self.assertEqual(map_math.value.decimals(), 4)
        self.assertEqual(map_math.second_value.decimals(), 4)
        self.assertEqual(curve_math.value.decimals(), 4)
        self.assertEqual(curve_math.second_value.decimals(), 4)

    def test_selection_interpolation_and_math_edit_source_and_result_independently(self):
        x = np.asarray([0.0, 1.0, 3.0])
        y = np.asarray([0.0, 2.0, 5.0])
        expected = 1.0 + 2.0 * x[None, :] + 3.0 * y[:, None]
        damaged = expected.copy()
        damaged[1, 1] = 999.0
        window = ECUMapMainWindow()
        window.set_source_map(MapData(x, y, damaged))

        source_table = window.source_panel.table
        source_table.selectAll()
        window.interpolate_source_selection()
        np.testing.assert_allclose(source_table.current_map().z, expected)
        window.undo_source()
        self.assertEqual(window.source_panel.table.current_map().z[1, 1], 999.0)
        window.redo_source()

        window.generate_result()
        result_table = window.result_panel.table
        expected_result = (
            1.0 + 2.0 * window.result.map_data.x[None, :] + 3.0 * window.result.map_data.y[:, None]
        )
        result_table.item(1, 1).setText("999")
        self.app.processEvents()
        result_table.selectAll()
        window.interpolate_result_selection()
        np.testing.assert_allclose(window.result.map_data.z, expected_result)
        np.testing.assert_allclose(window.source_panel.table.current_map().z, expected)
        window.undo_result()
        self.assertEqual(window.result.map_data.z[1, 1], 999.0)
        window.redo_result()

        window.result_panel.table.item(1, 1).setSelected(True)
        window.apply_selection_math("add", 5, target="result")
        self.assertEqual(window.result.map_data.z[1, 1], expected_result[1, 1] + 5)
        self.assertEqual(window.source_panel.table.current_map().z[1, 1], expected[1, 1])

        previous_axes = window.result.map_data.x.copy()
        with patch("ecu_map_tool.main_window.AxisDialog") as dialog_class:
            dialog = dialog_class.return_value
            dialog.exec_.return_value = QDialog.Accepted
            dialog.x_values = previous_axes + 0.25
            dialog.y_values = window.result.map_data.y.copy()
            window.edit_result_axes()
        np.testing.assert_allclose(window.result.map_data.x, previous_axes + 0.25)
        self.assertEqual(window.target_mode_tabs.currentIndex(), 1)
        window.undo_result()
        np.testing.assert_allclose(window.result.map_data.x, previous_axes)
        window.close()

    def test_selected_cell_block_copies_and_pastes_at_selected_anchor(self):
        window = ECUMapMainWindow()
        window.load_demo_map()
        table = window.source_panel.table
        original = table.current_map().z.copy()
        for row in (0, 1):
            for column in (0, 1):
                table.item(row, column).setSelected(True)
        self.assertTrue(table.copy_selected_cells())
        self.assertIn("\t", QApplication.clipboard().text())

        table.clearSelection()
        table.setCurrentCell(3, 4)
        self.assertTrue(table.paste_copied_cells())
        pasted = table.current_map().z
        np.testing.assert_allclose(pasted[3:5, 4:6], original[0:2, 0:2])
        window.undo_source()
        np.testing.assert_allclose(window.source_panel.table.current_map().z, original)
        window.close()

    def test_generated_map_is_editable_exported_and_undoable(self):
        window = ECUMapMainWindow()
        window.load_demo_map()
        window.generate_result()
        original = window.result.map_data.z.copy()
        replacement = original[0, 0] + 7.25
        window.result_panel.table.item(0, 0).setText(str(replacement))
        self.app.processEvents()

        self.assertAlmostEqual(window.result.map_data.z[0, 0], replacement)
        self.assertTrue(window.tabs.isTabEnabled(2))
        self.assertAlmostEqual(window.result.delta_vs_bilinear.z[0, 0], 7.25)
        self.assertTrue(window.undo_action.isEnabled())

        window.copy_result_romraider()
        exported = parse_clipboard(QApplication.clipboard().text()).map_data
        self.assertAlmostEqual(exported.z[0, 0], replacement)

        window.undo_active()
        np.testing.assert_allclose(window.result.map_data.z, original)
        window.redo_active()
        self.assertAlmostEqual(window.result.map_data.z[0, 0], replacement)
        window.close()

    def test_map_project_restores_settings_and_generated_result(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "map-session.ecumap"
            first = ECUMapMainWindow()
            first.load_demo_map()
            first.method_combo.setCurrentIndex(1)
            first.extrapolation_combo.setCurrentIndex(
                first.extrapolation_combo.findData("global_trend")
            )
            first.column_count.setValue(11)
            first.row_count.setValue(9)
            first.generate_result()
            replacement = first.result.map_data.z[0, 0] + 4.0
            first.result_panel.table.item(0, 0).setText(str(replacement))
            self.app.processEvents()
            expected = first.result.map_data.z.copy()
            self.assertTrue(first.save_project_file(path=path))
            first.close()

            restored = ECUMapMainWindow()
            self.assertTrue(restored.open_project_file(path=path))
            self.assertEqual(restored.method_combo.currentData(), "pchip")
            self.assertEqual(restored.extrapolation_combo.currentData(), "global_trend")
            self.assertEqual(restored.column_count.value(), 11)
            self.assertEqual(restored.row_count.value(), 9)
            self.assertIsNotNone(restored.result)
            self.assertFalse(restored.result_stale)
            np.testing.assert_allclose(restored.result.map_data.z, expected)
            self.assertTrue(restored.safety_report_button.isEnabled())
            restored.close()

    def test_curve_math_history_and_project_round_trip(self):
        source = CurveData([0, 1, 2, 3], [10, 20, 30, 40], "Test curve")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "curve-session.ecumap"
            first = CurveWindow(source)
            first.source_panel.table.item(0, 1).setSelected(True)
            first.source_panel.table.item(0, 2).setSelected(True)
            first.apply_selection_math("percent", 10)
            np.testing.assert_allclose(
                first.source_panel.table.current_curve().values, [10, 22, 33, 40]
            )
            first.undo_source()
            np.testing.assert_allclose(
                first.source_panel.table.current_curve().values, source.values
            )
            first.redo_source()
            first.point_count.setValue(7)
            first.generate_result()
            self.assertTrue(first.save_project_file(path=path))
            first.close()

            restored = CurveWindow()
            self.assertTrue(restored.open_project_file(path=path))
            np.testing.assert_allclose(
                restored.source_panel.table.current_curve().values, [10, 22, 33, 40]
            )
            self.assertEqual(restored.point_count.value(), 7)
            self.assertIsNotNone(restored.result)
            restored.close()

    def test_comparison_dialog_selects_cells_for_merge(self):
        base = MapData([0, 1], [0, 1], [[1, 2], [3, 4]], "Base")
        candidate = MapData([0, 1], [0, 1], [[2, 4], [6, 8]], "Candidate")
        comparison = compare_maps(base, candidate)
        dialog = MapComparisonDialog(comparison, 3)
        dialog.delta_panel.table.item(0, 1).setSelected(True)
        dialog._accept_selection()
        self.assertEqual(dialog.result(), QDialog.Accepted)
        merged = merge_comparison(comparison, dialog.merge_mask)
        np.testing.assert_allclose(merged.z, [[1, 4], [3, 4]])
        dialog.close()

    def test_generated_map_opens_safety_report(self):
        window = ECUMapMainWindow()
        window.load_demo_map()
        window.generate_result()
        with patch.object(SafetyReportDialog, "exec_", return_value=QDialog.Accepted) as opened:
            window.show_safety_report()
        opened.assert_called_once()
        window.close()


if __name__ == "__main__":
    unittest.main()
