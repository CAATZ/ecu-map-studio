# Changelog

All notable changes to ECU Map Studio are documented in this file.

The project follows [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Changed

- Updated the official GitHub workflow actions to their current Node 24-compatible major versions.

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
