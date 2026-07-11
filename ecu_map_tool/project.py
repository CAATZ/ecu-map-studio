from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
from typing import Any

import numpy as np

from .curve import CURVE_METHOD_LABELS, CurveResampleResult
from .interpolation import EXTRAPOLATION_LABELS, METHOD_LABELS, ResampleResult
from .model import CurveData, MapData, MapValidationError


PROJECT_FORMAT = "ecu-map-studio-project"
PROJECT_VERSION = 1


def map_to_dict(value: MapData) -> dict[str, Any]:
    return {
        "name": value.name,
        "x": value.x.tolist(),
        "y": value.y.tolist(),
        "z": value.z.tolist(),
    }


def map_from_dict(value: Any) -> MapData:
    if not isinstance(value, dict):
        raise MapValidationError("Project map data is missing or invalid.")
    try:
        return MapData(value["x"], value["y"], value["z"], name=str(value.get("name", "Map")))
    except (KeyError, TypeError, ValueError) as exc:
        raise MapValidationError("Project contains invalid map data.") from exc


def curve_to_dict(value: CurveData) -> dict[str, Any]:
    return {"name": value.name, "x": value.x.tolist(), "values": value.values.tolist()}


def curve_from_dict(value: Any) -> CurveData:
    if not isinstance(value, dict):
        raise MapValidationError("Project curve data is missing or invalid.")
    try:
        return CurveData(value["x"], value["values"], name=str(value.get("name", "Curve")))
    except (KeyError, TypeError, ValueError) as exc:
        raise MapValidationError("Project contains invalid curve data.") from exc


def map_result_to_dict(value: ResampleResult) -> dict[str, Any]:
    return {
        "map": map_to_dict(value.map_data),
        "mask": value.extrapolated_mask.astype(bool).tolist(),
        "reference": map_to_dict(value.bilinear_reference),
        "delta": map_to_dict(value.delta_vs_bilinear),
        "method": value.method,
        "extrapolation": value.extrapolation,
    }


def map_result_from_dict(value: Any) -> ResampleResult:
    if not isinstance(value, dict):
        raise MapValidationError("Project result data is invalid.")
    try:
        result = ResampleResult(
            map_from_dict(value["map"]),
            np.asarray(value["mask"], dtype=bool),
            map_from_dict(value["reference"]),
            map_from_dict(value["delta"]),
            str(value["method"]),
            str(value["extrapolation"]),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise MapValidationError("Project contains an invalid generated result.") from exc
    shape = result.map_data.z.shape
    if (
        result.extrapolated_mask.shape != shape
        or result.bilinear_reference.z.shape != shape
        or result.delta_vs_bilinear.z.shape != shape
        or result.method not in METHOD_LABELS
        or result.extrapolation not in EXTRAPOLATION_LABELS
    ):
        raise MapValidationError("Project generated-result dimensions or methods are invalid.")
    return result


def curve_result_to_dict(value: CurveResampleResult) -> dict[str, Any]:
    return {
        "curve": curve_to_dict(value.curve_data),
        "mask": value.extrapolated_mask.astype(bool).tolist(),
        "reference": curve_to_dict(value.linear_reference),
        "delta": curve_to_dict(value.delta_vs_linear),
        "method": value.method,
        "extrapolation": value.extrapolation,
    }


def curve_result_from_dict(value: Any) -> CurveResampleResult:
    if not isinstance(value, dict):
        raise MapValidationError("Project curve result data is invalid.")
    try:
        result = CurveResampleResult(
            curve_from_dict(value["curve"]),
            np.asarray(value["mask"], dtype=bool),
            curve_from_dict(value["reference"]),
            curve_from_dict(value["delta"]),
            str(value["method"]),
            str(value["extrapolation"]),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise MapValidationError("Project contains an invalid generated curve.") from exc
    size = result.curve_data.size
    if (
        result.extrapolated_mask.shape != (size,)
        or result.linear_reference.size != size
        or result.delta_vs_linear.size != size
        or result.method not in CURVE_METHOD_LABELS
        or result.extrapolation not in EXTRAPOLATION_LABELS
    ):
        raise MapValidationError("Project generated-curve dimensions or methods are invalid.")
    return result


def save_project(path: str | os.PathLike[str], document: dict[str, Any]) -> None:
    destination = Path(path)
    payload = dict(document)
    payload["format"] = PROJECT_FORMAT
    payload["version"] = PROJECT_VERSION
    destination.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary_name = tempfile.mkstemp(
        prefix=f".{destination.name}.", suffix=".tmp", dir=destination.parent
    )
    try:
        with os.fdopen(handle, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(payload, stream, indent=2, ensure_ascii=False, allow_nan=False)
            stream.write("\n")
        os.replace(temporary_name, destination)
    except Exception:
        try:
            os.unlink(temporary_name)
        except OSError:
            pass
        raise


def load_project(path: str | os.PathLike[str]) -> dict[str, Any]:
    try:
        with Path(path).open("r", encoding="utf-8") as stream:
            payload = json.load(stream)
    except (OSError, json.JSONDecodeError) as exc:
        raise MapValidationError(f"Unable to read project: {exc}") from exc
    if not isinstance(payload, dict) or payload.get("format") != PROJECT_FORMAT:
        raise MapValidationError("This is not an ECU Map Studio project file.")
    version = payload.get("version")
    if version != PROJECT_VERSION:
        raise MapValidationError(
            f"Project version {version!r} is not supported; expected {PROJECT_VERSION}."
        )
    if payload.get("kind") not in {"map", "curve"}:
        raise MapValidationError("Project does not declare a supported map or curve type.")
    return payload
