from __future__ import annotations

import sys
import os
from pathlib import Path

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import QApplication

from .main_window import ECUMapMainWindow
from .theme import APP_STYLE


def resource_path(relative_path: str) -> Path:
    """Resolve packaged resources in source and PyInstaller builds."""
    bundle_root = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[1]))
    return bundle_root / relative_path


def create_application(argv=None) -> QApplication:
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
    app = QApplication.instance() or QApplication(argv or sys.argv)
    app.setApplicationName("ECU Map Studio")
    app.setOrganizationName("ECU Map Studio")
    icon_path = resource_path("assets/ECUMapStudio.png")
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))
    app.setStyle("Fusion")
    app.setStyleSheet(APP_STYLE)
    # Headless tests create and close many independent top-level windows. Do not
    # let Qt terminate their shared application between test cases.
    if os.environ.get("QT_QPA_PLATFORM", "").lower() == "offscreen":
        app.setQuitOnLastWindowClosed(False)
    return app


def _packaged_smoke_test(app: QApplication) -> int:
    """Exercise lazy imports and core workflows inside a packaged executable."""
    from .curve_window import CurveWindow
    from .model import CurveData
    from .visualization import Map3DDialog

    map_window = ECUMapMainWindow()
    map_window.load_demo_map()
    map_window.generate_result()
    if map_window.result is None:
        raise RuntimeError("Map generation did not produce a result.")

    surface = Map3DDialog(
        map_window.result.map_data,
        "Packaged smoke test",
        map_window.result.extrapolated_mask,
    )
    surface.canvas.draw()
    if surface.axes is None or not surface.axes.collections:
        raise RuntimeError("The packaged 3D surface did not render.")

    curve_window = CurveWindow(CurveData([0.0, 1.0, 2.0, 3.0], [1.0, 2.5, 2.0, 4.0], "Smoke test"))
    curve_window.generate_result()
    if curve_window.result is None:
        raise RuntimeError("Curve generation did not produce a result.")

    app.processEvents()
    surface.close()
    curve_window.close()
    map_window.close()
    app.processEvents()
    return 0


def main() -> int:
    smoke_test = "--smoke-test" in sys.argv
    if smoke_test:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = create_application()
    if smoke_test:
        try:
            return _packaged_smoke_test(app)
        except Exception:
            import traceback

            traceback.print_exc()
            return 1
    window = ECUMapMainWindow()
    window.show()
    return app.exec_()
