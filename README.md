<p align="center">
  <img src="assets/ECUMapStudio.png" width="112" alt="ECU Map Studio icon">
</p>

<h1 align="center">ECU Map Studio</h1>

<p align="center">
  Resize, inspect, edit, smooth, and compare ECU calibration tables with direct RomRaider clipboard support.
</p>

> [!WARNING]
> ECU Map Studio performs numerical transformations; it cannot determine whether a calibration is safe for an engine. Review every result and validate changes with appropriate logs, instrumentation, and calibration practices.

## Overview

ECU Map Studio is a Windows desktop application for resampling ECU maps and curves onto new breakpoint grids. It accepts complete RomRaider tables directly from the clipboard, eliminating the usual Excel intermediary, and makes extrapolated data visually explicit.

The application supports:

- RomRaider `[Table3D]` maps with X, Y, and Z data.
- RomRaider `[Table2D]` curves with one axis and one value series.
- Excel-compatible tab-separated tables.
- Automatic constant-spacing axes or fully custom breakpoints.
- Bilinear, shape-preserving PCHIP, and nearest-neighbor interpolation.
- Held-edge, limited-linear, or disabled extrapolation.
- Heat maps, live X/Y slices, interactive 3D surfaces, and difference views.
- Deterministic selected-region and whole-table smoothing with previews and warnings.
- Cell editing, block copy/paste, selection math, comparison/merge, undo/redo, and project files.

## Screens and analysis tools

| Tool | Purpose |
| --- | --- |
| Heat map | Inspect the complete source, result, or difference table. |
| Live X/Y slices | Follow both cross-sections through the selected heat-map cell. |
| 3D surface | Rotate, pan, and zoom a surface snapshot; extrapolated points remain highlighted. |
| VS BILINEAR / VS LINEAR | Show how the selected smooth method differs from the predictable linear reference. |
| Safety report | Summarize changes, extrapolated cells, extrema, RMS difference, and sharp adjacent edges. |

## Quick start

### Run from source

Python 3.10 or newer is required.

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
.\.venv\Scripts\python app.py
```

Once the environment exists, `run_app.bat` starts the application directly.

### Basic RomRaider workflow

1. In RomRaider, copy the complete table using **Copy Table**.
2. In ECU Map Studio, choose **Paste RomRaider / Excel table**.
3. Set an automatic target range and table size, or enter custom axes.
4. Select the interpolation and boundary policies.
5. Generate the result and inspect the heat map, extrapolated cells, slices, 3D surface, and safety report.
6. Choose **Copy for RomRaider**, paste the complete result into RomRaider, and validate the calibration.

RomRaider selection payloads do not contain axes. Load a complete table first, select the destination cell, and then paste the selection.

## Extended RomRaider tables

Some expanded calibrations repeat their final X or Y breakpoint so a larger table initially behaves like the smaller original table. ECU Map Studio preserves every imported row, column, repeated breakpoint, and Z value.

When repeated coordinates contain matching values, calculations use an equivalent unique-coordinate surface without rewriting the source table. Use **Edit source axes** when the new breakpoints are ready to be assigned. If values at one repeated coordinate no longer match, surface calculations pause until those breakpoints are made distinct because the coordinate has become mathematically ambiguous.

## Numerical methods

### Interpolation

| Method | Recommended use |
| --- | --- |
| Bilinear | Predictable default for normal ignition, fuel, boost, and similar continuous maps. It is local and does not overshoot within a source cell. |
| PCHIP | A smoother, shape-preserving result when the source grid has at least four points on each axis. Compare it with the bilinear reference before use. |
| Nearest neighbor | Categorical maps, switches, or intentionally discrete levels. |

For 2D curves, Linear is the predictable default, PCHIP provides a smoother shape-preserving curve, and Nearest preserves discrete levels.

### Extrapolation

| Policy | Behavior |
| --- | --- |
| Hold edge values | Clamps out-of-range coordinates to the nearest known boundary. This is the default. |
| Limited linear | Continues the nearest edge slope for a configurable number of edge intervals. |
| Do not extrapolate | Rejects any target grid extending beyond the source range. |

Adding more breakpoints inside the original axis limits is interpolation, not extrapolation. Extrapolation occurs only when a target axis extends beyond a source limit.

## Smoothing

Smoothing is deterministic and deliberately has no strength slider.

- **Detect suspicious cells** identifies strong interior anomalies without changing data.
- **Repair selected cells** reconstructs only the selected region from the unchanged surrounding surface.
- **Smooth entire table** performs one axis-aware pass and always shows a warning, proposed map, and difference preview before it can be applied.
- **Undo last smoothing** restores the values from before the accepted operation.

A visually smoother calibration is not necessarily a better or safer calibration. Intentional steps, ridges, and compensations can be flattened by smoothing.

## 2D curves

Open **2D Curve Tool** from the main window or paste a complete `[Table2D]` payload and the application will route it automatically. The curve tool provides automatic or custom target axes, interpolation and extrapolation policies, plotted results, difference views, anomaly detection, repair, smoothing, selection math, undo/redo, and RomRaider copy-back.

## Projects and editing

Versioned `.ecumap` project files preserve the loaded source, generated result, extrapolation mask, target axes, numerical settings, and display precision. Source and generated results have separate undo histories.

Use **Clear table / New session** or `Ctrl+N` to reset a map workspace. The 2D curve window provides the equivalent command. Resetting a session does not modify RomRaider or the system clipboard.

## Build the Windows executable

Install the build dependencies and run the reproducible build script:

```powershell
.\.venv\Scripts\python -m pip install -r requirements-dev.txt
.\build_exe.bat
```

The single-file application is written to `dist\ECUMapStudio.exe`. Build output is intentionally excluded from version control; publish executables as versioned release assets instead.

## Prepare a release

The release helper validates version metadata, lint and formatting, runs the complete test suite and source smoke test, builds the executable, runs the packaged smoke test, and prepares versioned artifacts:

```powershell
.\packaging\prepare_release.ps1 -Version 1.1.0
```

The ignored `release\v1.1.0` directory contains:

- A versioned standalone Windows executable.
- A portable ZIP containing the executable, manual, README, and changelog.
- The illustrated PDF manual.
- `SHA256SUMS.txt` for download-integrity verification.

Pushing a matching `v1.1.0` tag runs the same release process in GitHub Actions and creates the GitHub Release. GitHub automatically adds source-code ZIP and TAR archives for the tag.

## Tests

The test suite covers clipboard layouts, padded tables, interpolation and extrapolation policies, smoothing, projects, comparison and merge behavior, 2D curves, live slices, 3D rendering, table editing, and headless Qt workflows.

```powershell
.\.venv\Scripts\python -m unittest discover -s tests -v
```

The repository includes a Windows CI workflow that runs the suite on supported Python versions.

## Documentation

The illustrated [ECU Map Studio User Manual](output/pdf/ECU_Map_Studio_User_Manual.pdf) provides the complete end-user workflow, screenshots, troubleshooting guidance, and calibration checklist.

## Repository layout

```text
ecu_map_tool/        Application, numerical methods, clipboard support, and UI
tests/               Unit, integration, and headless GUI tests
tests/fixtures/      RomRaider clipboard fixtures
assets/              Application icon assets
packaging/           Executable, icon, screenshot, and manual build helpers
output/pdf/          Published user manual
CHANGELOG.md         Version history
app.py               Source entry point
ECUMapStudio.spec    PyInstaller configuration
```

## Compatibility and scope

ECU Map Studio is developed and tested on Windows. Clipboard integration targets RomRaider table formats and conventional Excel-compatible TSV layouts. The project is independent and is not affiliated with or endorsed by the RomRaider project.

## License

No open-source license has been selected yet. Until a license is added, all rights are reserved. Choose an appropriate license before making the repository public.
