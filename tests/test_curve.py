import unittest

import numpy as np

from ecu_map_tool.clipboard import (
    format_excel_curve,
    format_romraider_curve,
    parse_clipboard,
)
from ecu_map_tool.curve import (
    detect_curve_anomalies,
    repair_curve_selection,
    resample_curve,
    smooth_entire_curve,
)
from ecu_map_tool.model import CurveData, MapValidationError, generate_even_axis


class CurveTests(unittest.TestCase):
    def setUp(self):
        self.curve = CurveData(
            [0.20, 0.45, 0.80, 1.20],
            [1.5, 2.0, 3.2, 4.8],
            name="Injection curve",
        )

    def assert_curve_equal(self, actual: CurveData, expected: CurveData):
        np.testing.assert_allclose(actual.x, expected.x)
        np.testing.assert_allclose(actual.values, expected.values)

    def test_romraider_table2d_round_trip(self):
        text = format_romraider_curve(self.curve, precision=12)
        self.assertTrue(text.startswith("[Table2D]\r\n0.2\t0.45\t0.8\t1.2\r\n"))
        payload = parse_clipboard(text, name="Injection curve")
        self.assertEqual(payload.kind, "curve")
        self.assert_curve_equal(payload.curve_data, self.curve)

    def test_bare_excel_two_row_curve_is_accepted(self):
        payload = parse_clipboard(format_excel_curve(self.curve, precision=12))
        self.assertEqual(payload.kind, "curve")
        self.assert_curve_equal(payload.curve_data, self.curve)

    def test_romraider_curve_selection_mask(self):
        payload = parse_clipboard("[Selection1D]\n1.0\tx\t3.0")
        self.assertEqual(payload.kind, "curve_selection")
        np.testing.assert_allclose(payload.selection, [1.0, np.nan, 3.0], equal_nan=True)

    def test_linear_resampling_is_exact_on_uneven_axis(self):
        source = CurveData([0, 1, 3, 8], [5, 7, 11, 21])
        target = generate_even_axis(0, 8, 20, "Target X")
        result = resample_curve(source, target, method="linear")
        np.testing.assert_allclose(result.curve_data.values, 2 * target + 5)
        self.assertEqual(result.extrapolated_points, 0)

    def test_descending_curve_and_target_are_supported(self):
        source = CurveData([8, 3, 1, 0], [21, 11, 7, 5])
        target = [7, 4, 2, 0.5]
        result = resample_curve(source, target)
        np.testing.assert_allclose(result.curve_data.values, 2 * np.asarray(target) + 5)

    def test_hold_and_limited_linear_extrapolation(self):
        source = CurveData([0, 1, 2], [0, 10, 20])
        held = resample_curve(source, [-5, 0, 2, 7], extrapolation="hold")
        np.testing.assert_allclose(held.curve_data.values, [0, 0, 20, 20])
        limited = resample_curve(
            source,
            [-5, 0, 2, 7],
            extrapolation="linear",
            maximum_edge_intervals=1,
        )
        np.testing.assert_allclose(limited.curve_data.values, [-10, 0, 20, 30])

    def test_disallow_curve_extrapolation(self):
        with self.assertRaises(MapValidationError):
            resample_curve(self.curve, [0.1, 0.5], extrapolation="disallow")

    def test_pchip_matches_source_nodes_and_uses_linear_outside(self):
        target = [0.1, 0.2, 0.45, 0.8, 1.2, 1.4]
        result = resample_curve(
            self.curve,
            target,
            method="pchip",
            extrapolation="linear",
            maximum_edge_intervals=1,
        )
        np.testing.assert_allclose(result.curve_data.values[1:5], self.curve.values)
        np.testing.assert_allclose(
            result.curve_data.values[result.extrapolated_mask],
            result.linear_reference.values[result.extrapolated_mask],
        )

    def test_curve_selection_repair_is_axis_aware(self):
        source = CurveData([0, 1, 3, 8, 12], [5, 7, 40, 21, 29])
        mask = np.asarray([False, False, True, False, False])
        repaired = repair_curve_selection(source, mask)
        self.assertAlmostEqual(repaired.values[2], 11.0)
        np.testing.assert_allclose(repaired.values[~mask], source.values[~mask])

    def test_whole_curve_smoothing_preserves_a_line_and_reduces_spike(self):
        line = CurveData([0, 1, 3, 8, 12], [5, 7, 11, 21, 29])
        np.testing.assert_allclose(smooth_entire_curve(line).values, line.values)
        damaged = CurveData(line.x, [5, 7, 40, 21, 29])
        smoothed = smooth_entire_curve(damaged)
        self.assertLess(smoothed.values[2], 40)

    def test_curve_anomaly_detection_flags_spike_without_modifying_curve(self):
        curve = CurveData([0, 1, 2, 3, 4], [1, 2, 20, 4, 5])
        before = curve.values.copy()
        result = detect_curve_anomalies(curve)
        self.assertTrue(result.mask[2])
        np.testing.assert_array_equal(curve.values, before)


if __name__ == "__main__":
    unittest.main()
