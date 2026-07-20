from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .interpolation import resample_map
from .model import CurveData, MapData, MapValidationError


MATH_OPERATIONS = {
    "add": "Add",
    "subtract": "Subtract",
    "multiply": "Multiply",
    "percent": "Adjust by percent",
    "set": "Set value",
    "clamp": "Clamp to range",
}


def _apply_math(
    values: np.ndarray,
    mask: np.ndarray,
    operation: str,
    value: float,
    second_value: float | None = None,
) -> np.ndarray:
    values = np.asarray(values, dtype=float)
    mask = np.asarray(mask, dtype=bool)
    if mask.shape != values.shape:
        raise MapValidationError("The selection does not match the source data.")
    if not np.any(mask):
        raise MapValidationError("Select at least one source value first.")
    if operation not in MATH_OPERATIONS:
        raise MapValidationError(f"Unknown selection operation: {operation}.")
    if not np.isfinite(value):
        raise MapValidationError("The selection-math value must be finite.")

    output = values.copy()
    selected = output[mask]
    if operation == "add":
        selected = selected + value
    elif operation == "subtract":
        selected = selected - value
    elif operation == "multiply":
        selected = selected * value
    elif operation == "percent":
        selected = selected * (1.0 + value / 100.0)
    elif operation == "set":
        selected = np.full_like(selected, value)
    else:
        if second_value is None or not np.isfinite(second_value):
            raise MapValidationError("Clamp requires finite minimum and maximum values.")
        if second_value < value:
            raise MapValidationError("Clamp maximum must be at least the minimum.")
        selected = np.clip(selected, value, second_value)
    if not np.all(np.isfinite(selected)):
        raise MapValidationError("The operation produced a non-finite value.")
    output[mask] = selected
    return output


def apply_map_math(
    source: MapData,
    mask: np.ndarray,
    operation: str,
    value: float,
    second_value: float | None = None,
) -> MapData:
    return MapData(
        source.x,
        source.y,
        _apply_math(source.z, mask, operation, value, second_value),
        name=source.name,
    )


def interpolate_map_selection(source: MapData, mask: np.ndarray) -> MapData:
    """Interpolate a contiguous row, column, or rectangle from its endpoints."""
    selected = np.asarray(mask, dtype=bool)
    if selected.shape != source.z.shape:
        raise MapValidationError("The selection does not match the table.")
    rows = np.flatnonzero(np.any(selected, axis=1))
    columns = np.flatnonzero(np.any(selected, axis=0))
    rectangular = bool(
        rows.size
        and columns.size
        and np.all(np.diff(rows) == 1)
        and np.all(np.diff(columns) == 1)
        and np.all(selected[np.ix_(rows, columns)])
        and int(np.count_nonzero(selected)) == rows.size * columns.size
    )
    if not rectangular or (rows.size < 2 and columns.size < 2):
        raise MapValidationError(
            "Select one contiguous row, column, or rectangle with at least two endpoints."
        )

    x = source.x[columns]
    y = source.y[rows]
    if (columns.size > 1 and x[-1] == x[0]) or (rows.size > 1 and y[-1] == y[0]):
        raise MapValidationError("The selected endpoints must use distinct axis values.")
    tx = np.zeros(columns.size) if columns.size == 1 else (x - x[0]) / (x[-1] - x[0])
    ty = np.zeros(rows.size) if rows.size == 1 else (y - y[0]) / (y[-1] - y[0])
    output = source.z.copy()

    if rows.size == 1:
        first, last = output[rows[0], columns[[0, -1]]]
        output[rows[0], columns] = first + (last - first) * tx
    elif columns.size == 1:
        first, last = output[rows[[0, -1]], columns[0]]
        output[rows, columns[0]] = first + (last - first) * ty
    else:
        top_left, top_right = output[rows[0], columns[[0, -1]]]
        bottom_left, bottom_right = output[rows[-1], columns[[0, -1]]]
        top = top_left + (top_right - top_left) * tx
        bottom = bottom_left + (bottom_right - bottom_left) * tx
        output[np.ix_(rows, columns)] = top + (bottom - top) * ty[:, None]
    return MapData(source.x, source.y, output, name=source.name)


def apply_curve_math(
    source: CurveData,
    mask: np.ndarray,
    operation: str,
    value: float,
    second_value: float | None = None,
) -> CurveData:
    return CurveData(
        source.x,
        _apply_math(source.values, mask, operation, value, second_value),
        name=source.name,
    )


@dataclass(frozen=True)
class SafetyReport:
    changed_cells: int
    extrapolated_cells: int
    maximum_absolute_change: float
    mean_absolute_change: float
    rms_change: float
    source_minimum: float
    source_maximum: float
    result_minimum: float
    result_maximum: float
    below_source_range: int
    above_source_range: int
    sharp_edges: int
    reference_label: str

    def to_text(self) -> str:
        return "\n".join(
            [
                "ECU Map Studio safety report",
                f"Comparison reference: {self.reference_label}",
                f"Changed cells: {self.changed_cells}",
                f"Extrapolated cells: {self.extrapolated_cells}",
                f"Maximum absolute change: {self.maximum_absolute_change:.8g}",
                f"Mean absolute change: {self.mean_absolute_change:.8g}",
                f"RMS change: {self.rms_change:.8g}",
                f"Source range: {self.source_minimum:.8g} to {self.source_maximum:.8g}",
                f"Result range: {self.result_minimum:.8g} to {self.result_maximum:.8g}",
                f"Below source range: {self.below_source_range}",
                f"Above source range: {self.above_source_range}",
                f"Unusually sharp adjacent edges: {self.sharp_edges}",
                "This is a numerical review aid, not an engine-safety determination.",
            ]
        )


def _sharp_edge_count(values: np.ndarray) -> int:
    differences = np.concatenate(
        [np.abs(np.diff(values, axis=0)).ravel(), np.abs(np.diff(values, axis=1)).ravel()]
    )
    positive = differences[differences > np.finfo(float).eps]
    if positive.size < 4:
        return 0
    median = float(np.median(positive))
    mad = float(np.median(np.abs(positive - median)))
    threshold = median + 6.0 * max(mad, np.finfo(float).eps)
    return int(np.count_nonzero(differences > threshold))


def build_safety_report(
    source: MapData,
    result: MapData,
    reference: MapData,
    extrapolated_mask: np.ndarray | None = None,
    reference_label: str = "bilinear result on the target grid",
) -> SafetyReport:
    if result.z.shape != reference.z.shape:
        raise MapValidationError("Safety-report result and reference dimensions do not match.")
    delta = result.z - reference.z
    changed = ~np.isclose(delta, 0.0, atol=1e-12, rtol=1e-10)
    source_minimum, source_maximum = source.value_range
    result_minimum, result_maximum = result.value_range
    tolerance = max(1.0, abs(source_minimum), abs(source_maximum)) * 1e-12
    outside = (
        np.zeros_like(result.z, dtype=bool)
        if extrapolated_mask is None
        else np.asarray(extrapolated_mask, dtype=bool)
    )
    if outside.shape != result.z.shape:
        raise MapValidationError("Safety-report extrapolation mask dimensions do not match.")
    return SafetyReport(
        changed_cells=int(np.count_nonzero(changed)),
        extrapolated_cells=int(np.count_nonzero(outside)),
        maximum_absolute_change=float(np.max(np.abs(delta))),
        mean_absolute_change=float(np.mean(np.abs(delta))),
        rms_change=float(np.sqrt(np.mean(np.square(delta)))),
        source_minimum=source_minimum,
        source_maximum=source_maximum,
        result_minimum=result_minimum,
        result_maximum=result_maximum,
        below_source_range=int(np.count_nonzero(result.z < source_minimum - tolerance)),
        above_source_range=int(np.count_nonzero(result.z > source_maximum + tolerance)),
        sharp_edges=_sharp_edge_count(result.z),
        reference_label=reference_label,
    )


@dataclass(frozen=True)
class MapComparison:
    base: MapData
    candidate: MapData
    delta: MapData
    percent_delta: np.ndarray
    resampled: bool
    extrapolated_mask: np.ndarray


def compare_maps(base: MapData, candidate: MapData) -> MapComparison:
    same_axes = (
        base.x.shape == candidate.x.shape
        and base.y.shape == candidate.y.shape
        and np.allclose(base.x, candidate.x, atol=1e-12, rtol=1e-10)
        and np.allclose(base.y, candidate.y, atol=1e-12, rtol=1e-10)
    )
    if same_axes:
        aligned = MapData(base.x, base.y, candidate.z, name=candidate.name)
        mask = np.zeros_like(base.z, dtype=bool)
    else:
        resampled = resample_map(
            candidate,
            base.x,
            base.y,
            method="bilinear",
            extrapolation="hold",
        )
        aligned = MapData(base.x, base.y, resampled.map_data.z, name=candidate.name)
        mask = resampled.extrapolated_mask
    delta_values = aligned.z - base.z
    percent = np.zeros_like(delta_values)
    np.divide(
        100.0 * delta_values,
        np.abs(base.z),
        out=percent,
        where=np.abs(base.z) > np.finfo(float).eps,
    )
    return MapComparison(
        base=base,
        candidate=aligned,
        delta=MapData(base.x, base.y, delta_values, name="Comparison difference"),
        percent_delta=percent,
        resampled=not same_axes,
        extrapolated_mask=mask,
    )


def merge_comparison(comparison: MapComparison, mask: np.ndarray) -> MapData:
    selected = np.asarray(mask, dtype=bool)
    if selected.shape != comparison.base.z.shape or not np.any(selected):
        raise MapValidationError("Select at least one comparison cell to merge.")
    values = comparison.base.z.copy()
    values[selected] = comparison.candidate.z[selected]
    return MapData(
        comparison.base.x,
        comparison.base.y,
        values,
        name=comparison.base.name,
    )
