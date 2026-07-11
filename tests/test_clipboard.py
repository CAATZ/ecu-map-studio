import unittest
from pathlib import Path

import numpy as np

from ecu_map_tool.clipboard import (
    ClipboardFormatError,
    format_excel_table,
    format_romraider_table,
    parse_clipboard,
)
from ecu_map_tool.model import MapData, MapValidationError, collapse_duplicate_map


class ClipboardTests(unittest.TestCase):
    def setUp(self):
        self.map_data = MapData(
            x=np.asarray([800.0, 2000.0, 4500.0]),
            y=np.asarray([0.25, 0.75, 1.25]),
            z=np.asarray(
                [
                    [32.0, 36.5, 31.0],
                    [25.0, 29.5, 27.0],
                    [16.0, 20.0, 18.5],
                ]
            ),
            name="Test map",
        )

    def assert_map_equal(self, actual: MapData, expected: MapData):
        np.testing.assert_allclose(actual.x, expected.x)
        np.testing.assert_allclose(actual.y, expected.y)
        np.testing.assert_allclose(actual.z, expected.z)

    def test_romraider_full_table_round_trip(self):
        text = format_romraider_table(self.map_data, precision=12)
        self.assertTrue(text.startswith("[Table3D]\r\n800\t2000\t4500"))
        payload = parse_clipboard(text)
        self.assertEqual(payload.kind, "table")
        self.assert_map_equal(payload.map_data, self.map_data)

    def test_airboy_header_on_same_line(self):
        text = (
            "[Table3D]\t800\t2000\t4500\r\n"
            "0.25\t32\t36.5\t31\r\n"
            "0.75\t25\t29.5\t27\r\n"
            "1.25\t16\t20\t18.5"
        )
        self.assert_map_equal(parse_clipboard(text).map_data, self.map_data)

    def test_excel_table_round_trip(self):
        text = format_excel_table(self.map_data, precision=12)
        payload = parse_clipboard(text)
        self.assert_map_equal(payload.map_data, self.map_data)

    def test_excel_label_in_top_left_is_accepted(self):
        text = (
            "Load / RPM\t800\t2000\t4500\n"
            "0.25\t32\t36.5\t31\n"
            "0.75\t25\t29.5\t27\n"
            "1.25\t16\t20\t18.5"
        )
        self.assert_map_equal(parse_clipboard(text).map_data, self.map_data)

    def test_romraider_selection_preserves_x_mask(self):
        payload = parse_clipboard("[Selection3D]\n1\tx\t3\n4\t5\tx")
        self.assertEqual(payload.kind, "selection")
        np.testing.assert_allclose(
            payload.selection,
            np.asarray([[1.0, np.nan, 3.0], [4.0, 5.0, np.nan]]),
            equal_nan=True,
        )

    def test_single_cell_selection_is_accepted(self):
        payload = parse_clipboard("[Selection3D]\n12.5")
        np.testing.assert_allclose(payload.selection, [[12.5]])

    def test_duplicate_axis_is_rejected(self):
        text = "[Table3D]\n800\t800\n0.2\t1\t2\n0.4\t3\t4"
        with self.assertRaises(ClipboardFormatError):
            parse_clipboard(text)

    def test_redundant_padded_axes_are_preserved_and_calculation_view_is_collapsed(self):
        text = "[Table3D]\n10\t20\t20\t20\n100\t1\t2\t2\t2\n200\t3\t4\t4\t4\n200\t3\t4\t4\t4"
        payload = parse_clipboard(text)
        self.assertEqual(payload.map_data.z.shape, (3, 4))
        np.testing.assert_allclose(payload.map_data.x, [10, 20, 20, 20])
        np.testing.assert_allclose(payload.map_data.y, [100, 200, 200])
        self.assertIn("complete table is preserved", payload.notice)

        collapsed = collapse_duplicate_map(payload.map_data)
        self.assertEqual(collapsed.map_data.z.shape, (2, 2))
        self.assertEqual(collapsed.removed_x, 2)
        self.assertEqual(collapsed.removed_y, 1)
        self.assertIn("10\t20\t20\t20", format_romraider_table(payload.map_data))

    def test_repeated_coordinate_with_different_values_is_preserved_for_axis_editing(self):
        text = "[Table3D]\n10\t20\t20\n100\t1\t2\t9\n200\t3\t4\t8"
        payload = parse_clipboard(text)
        self.assertEqual(payload.map_data.z.shape, (2, 3))
        self.assertIn("Assign distinct breakpoints", payload.notice)
        with self.assertRaisesRegex(MapValidationError, "Z columns are different"):
            collapse_duplicate_map(payload.map_data)

    def test_real_romraider_12_by_16_fixture(self):
        fixture = Path(__file__).parent / "fixtures" / "romraider_12x16_table.txt"
        payload = parse_clipboard(fixture.read_text(encoding="utf-8"))
        self.assertEqual(payload.map_data.z.shape, (16, 12))
        self.assertAlmostEqual(payload.map_data.x[0], 25.00984206912337)
        self.assertAlmostEqual(payload.map_data.x[-1], 700.0000457770657)
        self.assertAlmostEqual(payload.map_data.y[-1], 6958.0)
        self.assertAlmostEqual(payload.map_data.z[10, 1], 4.7541)


if __name__ == "__main__":
    unittest.main()
