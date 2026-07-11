import unittest

import numpy as np

from ecu_map_tool.interpolation import resample_map
from ecu_map_tool.model import (
    MapData,
    MapValidationError,
    axis_to_text,
    generate_even_axis,
    parse_axis_text,
)


class InterpolationTests(unittest.TestCase):
    @staticmethod
    def planar_map(descending=False):
        x = np.asarray([0.0, 1.0, 3.0, 7.0])
        y = np.asarray([-2.0, 0.0, 4.0, 9.0])
        yy, xx = np.meshgrid(y, x, indexing="ij")
        z = 2.0 * xx + 3.0 * yy + 5.0
        if descending:
            return MapData(x[::-1], y[::-1], z[::-1, ::-1])
        return MapData(x, y, z)

    def test_bilinear_is_exact_for_planar_surface_on_uneven_grid(self):
        target_x = np.asarray([0.2, 2.0, 5.5])
        target_y = np.asarray([-1.0, 2.0, 8.0])
        result = resample_map(self.planar_map(), target_x, target_y)
        yy, xx = np.meshgrid(target_y, target_x, indexing="ij")
        np.testing.assert_allclose(result.map_data.z, 2 * xx + 3 * yy + 5)
        self.assertEqual(result.extrapolated_cells, 0)

    def test_descending_source_and_target_axes_are_supported(self):
        target_x = np.asarray([6.0, 2.0, 0.5])
        target_y = np.asarray([8.0, 1.0, -1.0])
        result = resample_map(self.planar_map(descending=True), target_x, target_y)
        yy, xx = np.meshgrid(target_y, target_x, indexing="ij")
        np.testing.assert_allclose(result.map_data.z, 2 * xx + 3 * yy + 5)

    def test_hold_edge_uses_boundary_coordinates(self):
        source = MapData([0, 1], [0, 1], [[0, 1], [10, 11]])
        result = resample_map(
            source,
            [-2, 0, 1, 3],
            [-4, 0, 1, 5],
            extrapolation="hold",
        )
        self.assertEqual(result.map_data.z[0, 0], 0)
        self.assertEqual(result.map_data.z[-1, -1], 11)
        self.assertEqual(result.extrapolated_cells, 12)

    def test_linear_extrapolation_is_limited_by_edge_intervals(self):
        source = MapData([0, 1], [0, 1], [[0, 1], [10, 11]])
        result = resample_map(
            source,
            [-100, 0, 1, 100],
            [0, 1],
            extrapolation="linear",
            maximum_edge_intervals=1.0,
        )
        np.testing.assert_allclose(result.map_data.z[0], [-1, 0, 1, 2])

    def test_disallow_extrapolation_reports_error(self):
        with self.assertRaises(MapValidationError):
            resample_map(
                self.planar_map(),
                [-1, 1],
                [-2, 2],
                extrapolation="disallow",
            )

    def test_pchip_matches_original_nodes(self):
        source = self.planar_map()
        result = resample_map(source, source.x, source.y, method="pchip")
        np.testing.assert_allclose(result.map_data.z, source.z, atol=1e-12)
        np.testing.assert_allclose(result.delta_vs_bilinear.z, 0, atol=1e-12)

    def test_pchip_uses_linear_policy_outside_domain(self):
        source = self.planar_map()
        target_x = [-1, 0, 3, 8]
        target_y = [-3, 0, 4, 10]
        result = resample_map(
            source,
            target_x,
            target_y,
            method="pchip",
            extrapolation="linear",
            maximum_edge_intervals=1,
        )
        np.testing.assert_allclose(
            result.map_data.z[result.extrapolated_mask],
            result.bilinear_reference.z[result.extrapolated_mask],
        )

    def test_pchip_rejects_small_source_grids(self):
        source = MapData([0, 1, 2], [0, 1, 2], np.arange(9).reshape(3, 3))
        with self.assertRaises(MapValidationError):
            resample_map(source, [0, 1], [0, 1], method="pchip")

    def test_nearest_neighbor_preserves_discrete_values(self):
        source = MapData([0, 1], [0, 1], [[0, 1], [2, 3]])
        result = resample_map(source, [0.1, 0.9], [0.1, 0.9], method="nearest")
        np.testing.assert_allclose(result.map_data.z, [[0, 1], [2, 3]])

    def test_redundant_romraider_padding_is_ignored_only_during_calculation(self):
        source = MapData(
            x=np.asarray([0.0, 1.0, 1.0, 1.0]),
            y=np.asarray([0.0, 1.0, 1.0]),
            z=np.asarray(
                [
                    [0.0, 2.0, 2.0, 2.0],
                    [3.0, 5.0, 5.0, 5.0],
                    [3.0, 5.0, 5.0, 5.0],
                ]
            ),
        )
        result = resample_map(
            source,
            [0.0, 0.5, 1.0],
            [0.0, 0.5, 1.0],
            method="bilinear",
        )
        expected_y, expected_x = np.meshgrid([0.0, 0.5, 1.0], [0.0, 0.5, 1.0], indexing="ij")
        np.testing.assert_allclose(result.map_data.z, 2.0 * expected_x + 3.0 * expected_y)
        self.assertEqual(source.z.shape, (3, 4))

    def test_long_axis_values_round_trip_without_false_extrapolation(self):
        x = np.asarray([25.00984206912337, 75.0083314259556, 700.0000457770657])
        parsed = parse_axis_text(axis_to_text(x), "Target X")
        np.testing.assert_array_equal(parsed, x)

        source = MapData(x, [450.0, 6958.0], [[1, 2, 3], [4, 5, 6]])
        result = resample_map(source, parsed, [450.0, 6958.0])
        self.assertEqual(result.extrapolated_cells, 0)

    def test_automatic_axis_includes_limits_with_constant_spacing(self):
        axis = generate_even_axis(-100.0, 800.0, 20, "Target X")
        self.assertEqual(axis.size, 20)
        self.assertEqual(axis[0], -100.0)
        self.assertEqual(axis[-1], 800.0)
        np.testing.assert_allclose(np.diff(axis), 900.0 / 19.0)

        with self.assertRaises(MapValidationError):
            generate_even_axis(100.0, 100.0, 20, "Target X")


if __name__ == "__main__":
    unittest.main()
