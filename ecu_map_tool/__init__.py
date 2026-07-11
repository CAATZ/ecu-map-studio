"""Professional ECU map interpolation and clipboard tooling."""

from .interpolation import ResampleResult, resample_map
from .model import CurveData, MapData, MapValidationError

__all__ = [
    "CurveData",
    "MapData",
    "MapValidationError",
    "ResampleResult",
    "resample_map",
]

__version__ = "1.1.0"
