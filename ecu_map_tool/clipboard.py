from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .model import (
    CurveData,
    MapData,
    MapValidationError,
    collapse_duplicate_map,
    format_number,
)


class ClipboardFormatError(ValueError):
    """Raised when clipboard text is not a supported map representation."""


@dataclass(frozen=True)
class ClipboardPayload:
    kind: str
    map_data: MapData | None = None
    curve_data: CurveData | None = None
    selection: np.ndarray | None = None
    notice: str | None = None


def _number(token: str, context: str) -> float:
    clean = token.strip().replace("\u2212", "-")
    if not clean:
        raise ClipboardFormatError(f"Missing numeric value in {context}.")
    if "," in clean and "." not in clean:
        clean = clean.replace(",", ".")
    try:
        value = float(clean)
    except ValueError as exc:
        raise ClipboardFormatError(f"Invalid number {token!r} in {context}.") from exc
    if not np.isfinite(value):
        raise ClipboardFormatError(f"Non-finite value {token!r} in {context}.")
    return value


def _lines(text: str) -> list[str]:
    clean = text.replace("\ufeff", "").replace("\r\n", "\n").replace("\r", "\n")
    rows = clean.split("\n")
    while rows and not rows[-1].strip():
        rows.pop()
    while rows and not rows[0].strip():
        rows.pop(0)
    return rows


def _extract_marker(rows: list[str]) -> tuple[str | None, list[str]]:
    if not rows:
        return None, rows
    first = rows[0].lstrip()
    for marker, kind in (
        ("[Table3D]", "table"),
        ("[Selection3D]", "selection"),
        ("[Table2D]", "curve"),
        ("[Selection1D]", "curve_selection"),
    ):
        if first.lower().startswith(marker.lower()):
            tail = first[len(marker) :]
            remaining = rows[1:]
            if tail:
                # Airboy format places a tab between the marker and the X row.
                tail = tail[1:] if tail.startswith("\t") else tail.lstrip()
                if tail.strip():
                    remaining.insert(0, tail)
            return kind, remaining
    return None, rows


def _tab_rows(rows: list[str]) -> list[list[str]]:
    if not rows:
        raise ClipboardFormatError("Clipboard is empty.")
    if not any("\t" in row for row in rows):
        raise ClipboardFormatError(
            "Expected a tab-separated table. Copy the full table from RomRaider or Excel."
        )
    return [row.split("\t") for row in rows if row.strip()]


def _parse_selection(rows: list[str]) -> ClipboardPayload:
    if not rows:
        raise ClipboardFormatError("RomRaider selection is empty.")
    grid = [row.split("\t") for row in rows if row.strip()]
    width = len(grid[0])
    if width == 0 or any(len(row) != width for row in grid):
        raise ClipboardFormatError("RomRaider selection rows have inconsistent widths.")

    values = np.empty((len(grid), width), dtype=float)
    for row_index, row in enumerate(grid):
        for column_index, token in enumerate(row):
            if token.strip().lower() == "x":
                values[row_index, column_index] = np.nan
            else:
                values[row_index, column_index] = _number(
                    token, f"selection row {row_index + 1}, column {column_index + 1}"
                )
    return ClipboardPayload(kind="selection", selection=values)


def _parse_curve_selection(rows: list[str]) -> ClipboardPayload:
    if not rows:
        raise ClipboardFormatError("RomRaider curve selection is empty.")
    tokens: list[str] = []
    for row in rows:
        tokens.extend(row.split("\t"))
    values = np.empty(len(tokens), dtype=float)
    for index, token in enumerate(tokens):
        if token.strip().lower() == "x":
            values[index] = np.nan
        else:
            values[index] = _number(token, f"curve selection value {index + 1}")
    return ClipboardPayload(kind="curve_selection", selection=values)


def _parse_full_table(rows: list[str], name: str) -> ClipboardPayload:
    grid = _tab_rows(rows)
    if len(grid) < 3:
        raise ClipboardFormatError("A 3D table needs an X row and at least two Y rows.")

    header = grid[0]
    data_rows = grid[1:]

    # Native RomRaider: X-only header, then each data row is Y + Z values.
    native_shape = all(len(row) == len(header) + 1 for row in data_rows)

    # Excel convention: blank/label top-left cell followed by X values.
    excel_shape = (
        len(header) >= 3
        and all(len(row) == len(header) for row in data_rows)
        and (not header[0].strip() or _is_not_number(header[0]))
    )

    if native_shape:
        x_tokens = header
    elif excel_shape:
        x_tokens = header[1:]
    else:
        widths = ", ".join(str(len(row)) for row in grid[:4])
        raise ClipboardFormatError(
            f"Table dimensions do not match RomRaider or Excel layout (first row widths: {widths})."
        )

    x = [_number(token, "X axis") for token in x_tokens]
    y: list[float] = []
    z_rows: list[list[float]] = []
    expected = len(x) + 1
    for row_index, row in enumerate(data_rows):
        if len(row) != expected:
            raise ClipboardFormatError(
                f"Data row {row_index + 1} has {len(row)} cells; expected {expected}."
            )
        y.append(_number(row[0], f"Y axis row {row_index + 1}"))
        z_rows.append(
            [
                _number(token, f"Z row {row_index + 1}, column {column_index + 1}")
                for column_index, token in enumerate(row[1:])
            ]
        )

    try:
        map_data = MapData(x=np.asarray(x), y=np.asarray(y), z=np.asarray(z_rows), name=name)
    except MapValidationError as exc:
        raise ClipboardFormatError(str(exc)) from exc
    notice = None
    removed_x = int(map_data.columns - np.unique(map_data.x).size)
    removed_y = int(map_data.rows - np.unique(map_data.y).size)
    if removed_x or removed_y:
        prefix = (
            f"RomRaider supplied a {map_data.columns} × {map_data.rows} table with "
            f"{removed_x} repeated X bin(s) and {removed_y} repeated Y bin(s). The "
            "complete table is preserved for editing and exact copy-back. "
        )
        try:
            collapsed = collapse_duplicate_map(map_data)
        except MapValidationError as exc:
            notice = (
                prefix + "Some bins sharing a coordinate already contain different Z values. "
                "Assign distinct breakpoints with Edit source axes before interpolating, "
                f"smoothing, or visualizing the surface. Details: {exc}"
            )
        else:
            notice = (
                prefix + "Until those breakpoints are made distinct, interpolation uses the "
                f"equivalent {collapsed.map_data.columns} × {collapsed.map_data.rows} "
                "unique-coordinate surface. No values were averaged or discarded."
            )
    return ClipboardPayload(kind="table", map_data=map_data, notice=notice)


def _parse_curve(rows: list[str], name: str) -> ClipboardPayload:
    grid = _tab_rows(rows)
    if len(grid) != 2:
        raise ClipboardFormatError(
            "A RomRaider 2D curve needs exactly two rows: X axis, then values."
        )
    if len(grid[0]) < 2 or len(grid[0]) != len(grid[1]):
        raise ClipboardFormatError("The 2D curve axis and value rows must have the same length.")
    x = [_number(token, "curve X axis") for token in grid[0]]
    values = [_number(token, "curve values") for token in grid[1]]
    try:
        curve = CurveData(np.asarray(x), np.asarray(values), name=name)
    except MapValidationError as exc:
        raise ClipboardFormatError(str(exc)) from exc
    return ClipboardPayload(kind="curve", curve_data=curve)


def _is_not_number(token: str) -> bool:
    try:
        _number(token, "header")
    except ClipboardFormatError:
        return True
    return False


def parse_clipboard(text: str, name: str = "Clipboard map") -> ClipboardPayload:
    rows = _lines(text)
    marker, rows = _extract_marker(rows)
    if marker == "selection":
        return _parse_selection(rows)
    if marker == "curve_selection":
        return _parse_curve_selection(rows)
    if marker == "curve":
        return _parse_curve(rows, name)
    # A bare two-row TSV is naturally interpreted as axis + curve values.
    if marker is None and len(rows) == 2:
        return _parse_curve(rows, name)
    return _parse_full_table(rows, name)


def format_romraider_table(map_data: MapData, precision: int = 8) -> str:
    """Create RomRaider's default full 3D-table clipboard representation."""
    lines = ["[Table3D]"]
    lines.append("\t".join(format_number(value, precision) for value in map_data.x))
    for y_value, row in zip(map_data.y, map_data.z):
        values = [format_number(y_value, precision)]
        values.extend(format_number(value, precision) for value in row)
        lines.append("\t".join(values))
    return "\r\n".join(lines)


def format_excel_table(map_data: MapData, precision: int = 8) -> str:
    lines = ["\t" + "\t".join(format_number(value, precision) for value in map_data.x)]
    for y_value, row in zip(map_data.y, map_data.z):
        values = [format_number(y_value, precision)]
        values.extend(format_number(value, precision) for value in row)
        lines.append("\t".join(values))
    return "\r\n".join(lines)


def format_romraider_curve(curve_data: CurveData, precision: int = 8) -> str:
    lines = ["[Table2D]"]
    lines.append("\t".join(format_number(value, precision) for value in curve_data.x))
    lines.append("\t".join(format_number(value, precision) for value in curve_data.values))
    return "\r\n".join(lines)


def format_excel_curve(curve_data: CurveData, precision: int = 8) -> str:
    return "\r\n".join(
        (
            "\t".join(format_number(value, precision) for value in curve_data.x),
            "\t".join(format_number(value, precision) for value in curve_data.values),
        )
    )


def format_romraider_selection(values: np.ndarray, precision: int = 8) -> str:
    array = np.asarray(values, dtype=float)
    if array.ndim != 2:
        raise ClipboardFormatError("Selection must be a two-dimensional grid.")
    lines = ["[Selection3D]"]
    for row in array:
        lines.append(
            "\t".join("x" if np.isnan(value) else format_number(value, precision) for value in row)
        )
    return "\r\n".join(lines)


def format_romraider_curve_selection(values: np.ndarray, precision: int = 8) -> str:
    array = np.asarray(values, dtype=float).reshape(-1)
    return "\r\n".join(
        (
            "[Selection1D]",
            "\t".join(
                "x" if np.isnan(value) else format_number(value, precision) for value in array
            ),
        )
    )
