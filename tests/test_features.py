import tempfile
import unittest
from pathlib import Path

import numpy as np

from ecu_map_tool.features import (
    apply_curve_math,
    apply_map_math,
    build_safety_report,
    compare_maps,
    interpolate_map_selection,
    merge_comparison,
)
from ecu_map_tool.history import UndoHistory
from ecu_map_tool.interpolation import resample_map
from ecu_map_tool.model import CurveData, MapData, MapValidationError
from ecu_map_tool.project import (
    load_project,
    map_from_dict,
    map_result_from_dict,
    map_result_to_dict,
    map_to_dict,
    save_project,
)


def maps_equal(left: MapData, right: MapData) -> bool:
    return (
        np.array_equal(left.x, right.x)
        and np.array_equal(left.y, right.y)
        and np.array_equal(left.z, right.z)
        and left.name == right.name
    )


class FeatureCoreTests(unittest.TestCase):
    def setUp(self):
        self.base = MapData(
            [0, 1, 2],
            [0, 1, 2],
            [[0, 1, 2], [10, 11, 12], [20, 21, 22]],
            name="Base",
        )

    def test_snapshot_history_drops_redo_branch(self):
        history = UndoHistory(maps_equal)
        history.reset(self.base)
        second = MapData(self.base.x, self.base.y, self.base.z + 1, "Second")
        third = MapData(self.base.x, self.base.y, self.base.z + 2, "Third")
        history.record(second)
        history.record(third)
        self.assertTrue(maps_equal(history.undo(), second))
        replacement = MapData(self.base.x, self.base.y, self.base.z - 1, "Replacement")
        history.record(replacement)
        self.assertFalse(history.can_redo)
        self.assertTrue(maps_equal(history.undo(), second))

    def test_selection_math_changes_only_selected_map_cells(self):
        mask = np.zeros_like(self.base.z, dtype=bool)
        mask[0, 1] = True
        mask[2, 2] = True
        adjusted = apply_map_math(self.base, mask, "percent", 10)
        expected = self.base.z.copy()
        expected[mask] *= 1.1
        np.testing.assert_allclose(adjusted.z, expected)
        clamped = apply_map_math(adjusted, mask, "clamp", 2, 20)
        np.testing.assert_allclose(clamped.z[mask], [2, 20])

    def test_curve_selection_math_and_empty_selection_validation(self):
        curve = CurveData([0, 1, 2], [2, 4, 6])
        adjusted = apply_curve_math(curve, [True, False, True], "multiply", 2)
        np.testing.assert_allclose(adjusted.values, [4, 4, 12])
        with self.assertRaises(MapValidationError):
            apply_curve_math(curve, [False, False, False], "add", 1)

    def test_selection_interpolation_uses_real_axis_spacing(self):
        x = np.asarray([0.0, 1.0, 3.0])
        y = np.asarray([0.0, 2.0, 5.0])
        expected = 1.0 + 2.0 * x[None, :] + 3.0 * y[:, None]
        damaged = expected.copy()
        damaged[1, 1] = 999.0
        source = MapData(x, y, damaged)
        repaired = interpolate_map_selection(source, np.ones((3, 3), dtype=bool))
        np.testing.assert_allclose(repaired.z, expected)

        invalid = np.eye(3, dtype=bool)
        with self.assertRaises(MapValidationError):
            interpolate_map_selection(source, invalid)

    def test_project_round_trip_preserves_generated_result(self):
        result = resample_map(self.base, [0, 0.5, 2], [-1, 1, 2], method="bilinear")
        document = {
            "kind": "map",
            "source": map_to_dict(self.base),
            "result": map_result_to_dict(result),
            "settings": {"method": "bilinear"},
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "sample.ecumap"
            save_project(path, document)
            loaded = load_project(path)
        self.assertTrue(maps_equal(map_from_dict(loaded["source"]), self.base))
        restored_result = map_result_from_dict(loaded["result"])
        np.testing.assert_allclose(restored_result.map_data.z, result.map_data.z)
        np.testing.assert_array_equal(restored_result.extrapolated_mask, result.extrapolated_mask)

    def test_comparison_aligns_candidate_and_merges_selection(self):
        candidate = MapData(
            [0, 2],
            [0, 2],
            [[5, 7], [25, 27]],
            name="Candidate",
        )
        comparison = compare_maps(self.base, candidate)
        self.assertTrue(comparison.resampled)
        np.testing.assert_allclose(comparison.candidate.z, self.base.z + 5)
        mask = np.zeros_like(self.base.z, dtype=bool)
        mask[1, 1] = True
        merged = merge_comparison(comparison, mask)
        self.assertEqual(merged.z[1, 1], 16)
        unchanged = ~mask
        np.testing.assert_allclose(merged.z[unchanged], self.base.z[unchanged])

    def test_safety_report_summarizes_change_and_extrapolation(self):
        result = MapData(self.base.x, self.base.y, self.base.z.copy(), "Result")
        result.z[1, 1] += 3
        mask = np.zeros_like(result.z, dtype=bool)
        mask[0, :] = True
        report = build_safety_report(self.base, result, self.base, mask, "source grid")
        self.assertEqual(report.changed_cells, 1)
        self.assertEqual(report.extrapolated_cells, 3)
        self.assertEqual(report.maximum_absolute_change, 3)
        self.assertIn("Changed cells: 1", report.to_text())


if __name__ == "__main__":
    unittest.main()
