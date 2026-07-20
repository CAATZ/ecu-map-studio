# Changelog

All notable changes to ECU Map Studio are documented in this file.

The project follows [Semantic Versioning](https://semver.org/).

## [Unreleased]

## [1.2.0] - 2026-07-20

### Added

- Added boundary-matched local 4 × 4 and global whole-table least-squares trend extrapolation.
- Added deterministic selected-row, selected-column, and rectangular interpolation to both Source and Result tables.
- Added matching smoothing, math, comparison, axis-editing, visualization, and export actions to the Result table.
- Added direct numeric entry across selected cells: type a value and press Enter to apply one undoable edit.
- Added standard PyInstaller and alternative Nuitka Windows installers.

### Changed

- Improved table fitting, coarse axis labels, compact axis/math inputs, and low-zoom cell editing.
- Made the left control panel reliably resizable after loading or pasting a table.
- Prevented mouse-wheel scrolling from changing combo-box selections.
- Updated the official GitHub workflow actions to their current Node 24-compatible major versions.
- Licensed the project and distributed release bundles under the MIT License.

### Fixed

- Fixed Apply in the map and curve selection-math dialogs.
- Fixed clipped table headers, action labels, axis values, and in-cell editor digits.

## [1.1.0] - 2026-07-11

### Added

- Direct RomRaider `[Table3D]` and Excel-style map clipboard import and export.
- Dedicated `[Table2D]` curve editor with automatic routing from the main window.
- Automatic constant-spacing target grids and fully custom target axes.
- Bilinear, shape-preserving PCHIP, and nearest-neighbor interpolation.
- Held-edge, limited-linear, and disabled extrapolation policies.
- Preserved extended-table padding with repeated X or Y breakpoints.
- Source, result, and reference heat maps with explicit extrapolation markers.
- Live X/Y slice plots and an interactive 3D surface viewer.
- Deterministic anomaly detection, selected-region repair, and whole-table smoothing.
- Editable source and generated cells, block copy/paste, selection math, and undo/redo.
- Project save/open, clipboard comparison and merge, and numerical safety reports.
- Clean-session reset for both 3D maps and 2D curves.
- Single-file Windows executable packaging and an illustrated user manual.

### Changed

- Consolidated the application around the `ecu_map_tool` package and one supported entry point.
- Added consistent formatting, lint configuration, package metadata, and automated Windows tests.
- Improved RomRaider clipboard validation and actionable error messages.

### Fixed

- Prevented recursive heat-map updates when importing and recoloring larger tables.
- Accepted padded extended tables without rejecting intentionally repeated breakpoints.
- Preserved masked cells when applying RomRaider selection payloads.
- Allowed a cleared workspace to accept another table without restarting the application.
