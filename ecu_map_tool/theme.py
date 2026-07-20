APP_STYLE = r"""
QWidget {
    color: #e8eef8;
    font-family: "Segoe UI";
    font-size: 10pt;
}

QMainWindow, QDialog, QWidget#AppRoot {
    background: #080d18;
}

QToolBar#Map3DToolbar {
    color: #cbd6e5;
    background: #101827;
    border: 1px solid #223047;
    border-radius: 7px;
    padding: 3px;
    spacing: 2px;
}

QToolBar#Map3DToolbar QToolButton {
    color: #cbd6e5;
    background: transparent;
    border: 1px solid transparent;
    border-radius: 5px;
    min-width: 30px;
    min-height: 30px;
    padding: 1px;
}

QToolBar#Map3DToolbar QToolButton:hover {
    background: #202d45;
    border-color: #3e506e;
}

QToolBar#Map3DToolbar QToolButton:pressed,
QToolBar#Map3DToolbar QToolButton:checked {
    background: #111a2b;
    border-color: #35d0df;
}

QWidget#SidebarBody {
    background: #0b111d;
}

QMenuBar {
    color: #b8c5d8;
    background: #0b111d;
    border-bottom: 1px solid #1d293a;
    padding: 2px 6px;
}

QMenuBar::item {
    background: transparent;
    padding: 4px 9px;
    border-radius: 4px;
}

QMenuBar::item:selected {
    color: #f4f7fb;
    background: #1b273b;
}

QMenu {
    color: #e8eef8;
    background: #111827;
    border: 1px solid #31415c;
    padding: 5px;
}

QMenu::item {
    padding: 7px 24px 7px 10px;
    border-radius: 4px;
}

QMenu::item:selected {
    background: #20324a;
}

QFrame#TopBar {
    background: #0d1422;
    border-bottom: 1px solid #202b3d;
}

QLabel#AppTitle {
    color: #f8fbff;
    font-size: 18pt;
    font-weight: 700;
}

QLabel#AppSubtitle, QLabel#Muted, QLabel#FieldHint {
    color: #8e9cb1;
}

QLabel#SectionTitle {
    color: #f4f7fb;
    font-size: 11pt;
    font-weight: 650;
}

QLabel#StepPill {
    color: #061017;
    background: #35d0df;
    border-radius: 11px;
    min-width: 22px;
    max-width: 22px;
    min-height: 22px;
    max-height: 22px;
    font-weight: 800;
}

QLabel#Badge {
    color: #b8c5d8;
    background: #182235;
    border: 1px solid #293750;
    border-radius: 10px;
    padding: 3px 8px;
    font-size: 9pt;
}

QLabel#WarningBadge {
    color: #ffd98a;
    background: #2d2414;
    border: 1px solid #6c4c16;
    border-radius: 10px;
    padding: 3px 8px;
    font-size: 9pt;
}

QFrame#Card {
    background: #111827;
    border: 1px solid #223047;
    border-radius: 12px;
}

QFrame#MapHeader {
    background: #101827;
    border-bottom: 1px solid #26334a;
}

QFrame#MapActions {
    background: #101827;
    border-bottom: 1px solid #26334a;
}

QFrame#MapActions QPushButton {
    min-height: 30px;
    padding: 0 9px;
    font-size: 9pt;
}

QPushButton {
    min-height: 34px;
    padding: 0 13px;
    border-radius: 7px;
    border: 1px solid #2a3952;
    background: #172136;
    color: #dfe8f5;
    font-weight: 600;
}

QPushButton:hover {
    color: #ffffff;
    background: #21364d;
    border-color: #35d0df;
}

QPushButton:pressed {
    background: #111a2b;
}

QPushButton:disabled {
    color: #657189;
    background: #111827;
    border-color: #1d293a;
}

QPushButton#PrimaryButton {
    color: #041014;
    background: #35d0df;
    border-color: #35d0df;
    font-weight: 750;
}

QPushButton#PrimaryButton:hover {
    background: #67e0e9;
    border-color: #67e0e9;
}

QPushButton#PrimaryButton:focus {
    color: #041014;
    background: #35d0df;
    border-color: #8af0f5;
}

QPushButton#GenerateButton {
    color: #041014;
    background: #4ade80;
    border-color: #4ade80;
    min-height: 46px;
    font-size: 11pt;
    font-weight: 800;
}

QPushButton#GenerateButton:hover {
    background: #75e69b;
    border-color: #75e69b;
}

QPushButton#GhostButton {
    background: transparent;
    border-color: #28374f;
}

QPushButton#GhostButton:hover {
    color: #ffffff;
    background: #163246;
    border-color: #35d0df;
}

QWidget#TableZoomBar {
    background: #0d1422;
    border-top: 1px solid #202d42;
}

QPushButton#ZoomButton {
    color: #b9c8da;
    background: #111b2b;
    border: 1px solid #2b3a52;
    border-radius: 5px;
    padding: 1px 4px;
    min-height: 21px;
    max-height: 21px;
    font-size: 8.5pt;
    font-weight: 650;
}

QPushButton#ZoomButton:hover {
    color: #ffffff;
    border-color: #35d0df;
    background: #17263a;
}

QLineEdit, QPlainTextEdit, QComboBox, QSpinBox, QDoubleSpinBox {
    color: #eef4fb;
    background: #0c1320;
    border: 1px solid #2a3952;
    border-radius: 7px;
    padding: 6px 8px;
    selection-background-color: #238b9a;
}

QLineEdit:focus, QPlainTextEdit:focus, QComboBox:focus,
QSpinBox:focus, QDoubleSpinBox:focus {
    border: 1px solid #35d0df;
}

QComboBox::drop-down {
    border: none;
    width: 24px;
}

QComboBox QAbstractItemView {
    color: #e8eef8;
    background: #111827;
    border: 1px solid #31415c;
    selection-background-color: #20324a;
    outline: 0;
}

QTabWidget::pane {
    background: #0d1422;
    border: 1px solid #223047;
    border-radius: 10px;
    top: -1px;
}

QTabBar {
    outline: 0;
}

QTabBar::tab {
    color: #8898ae;
    background: transparent;
    padding: 9px 14px;
    border-bottom: 2px solid transparent;
    font-weight: 650;
}

QTabBar::tab:hover {
    color: #dbe6f4;
}

QTabBar::tab:selected {
    color: #54dbe6;
    border-bottom: 2px solid #35d0df;
}

QTabWidget#ModeTabs::pane {
    background: #0d1422;
    border: 1px solid #25334a;
    border-radius: 8px;
}

QTabWidget#ModeTabs QTabBar::tab {
    padding: 8px 11px;
    font-size: 8.5pt;
}

QTableWidget {
    color: #f8fbff;
    background: #0a101b;
    border: none;
    gridline-color: #29354a;
    selection-background-color: #ffffff;
    selection-color: #07101b;
    outline: 0;
}

QHeaderView::section {
    color: #b8c5d8;
    background: #131d2e;
    border: none;
    border-right: 1px solid #29364b;
    border-bottom: 1px solid #29364b;
    padding: 7px 6px;
    font-weight: 650;
}

QHeaderView::section:vertical {
    padding: 0 6px;
}

QHeaderView {
    background: #131d2e;
}

QTableCornerButton::section {
    background: #131d2e;
    border: none;
    border-right: 1px solid #29364b;
    border-bottom: 1px solid #29364b;
}

QScrollArea {
    border: none;
    background: transparent;
}

QScrollBar:vertical, QScrollBar:horizontal {
    background: #0b111d;
    border: none;
    margin: 0;
}

QScrollBar::handle:vertical, QScrollBar::handle:horizontal {
    background: #34425b;
    border-radius: 5px;
    min-height: 30px;
    min-width: 30px;
}

QScrollBar::handle:vertical:hover, QScrollBar::handle:horizontal:hover {
    background: #465873;
}

QScrollBar::add-line, QScrollBar::sub-line {
    width: 0;
    height: 0;
}

QSplitter::handle {
    background: transparent;
    width: 8px;
}

QStatusBar {
    color: #8796aa;
    background: #0b111d;
    border-top: 1px solid #1d293a;
}

QToolTip {
    color: #f2f6fb;
    background: #182235;
    border: 1px solid #3a4b67;
    padding: 5px;
}
"""
