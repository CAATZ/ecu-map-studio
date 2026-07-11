from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.interpolate import RegularGridInterpolator

from .model import (
    MapData,
    MapValidationError,
    collapse_duplicate_map,
    validate_map_axis,
)


METHOD_LABELS = {
    "bilinear": "Bilinear",
    "pchip": "Shape-preserving PCHIP",
    "nearest": "Nearest neighbor",
}

EXTRAPOLATION_LABELS = {
    "hold": "Hold edge values",
    "linear": "Limited linear",
    "disallow": "Do not extrapolate",
}


@dataclass(frozen=True)
class ResampleResult:
    map_data: MapData
    extrapolated_mask: np.ndarray
    bilinear_reference: MapData
    delta_vs_bilinear: MapData
    method: str
    extrapolation: str

    @property
    def extrapolated_cells(self) -> int:
        return int(np.count_nonzero(self.extrapolated_mask))


def _outside_mask(x: np.ndarray, y: np.ndarray, new_x: np.ndarray, new_y: np.ndarray) -> np.ndarray:
    x_scale = max(1.0, float(np.max(np.abs(x))))
    y_scale = max(1.0, float(np.max(np.abs(y))))
    x_tolerance = np.finfo(float).eps * x_scale * 16.0
    y_tolerance = np.finfo(float).eps * y_scale * 16.0
    outside_x = (new_x < x[0] - x_tolerance) | (new_x > x[-1] + x_tolerance)
    outside_y = (new_y < y[0] - y_tolerance) | (new_y > y[-1] + y_tolerance)
    return outside_y[:, None] | outside_x[None, :]


def _limited_coordinates(
    axis: np.ndarray, target: np.ndarray, maximum_edge_intervals: float
) -> np.ndarray:
    lower = axis[0] - maximum_edge_intervals * (axis[1] - axis[0])
    upper = axis[-1] + maximum_edge_intervals * (axis[-1] - axis[-2])
    return np.clip(target, lower, upper)


def _bilinear_values(
    source: MapData,
    target_x: np.ndarray,
    target_y: np.ndarray,
) -> np.ndarray:
    x, y, z = source.x, source.y, source.z
    x_index = np.searchsorted(x, target_x, side="right") - 1
    y_index = np.searchsorted(y, target_y, side="right") - 1
    x_index = np.clip(x_index, 0, x.size - 2)
    y_index = np.clip(y_index, 0, y.size - 2)

    x0 = x[x_index]
    x1 = x[x_index + 1]
    y0 = y[y_index]
    y1 = y[y_index + 1]
    wx = (target_x - x0) / (x1 - x0)
    wy = (target_y - y0) / (y1 - y0)

    z00 = z[np.ix_(y_index, x_index)]
    z10 = z[np.ix_(y_index, x_index + 1)]
    z01 = z[np.ix_(y_index + 1, x_index)]
    z11 = z[np.ix_(y_index + 1, x_index + 1)]

    wx2 = wx[None, :]
    wy2 = wy[:, None]
    return (
        z00 * (1 - wx2) * (1 - wy2)
        + z10 * wx2 * (1 - wy2)
        + z01 * (1 - wx2) * wy2
        + z11 * wx2 * wy2
    )


def _nearest_values(source: MapData, target_x: np.ndarray, target_y: np.ndarray) -> np.ndarray:
    def nearest_indices(axis: np.ndarray, values: np.ndarray) -> np.ndarray:
        right = np.searchsorted(axis, values, side="left")
        right = np.clip(right, 0, axis.size - 1)
        left = np.clip(right - 1, 0, axis.size - 1)
        choose_left = np.abs(values - axis[left]) <= np.abs(axis[right] - values)
        return np.where(choose_left, left, right)

    xi = nearest_indices(source.x, target_x)
    yi = nearest_indices(source.y, target_y)
    return source.z[np.ix_(yi, xi)]


def _pchip_values(source: MapData, target_x: np.ndarray, target_y: np.ndarray) -> np.ndarray:
    if source.x.size < 4 or source.y.size < 4:
        raise MapValidationError(
            "PCHIP needs at least four source values on both X and Y axes. "
            "Use Bilinear for smaller maps."
        )
    interpolator = RegularGridInterpolator(
        (source.y, source.x),
        source.z,
        method="pchip",
        bounds_error=False,
        fill_value=None,
    )
    yy, xx = np.meshgrid(target_y, target_x, indexing="ij")
    points = np.column_stack((yy.ravel(), xx.ravel()))
    return interpolator(points).reshape(yy.shape)


def _evaluation_axes(
    source: MapData,
    target_x: np.ndarray,
    target_y: np.ndarray,
    extrapolation: str,
    maximum_edge_intervals: float,
) -> tuple[np.ndarray, np.ndarray]:
    if extrapolation == "hold":
        return (
            np.clip(target_x, source.x[0], source.x[-1]),
            np.clip(target_y, source.y[0], source.y[-1]),
        )
    if extrapolation == "linear":
        if maximum_edge_intervals <= 0:
            raise MapValidationError("Maximum extrapolation distance must be greater than zero.")
        return (
            _limited_coordinates(source.x, target_x, maximum_edge_intervals),
            _limited_coordinates(source.y, target_y, maximum_edge_intervals),
        )
    return target_x, target_y


def resample_map(
    source: MapData,
    target_x,
    target_y,
    method: str = "bilinear",
    extrapolation: str = "hold",
    maximum_edge_intervals: float = 1.0,
) -> ResampleResult:
    if method not in METHOD_LABELS:
        raise MapValidationError(f"Unknown interpolation method: {method}.")
    if extrapolation not in EXTRAPOLATION_LABELS:
        raise MapValidationError(f"Unknown extrapolation mode: {extrapolation}.")

    new_x = validate_map_axis(target_x, "Target X")
    new_y = validate_map_axis(target_y, "Target Y")
    ascending_source = collapse_duplicate_map(source).map_data.ascending()
    outside = _outside_mask(ascending_source.x, ascending_source.y, new_x, new_y)

    if extrapolation == "disallow" and np.any(outside):
        count = int(np.count_nonzero(outside))
        raise MapValidationError(
            f"Target axes create {count} cells outside the source range. "
            "Change the axes or choose an extrapolation mode."
        )

    eval_x, eval_y = _evaluation_axes(
        ascending_source, new_x, new_y, extrapolation, maximum_edge_intervals
    )
    bilinear = _bilinear_values(ascending_source, eval_x, eval_y)

    if method == "bilinear":
        values = bilinear
    elif method == "nearest":
        values = _nearest_values(ascending_source, eval_x, eval_y)
    else:
        # PCHIP is used only inside the known domain. Limited extrapolation uses
        # the predictable bilinear edge slope rather than a cubic continuation.
        pchip_x = np.clip(new_x, ascending_source.x[0], ascending_source.x[-1])
        pchip_y = np.clip(new_y, ascending_source.y[0], ascending_source.y[-1])
        values = _pchip_values(ascending_source, pchip_x, pchip_y)
        if extrapolation == "linear" and np.any(outside):
            values[outside] = bilinear[outside]

    result_map = MapData(new_x, new_y, values, name=f"{source.name} — resampled")
    reference_map = MapData(new_x, new_y, bilinear, name="Bilinear reference")
    delta_map = MapData(
        new_x,
        new_y,
        values - bilinear,
        name="Difference vs bilinear",
    )
    return ResampleResult(
        map_data=result_map,
        extrapolated_mask=outside,
        bilinear_reference=reference_map,
        delta_vs_bilinear=delta_map,
        method=method,
        extrapolation=extrapolation,
    )
