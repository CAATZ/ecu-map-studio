from __future__ import annotations

from dataclasses import dataclass
import warnings

import numpy as np
from scipy.sparse import lil_matrix
from scipy.sparse.linalg import MatrixRankWarning, spsolve

from .model import MapData, MapValidationError, collapse_duplicate_map


@dataclass(frozen=True)
class AnomalyResult:
    mask: np.ndarray
    predicted: np.ndarray
    residual: np.ndarray
    threshold: float

    @property
    def count(self) -> int:
        return int(np.count_nonzero(self.mask))


def _axis_neighbor_weights(axis: np.ndarray, index: int) -> list[tuple[int, float]]:
    """Second-derivative weights that account for unequal axis spacing."""
    size = axis.size
    if index == 0:
        distance = abs(float(axis[1] - axis[0]))
        return [(1, 1.0 / distance**2)]
    if index == size - 1:
        distance = abs(float(axis[-1] - axis[-2]))
        return [(size - 2, 1.0 / distance**2)]

    left_distance = abs(float(axis[index] - axis[index - 1]))
    right_distance = abs(float(axis[index + 1] - axis[index]))
    total = left_distance + right_distance
    return [
        (index - 1, 2.0 / (left_distance * total)),
        (index + 1, 2.0 / (right_distance * total)),
    ]


def repair_selected_region(map_data: MapData, selected_mask: np.ndarray) -> MapData:
    """Reconstruct selected cells as a harmonic surface from fixed surroundings."""
    mask = np.asarray(selected_mask, dtype=bool)
    if mask.shape != map_data.z.shape:
        raise MapValidationError("The smoothing selection does not match the source table.")
    collapsed = collapse_duplicate_map(map_data)
    if collapsed.has_duplicates:
        repaired = repair_selected_region(
            collapsed.map_data,
            collapsed.collapse_mask(mask),
        )
        return MapData(
            map_data.x,
            map_data.y,
            collapsed.expand_values(repaired.z),
            name=f"{map_data.name} — repaired",
        )
    selected_count = int(np.count_nonzero(mask))
    if selected_count == 0:
        raise MapValidationError("Select at least one source cell to repair.")
    if selected_count == mask.size:
        raise MapValidationError(
            "Selection repair needs unchanged surrounding cells. Use Smooth entire table instead."
        )

    selected_coordinates = [tuple(value) for value in np.argwhere(mask)]
    lookup = {coordinate: index for index, coordinate in enumerate(selected_coordinates)}
    matrix = lil_matrix((selected_count, selected_count), dtype=float)
    right_hand_side = np.zeros(selected_count, dtype=float)

    for equation, (row, column) in enumerate(selected_coordinates):
        neighbors: list[tuple[int, int, float]] = []
        for neighbor_column, weight in _axis_neighbor_weights(map_data.x, column):
            neighbors.append((row, neighbor_column, weight))
        for neighbor_row, weight in _axis_neighbor_weights(map_data.y, row):
            neighbors.append((neighbor_row, column, weight))

        total_weight = sum(weight for _, _, weight in neighbors)
        matrix[equation, equation] = total_weight
        for neighbor_row, neighbor_column, weight in neighbors:
            coordinate = (neighbor_row, neighbor_column)
            if mask[coordinate]:
                matrix[equation, lookup[coordinate]] -= weight
            else:
                right_hand_side[equation] += weight * map_data.z[coordinate]

    with warnings.catch_warnings():
        warnings.simplefilter("error", MatrixRankWarning)
        try:
            repaired_values = spsolve(matrix.tocsr(), right_hand_side)
        except (MatrixRankWarning, RuntimeError) as exc:
            raise MapValidationError(
                "The selected region could not be reconstructed from its surroundings."
            ) from exc

    if not np.all(np.isfinite(repaired_values)):
        raise MapValidationError(
            "The selected region needs more unchanged surrounding reference cells."
        )

    repaired = map_data.z.copy()
    for coordinate, value in zip(selected_coordinates, repaired_values):
        repaired[coordinate] = value
    return MapData(map_data.x, map_data.y, repaired, name=f"{map_data.name} — repaired")


def _local_plane_value(
    map_data: MapData,
    row: int,
    column: int,
    *,
    include_center: bool,
) -> float:
    row_start = max(0, row - 1)
    row_stop = min(map_data.rows, row + 2)
    column_start = max(0, column - 1)
    column_stop = min(map_data.columns, column + 2)

    points: list[tuple[float, float, float]] = []
    for neighbor_row in range(row_start, row_stop):
        for neighbor_column in range(column_start, column_stop):
            if not include_center and neighbor_row == row and neighbor_column == column:
                continue
            points.append(
                (
                    float(map_data.x[neighbor_column] - map_data.x[column]),
                    float(map_data.y[neighbor_row] - map_data.y[row]),
                    float(map_data.z[neighbor_row, neighbor_column]),
                )
            )

    if len(points) < 3:
        return float(map_data.z[row, column])

    coordinates = np.asarray([(x, y) for x, y, _ in points], dtype=float)
    values = np.asarray([value for _, _, value in points], dtype=float)
    x_scale = max(float(np.max(np.abs(coordinates[:, 0]))), np.finfo(float).eps)
    y_scale = max(float(np.max(np.abs(coordinates[:, 1]))), np.finfo(float).eps)
    normalized_x = coordinates[:, 0] / x_scale
    normalized_y = coordinates[:, 1] / y_scale
    design = np.column_stack((np.ones(len(points)), normalized_x, normalized_y))
    distance_squared = normalized_x**2 + normalized_y**2
    weights = 1.0 / (1.0 + distance_squared)
    root_weights = np.sqrt(weights)
    coefficients, *_ = np.linalg.lstsq(
        design * root_weights[:, None], values * root_weights, rcond=None
    )
    return float(coefficients[0])


def smooth_entire_table(map_data: MapData) -> MapData:
    """Apply one deterministic axis-aware local-plane pass to every cell."""
    collapsed = collapse_duplicate_map(map_data)
    if collapsed.has_duplicates:
        smoothed = smooth_entire_table(collapsed.map_data)
        return MapData(
            map_data.x,
            map_data.y,
            collapsed.expand_values(smoothed.z),
            name=f"{map_data.name} — smoothed",
        )
    smoothed = np.empty_like(map_data.z, dtype=float)
    for row in range(map_data.rows):
        for column in range(map_data.columns):
            smoothed[row, column] = _local_plane_value(map_data, row, column, include_center=True)
    return MapData(map_data.x, map_data.y, smoothed, name=f"{map_data.name} — smoothed")


def detect_anomalies(map_data: MapData) -> AnomalyResult:
    """Flag statistically strong interior deviations from the local surface trend."""
    collapsed = collapse_duplicate_map(map_data)
    if collapsed.has_duplicates:
        result = detect_anomalies(collapsed.map_data)
        return AnomalyResult(
            mask=collapsed.expand_values(result.mask).astype(bool),
            predicted=collapsed.expand_values(result.predicted),
            residual=collapsed.expand_values(result.residual),
            threshold=result.threshold,
        )
    predicted = map_data.z.copy()
    residual = np.zeros_like(map_data.z, dtype=float)

    if map_data.rows < 3 or map_data.columns < 3:
        return AnomalyResult(
            mask=np.zeros_like(map_data.z, dtype=bool),
            predicted=predicted,
            residual=residual,
            threshold=0.0,
        )

    interior_values: list[float] = []
    for row in range(1, map_data.rows - 1):
        for column in range(1, map_data.columns - 1):
            predicted[row, column] = _local_plane_value(map_data, row, column, include_center=False)
            residual[row, column] = abs(map_data.z[row, column] - predicted[row, column])
            interior_values.append(float(residual[row, column]))

    residual_values = np.asarray(interior_values, dtype=float)
    median = float(np.median(residual_values))
    mad = float(np.median(np.abs(residual_values - median)))
    robust_sigma = 1.4826 * mad
    value_range = max(float(np.ptp(map_data.z)), np.finfo(float).eps)
    # A conservative robust threshold avoids asking the user to choose a
    # sensitivity. Detection only selects candidates; it never changes data.
    threshold = max(median + 6.0 * robust_sigma, 0.05 * value_range)
    mask = residual > threshold
    mask[0, :] = False
    mask[-1, :] = False
    mask[:, 0] = False
    mask[:, -1] = False
    return AnomalyResult(mask=mask, predicted=predicted, residual=residual, threshold=threshold)
