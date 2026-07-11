import unittest
from pathlib import Path

import numpy as np

from ecu_map_tool.clipboard import parse_clipboard
from ecu_map_tool.model import MapData, MapValidationError
from ecu_map_tool.smoothing import (
    detect_anomalies,
    repair_selected_region,
    smooth_entire_table,
)


class SmoothingTests(unittest.TestCase):
    @staticmethod
    def planar_map() -> MapData:
        x = np.asarray([0.0, 1.0, 3.0, 7.0, 10.0])
        y = np.asarray([0.0, 2.0, 5.0, 9.0, 15.0])
        yy, xx = np.meshgrid(y, x, indexing="ij")
        return MapData(x, y, 2.0 * xx + 3.0 * yy + 5.0)

    def test_selection_repair_reconstructs_planar_surface(self):
        expected = self.planar_map()
        damaged_values = expected.z.copy()
        damaged_values[2, 2] += 25.0
        damaged = MapData(expected.x, expected.y, damaged_values)
        mask = np.zeros_like(damaged.z, dtype=bool)
        mask[2, 2] = True

        repaired = repair_selected_region(damaged, mask)
        np.testing.assert_allclose(repaired.z, expected.z, atol=1e-10)

    def test_selection_repair_changes_only_selected_block(self):
        source = self.planar_map()
        damaged_values = source.z.copy()
        damaged_values[1:3, 2:4] += np.asarray([[7.0, -3.0], [5.0, 9.0]])
        damaged = MapData(source.x, source.y, damaged_values)
        mask = np.zeros_like(damaged.z, dtype=bool)
        mask[1:3, 2:4] = True

        repaired = repair_selected_region(damaged, mask)
        np.testing.assert_allclose(repaired.z[~mask], damaged.z[~mask])
        np.testing.assert_allclose(repaired.z[mask], source.z[mask], atol=1e-9)

    def test_selection_repair_rejects_entire_table(self):
        source = self.planar_map()
        with self.assertRaises(MapValidationError):
            repair_selected_region(source, np.ones_like(source.z, dtype=bool))

    def test_whole_table_smoothing_preserves_a_plane(self):
        source = self.planar_map()
        smoothed = smooth_entire_table(source)
        np.testing.assert_allclose(smoothed.z, source.z, atol=1e-10)

    def test_whole_table_smoothing_preserves_redundant_romraider_padding(self):
        x = np.asarray([0.0, 1.0, 2.0, 2.0, 2.0])
        y = np.asarray([0.0, 1.0, 2.0, 2.0])
        yy, xx = np.meshgrid(y, x, indexing="ij")
        source = MapData(x, y, 2.0 * xx + 3.0 * yy + 5.0)

        smoothed = smooth_entire_table(source)

        self.assertEqual(smoothed.z.shape, source.z.shape)
        np.testing.assert_allclose(smoothed.z, source.z, atol=1e-10)
        np.testing.assert_allclose(smoothed.z[:, -1], smoothed.z[:, -2])
        np.testing.assert_allclose(smoothed.z[-1, :], smoothed.z[-2, :])

    def test_whole_table_smoothing_reduces_isolated_spike(self):
        source = self.planar_map()
        values = source.z.copy()
        values[2, 2] += 25.0
        damaged = MapData(source.x, source.y, values)
        smoothed = smooth_entire_table(damaged)
        self.assertLess(smoothed.z[2, 2], damaged.z[2, 2])
        self.assertGreater(smoothed.z[2, 2], source.z[2, 2])

    def test_anomaly_detection_flags_spike_without_changing_data(self):
        source = self.planar_map()
        values = source.z.copy()
        values[2, 2] += 25.0
        damaged = MapData(source.x, source.y, values)
        result = detect_anomalies(damaged)
        self.assertTrue(result.mask[2, 2])
        self.assertGreater(result.threshold, 0)
        np.testing.assert_array_equal(damaged.z, values)

    def test_real_romraider_fixture_finds_known_interior_outliers(self):
        fixture = Path(__file__).parent / "fixtures" / "romraider_12x16_table.txt"
        source = parse_clipboard(fixture.read_text(encoding="utf-8")).map_data
        result = detect_anomalies(source)
        self.assertGreater(result.count, 0)
        self.assertTrue(result.mask[10, 1])  # 4.7541 at Y=4100, X≈75


if __name__ == "__main__":
    unittest.main()
