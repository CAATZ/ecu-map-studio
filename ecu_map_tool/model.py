from __future__ import annotations

from dataclasses import dataclass

import numpy as np


class MapValidationError(ValueError):
    """Raised when a map or an axis cannot be used safely."""


def validate_axis(values, name: str, minimum_points: int = 2) -> np.ndarray:
    axis = np.asarray(values, dtype=float).reshape(-1)
    if axis.size < minimum_points:
        raise MapValidationError(
            f"{name} axis needs at least {minimum_points} values; got {axis.size}."
        )
    if not np.all(np.isfinite(axis)):
        raise MapValidationError(f"{name} axis contains a blank or non-finite value.")

    steps = np.diff(axis)
    if np.any(steps == 0):
        raise MapValidationError(f"{name} axis contains duplicate values.")
    if not (np.all(steps > 0) or np.all(steps < 0)):
        raise MapValidationError(f"{name} axis must be strictly ascending or strictly descending.")
    return axis


def validate_map_axis(values, name: str, minimum_points: int = 2) -> np.ndarray:
    """Validate a map axis while permitting RomRaider's repeated padded bins."""
    axis = np.asarray(values, dtype=float).reshape(-1)
    if axis.size < minimum_points:
        raise MapValidationError(
            f"{name} axis needs at least {minimum_points} values; got {axis.size}."
        )
    if not np.all(np.isfinite(axis)):
        raise MapValidationError(f"{name} axis contains a blank or non-finite value.")

    steps = np.diff(axis)
    nonzero_steps = steps[steps != 0]
    if nonzero_steps.size == 0 or np.unique(axis).size < minimum_points:
        raise MapValidationError(f"{name} axis needs at least {minimum_points} distinct values.")
    if not (np.all(nonzero_steps > 0) or np.all(nonzero_steps < 0)):
        raise MapValidationError(
            f"{name} axis must be ascending or descending; repeated values may only pad "
            "an otherwise ordered axis."
        )
    return axis


@dataclass(frozen=True)
class MapData:
    x: np.ndarray
    y: np.ndarray
    z: np.ndarray
    name: str = "Untitled map"

    def __post_init__(self) -> None:
        x = validate_map_axis(self.x, "X")
        y = validate_map_axis(self.y, "Y")
        z = np.asarray(self.z, dtype=float)

        expected = (y.size, x.size)
        if z.ndim != 2 or z.shape != expected:
            raise MapValidationError(
                f"Z grid shape must be {expected[0]} rows by {expected[1]} columns; "
                f"got {tuple(z.shape)}."
            )
        if not np.all(np.isfinite(z)):
            raise MapValidationError("Z grid contains a blank or non-finite value.")

        object.__setattr__(self, "x", x.copy())
        object.__setattr__(self, "y", y.copy())
        object.__setattr__(self, "z", z.copy())

    @property
    def rows(self) -> int:
        return int(self.y.size)

    @property
    def columns(self) -> int:
        return int(self.x.size)

    @property
    def value_range(self) -> tuple[float, float]:
        return float(np.min(self.z)), float(np.max(self.z))

    def ascending(self) -> "MapData":
        """Return a copy with ascending axes and matching Z orientation."""
        x = self.x.copy()
        y = self.y.copy()
        z = self.z.copy()

        if x[0] > x[-1]:
            x = x[::-1]
            z = z[:, ::-1]
        if y[0] > y[-1]:
            y = y[::-1]
            z = z[::-1, :]
        return MapData(x=x, y=y, z=z, name=self.name)


@dataclass(frozen=True)
class CollapsedMap:
    """A unique-coordinate view plus mappings back to a padded source table."""

    map_data: MapData
    x_inverse: np.ndarray
    y_inverse: np.ndarray
    removed_x: int
    removed_y: int

    @property
    def has_duplicates(self) -> bool:
        return bool(self.removed_x or self.removed_y)

    def collapse_mask(self, mask: np.ndarray) -> np.ndarray:
        source = np.asarray(mask, dtype=bool)
        expected = (self.y_inverse.size, self.x_inverse.size)
        if source.shape != expected:
            raise MapValidationError(
                f"Mask shape must be {expected[0]} rows by {expected[1]} columns."
            )
        collapsed = np.zeros(self.map_data.z.shape, dtype=bool)
        for row in range(source.shape[0]):
            for column in range(source.shape[1]):
                if source[row, column]:
                    collapsed[self.y_inverse[row], self.x_inverse[column]] = True
        return collapsed

    def expand_values(self, values: np.ndarray) -> np.ndarray:
        source = np.asarray(values)
        if source.shape != self.map_data.z.shape:
            raise MapValidationError("Collapsed values do not match the unique-coordinate map.")
        return source[np.ix_(self.y_inverse, self.x_inverse)].copy()


def _axis_inverse(axis: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    keep: list[int] = []
    inverse = np.empty(axis.size, dtype=int)
    unique_index = -1
    previous: float | None = None
    for index, value in enumerate(axis):
        if index == 0 or value != previous:
            keep.append(index)
            unique_index += 1
        inverse[index] = unique_index
        previous = float(value)
    return np.asarray(keep, dtype=int), inverse


def _matching_duplicate_values(left: np.ndarray, right: np.ndarray) -> bool:
    scale = max(
        1.0,
        float(np.max(np.abs(left))),
        float(np.max(np.abs(right))),
    )
    return bool(np.allclose(left, right, rtol=1e-12, atol=scale * 1e-12))


def collapse_duplicate_map(map_data: MapData) -> CollapsedMap:
    """Collapse redundant coordinates, rejecting ambiguous duplicate slices."""
    x_keep, x_inverse = _axis_inverse(map_data.x)
    y_keep, y_inverse = _axis_inverse(map_data.y)

    for column, unique_column in enumerate(x_inverse):
        reference_column = x_keep[unique_column]
        if column != reference_column and not _matching_duplicate_values(
            map_data.z[:, column], map_data.z[:, reference_column]
        ):
            raise MapValidationError(
                f"X axis value {format_number(map_data.x[column], 12)} is repeated, but "
                "its Z columns are different. Interpolation at one coordinate would be "
                "ambiguous; make the repeated columns identical or use distinct X values."
            )

    for row, unique_row in enumerate(y_inverse):
        reference_row = y_keep[unique_row]
        if row != reference_row and not _matching_duplicate_values(
            map_data.z[row, :], map_data.z[reference_row, :]
        ):
            raise MapValidationError(
                f"Y axis value {format_number(map_data.y[row], 12)} is repeated, but "
                "its Z rows are different. Interpolation at one coordinate would be "
                "ambiguous; make the repeated rows identical or use distinct Y values."
            )

    unique_map = MapData(
        map_data.x[x_keep],
        map_data.y[y_keep],
        map_data.z[np.ix_(y_keep, x_keep)],
        name=map_data.name,
    )
    return CollapsedMap(
        map_data=unique_map,
        x_inverse=x_inverse,
        y_inverse=y_inverse,
        removed_x=int(map_data.columns - unique_map.columns),
        removed_y=int(map_data.rows - unique_map.rows),
    )


@dataclass(frozen=True)
class CurveData:
    x: np.ndarray
    values: np.ndarray
    name: str = "Untitled curve"

    def __post_init__(self) -> None:
        x = validate_axis(self.x, "X")
        values = np.asarray(self.values, dtype=float).reshape(-1)
        if values.size != x.size:
            raise MapValidationError(
                f"Curve needs one value for each X breakpoint; got {values.size} values "
                f"for {x.size} breakpoints."
            )
        if not np.all(np.isfinite(values)):
            raise MapValidationError("Curve contains a blank or non-finite value.")
        object.__setattr__(self, "x", x.copy())
        object.__setattr__(self, "values", values.copy())

    @property
    def size(self) -> int:
        return int(self.x.size)

    @property
    def value_range(self) -> tuple[float, float]:
        return float(np.min(self.values)), float(np.max(self.values))

    def ascending(self) -> "CurveData":
        if self.x[0] < self.x[-1]:
            return CurveData(self.x, self.values, self.name)
        return CurveData(self.x[::-1], self.values[::-1], self.name)


def _parse_axis_values(text: str, name: str) -> list[float]:
    import re

    clean = text.strip()
    if not clean:
        raise MapValidationError(f"{name} axis is empty.")

    # Semicolon-separated values commonly accompany a decimal comma locale.
    if ";" in clean and "." not in clean:
        raw_tokens = re.split(r"[;\s]+", clean)
        raw_tokens = [token.replace(",", ".") for token in raw_tokens if token]
    else:
        raw_tokens = [token for token in re.split(r"[,;\s]+", clean) if token]

    try:
        values = [float(token) for token in raw_tokens]
    except ValueError as exc:
        raise MapValidationError(f"{name} axis contains an invalid number: {exc}.") from exc
    return values


def parse_axis_text(text: str, name: str) -> np.ndarray:
    """Parse a strictly ordered curve or interpolation axis."""
    return validate_axis(_parse_axis_values(text, name), name)


def parse_map_axis_text(text: str, name: str) -> np.ndarray:
    """Parse a map axis, including deliberate repeated padding breakpoints."""
    return validate_map_axis(_parse_axis_values(text, name), name)


def parse_number_text(text: str, name: str) -> float:
    clean = text.strip().replace("\u2212", "-")
    if not clean:
        raise MapValidationError(f"{name} is empty.")
    if "," in clean and "." not in clean:
        clean = clean.replace(",", ".")
    try:
        value = float(clean)
    except ValueError as exc:
        raise MapValidationError(f"{name} is not a valid number.") from exc
    if not np.isfinite(value):
        raise MapValidationError(f"{name} must be finite.")
    return value


def generate_even_axis(minimum: float, maximum: float, count: int, name: str) -> np.ndarray:
    minimum = float(minimum)
    maximum = float(maximum)
    count = int(count)
    if not np.isfinite(minimum) or not np.isfinite(maximum):
        raise MapValidationError(f"{name} minimum and maximum must be finite.")
    if count < 2:
        raise MapValidationError(f"{name} axis needs at least two values.")
    if maximum <= minimum:
        raise MapValidationError(f"{name} maximum must be greater than its minimum.")
    return np.linspace(minimum, maximum, count, dtype=float)


def axis_to_text(axis: np.ndarray, precision: int = 17) -> str:
    return ", ".join(format_number(value, precision) for value in axis)


def format_number(value: float, precision: int = 8) -> str:
    value = float(value)
    if value == 0:
        value = 0.0
    return f"{value:.{precision}g}"


def format_axis_label(value: float) -> str:
    """Format a table-axis breakpoint as a coarse whole number."""
    return str(round(float(value)))
