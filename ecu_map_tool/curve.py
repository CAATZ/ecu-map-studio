from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.interpolate import PchipInterpolator

from .model import CurveData, MapValidationError, validate_axis


CURVE_METHOD_LABELS = {
    "linear": "Linear",
    "pchip": "Shape-preserving PCHIP",
    "nearest": "Nearest neighbor",
}


@dataclass(frozen=True)
class CurveResampleResult:
    curve_data: CurveData
    extrapolated_mask: np.ndarray
    linear_reference: CurveData
    delta_vs_linear: CurveData
    method: str
    extrapolation: str

    @property
    def extrapolated_points(self) -> int:
        return int(np.count_nonzero(self.extrapolated_mask))


@dataclass(frozen=True)
class CurveAnomalyResult:
    mask: np.ndarray
    predicted: np.ndarray
    residual: np.ndarray
    threshold: float

    @property
    def count(self) -> int:
        return int(np.count_nonzero(self.mask))


def _outside_mask(source_x: np.ndarray, target_x: np.ndarray) -> np.ndarray:
    scale = max(1.0, float(np.max(np.abs(source_x))))
    tolerance = np.finfo(float).eps * scale * 16.0
    return (target_x < source_x[0] - tolerance) | (target_x > source_x[-1] + tolerance)


def _limited_coordinates(
    source_x: np.ndarray, target_x: np.ndarray, maximum_edge_intervals: float
) -> np.ndarray:
    lower = source_x[0] - maximum_edge_intervals * (source_x[1] - source_x[0])
    upper = source_x[-1] + maximum_edge_intervals * (source_x[-1] - source_x[-2])
    return np.clip(target_x, lower, upper)


def _linear_values(source: CurveData, target_x: np.ndarray) -> np.ndarray:
    indexes = np.searchsorted(source.x, target_x, side="right") - 1
    indexes = np.clip(indexes, 0, source.size - 2)
    x0 = source.x[indexes]
    x1 = source.x[indexes + 1]
    weights = (target_x - x0) / (x1 - x0)
    return source.values[indexes] * (1.0 - weights) + source.values[indexes + 1] * weights


def _nearest_values(source: CurveData, target_x: np.ndarray) -> np.ndarray:
    right = np.searchsorted(source.x, target_x, side="left")
    right = np.clip(right, 0, source.size - 1)
    left = np.clip(right - 1, 0, source.size - 1)
    choose_left = np.abs(target_x - source.x[left]) <= np.abs(source.x[right] - target_x)
    return source.values[np.where(choose_left, left, right)]


def resample_curve(
    source: CurveData,
    target_x,
    method: str = "linear",
    extrapolation: str = "hold",
    maximum_edge_intervals: float = 1.0,
) -> CurveResampleResult:
    if method not in CURVE_METHOD_LABELS:
        raise MapValidationError(f"Unknown curve interpolation method: {method}.")
    if extrapolation not in {"hold", "linear", "disallow"}:
        raise MapValidationError(f"Unknown extrapolation mode: {extrapolation}.")

    requested_x = validate_axis(target_x, "Target X")
    ascending_source = source.ascending()
    outside = _outside_mask(ascending_source.x, requested_x)
    if extrapolation == "disallow" and np.any(outside):
        raise MapValidationError(
            f"Target axis creates {int(np.count_nonzero(outside))} points outside the "
            "source range. Change the axis or choose an extrapolation mode."
        )

    if extrapolation == "hold":
        evaluation_x = np.clip(requested_x, ascending_source.x[0], ascending_source.x[-1])
    elif extrapolation == "linear":
        if maximum_edge_intervals <= 0:
            raise MapValidationError("Maximum extrapolation distance must be greater than zero.")
        evaluation_x = _limited_coordinates(ascending_source.x, requested_x, maximum_edge_intervals)
    else:
        evaluation_x = requested_x

    linear = _linear_values(ascending_source, evaluation_x)
    if method == "linear":
        values = linear
    elif method == "nearest":
        values = _nearest_values(ascending_source, evaluation_x)
    else:
        pchip_x = np.clip(requested_x, ascending_source.x[0], ascending_source.x[-1])
        values = np.asarray(
            PchipInterpolator(ascending_source.x, ascending_source.values, extrapolate=False)(
                pchip_x
            ),
            dtype=float,
        )
        if extrapolation == "linear" and np.any(outside):
            values[outside] = linear[outside]

    result = CurveData(requested_x, values, name=f"{source.name} — resampled")
    reference = CurveData(requested_x, linear, name="Linear reference")
    delta = CurveData(requested_x, values - linear, name="Difference vs linear")
    return CurveResampleResult(
        curve_data=result,
        extrapolated_mask=outside,
        linear_reference=reference,
        delta_vs_linear=delta,
        method=method,
        extrapolation=extrapolation,
    )


def _contiguous_segments(mask: np.ndarray) -> list[tuple[int, int]]:
    segments: list[tuple[int, int]] = []
    index = 0
    while index < mask.size:
        if not mask[index]:
            index += 1
            continue
        start = index
        while index + 1 < mask.size and mask[index + 1]:
            index += 1
        segments.append((start, index))
        index += 1
    return segments


def repair_curve_selection(curve: CurveData, selected_mask: np.ndarray) -> CurveData:
    mask = np.asarray(selected_mask, dtype=bool).reshape(-1)
    if mask.size != curve.size:
        raise MapValidationError("The smoothing selection does not match the curve.")
    if not np.any(mask):
        raise MapValidationError("Select at least one curve value to repair.")
    if np.all(mask):
        raise MapValidationError(
            "Selection repair needs unchanged reference points. Use Smooth entire curve instead."
        )

    values = curve.values.copy()
    for start, stop in _contiguous_segments(mask):
        left = start - 1 if start > 0 else None
        right = stop + 1 if stop + 1 < curve.size else None

        if left is not None and right is not None:
            x0, x1 = curve.x[left], curve.x[right]
            y0, y1 = curve.values[left], curve.values[right]
        elif left is None:
            fixed = np.flatnonzero(~mask)
            if fixed.size < 2:
                raise MapValidationError("The edge selection needs two unchanged reference points.")
            first, second = int(fixed[0]), int(fixed[1])
            x0, x1 = curve.x[first], curve.x[second]
            y0, y1 = curve.values[first], curve.values[second]
        else:
            fixed = np.flatnonzero(~mask)
            if fixed.size < 2:
                raise MapValidationError("The edge selection needs two unchanged reference points.")
            first, second = int(fixed[-2]), int(fixed[-1])
            x0, x1 = curve.x[first], curve.x[second]
            y0, y1 = curve.values[first], curve.values[second]

        selected_x = curve.x[start : stop + 1]
        weights = (selected_x - x0) / (x1 - x0)
        values[start : stop + 1] = y0 + weights * (y1 - y0)

    return CurveData(curve.x, values, name=f"{curve.name} — repaired")


def _local_line_value(curve: CurveData, index: int, include_center: bool) -> float:
    start = max(0, index - 1)
    stop = min(curve.size, index + 2)
    indexes = np.arange(start, stop)
    if not include_center:
        indexes = indexes[indexes != index]
    if indexes.size < 2:
        return float(curve.values[index])
    x = curve.x[indexes] - curve.x[index]
    scale = max(float(np.max(np.abs(x))), np.finfo(float).eps)
    design = np.column_stack((np.ones(indexes.size), x / scale))
    coefficients, *_ = np.linalg.lstsq(design, curve.values[indexes], rcond=None)
    return float(coefficients[0])


def smooth_entire_curve(curve: CurveData) -> CurveData:
    values = np.asarray(
        [_local_line_value(curve, index, True) for index in range(curve.size)],
        dtype=float,
    )
    return CurveData(curve.x, values, name=f"{curve.name} — smoothed")


def detect_curve_anomalies(curve: CurveData) -> CurveAnomalyResult:
    predicted = curve.values.copy()
    residual = np.zeros(curve.size, dtype=float)
    if curve.size < 3:
        return CurveAnomalyResult(np.zeros(curve.size, dtype=bool), predicted, residual, 0.0)

    for index in range(1, curve.size - 1):
        predicted[index] = _local_line_value(curve, index, False)
        residual[index] = abs(curve.values[index] - predicted[index])
    interior = residual[1:-1]
    median = float(np.median(interior))
    mad = float(np.median(np.abs(interior - median)))
    robust_sigma = 1.4826 * mad
    value_range = max(float(np.ptp(curve.values)), np.finfo(float).eps)
    threshold = max(median + 6.0 * robust_sigma, 0.05 * value_range)
    mask = residual > threshold
    mask[0] = False
    mask[-1] = False
    return CurveAnomalyResult(mask, predicted, residual, threshold)
