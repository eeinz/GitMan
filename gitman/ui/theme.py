"""Visual theme and application icon."""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (
    QColor,
    QFont,
    QFontDatabase,
    QIcon,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
)
from PySide6.QtWidgets import QApplication


APP_QSS = """
QWidget {
    color: #1e293b;
    font-size: 13px;
}
QMainWindow, QDialog, QWidget#Central {
    background: #f3f5fa;
}
QFrame#AppHeader, QFrame#Panel, QFrame#SubPanel {
    background: #ffffff;
    border: 1px solid #e4e9f2;
    border-radius: 14px;
}
QFrame#SubPanel {
    border-radius: 10px;
}
QLabel {
    background: transparent;
}
QLabel#AppTitle {
    color: #0f172a;
    font-size: 23px;
    font-weight: 700;
}
QLabel#AppSubtitle {
    color: #7b879b;
    font-size: 12px;
}
QLabel#SectionTitle {
    color: #0f172a;
    font-size: 14px;
    font-weight: 700;
}
QLabel#DetailTitle {
    color: #0f172a;
    font-size: 17px;
    font-weight: 700;
}
QLabel#Muted {
    color: #7b879b;
}
QLabel#Hint {
    color: #94a3b8;
    font-size: 12px;
}
QLabel#EmptyTitle {
    color: #334155;
    font-size: 17px;
    font-weight: 600;
}
QLabel#EmptyBody {
    color: #8a97aa;
    font-size: 12px;
}
QLabel#CommitSubject {
    color: #0f172a;
    font-size: 14px;
    font-weight: 600;
}
QLabel#CommitMeta {
    color: #718096;
    font-size: 12px;
}
QLabel#DiffPlaceholder {
    color: #9aa7ba;
    background: #f8fafc;
    border: 1px dashed #dbe3ef;
    border-radius: 8px;
    padding: 16px;
}

QPushButton {
    background: #ffffff;
    border: 1px solid #dce3ee;
    border-radius: 8px;
    color: #334155;
    font-weight: 500;
    min-height: 22px;
    padding: 7px 14px;
}
QPushButton:hover {
    background: #f8faff;
    border-color: #b8c4d9;
}
QPushButton:pressed {
    background: #eef2f9;
}
QPushButton:disabled {
    background: #f4f6fa;
    border-color: #e7ebf2;
    color: #a1adbf;
}
QPushButton[variant="primary"] {
    background: #4f46e5;
    border-color: #4f46e5;
    color: #ffffff;
    font-weight: 600;
}
QPushButton[variant="primary"]:hover {
    background: #4338ca;
    border-color: #4338ca;
}
QPushButton[variant="primary"]:pressed {
    background: #3730a3;
}
QPushButton[variant="primary"]:disabled {
    background: #c7c4f4;
    border-color: #c7c4f4;
    color: #ffffff;
}
QPushButton[variant="danger"] {
    color: #b91c1c;
    border-color: #f1caca;
}
QPushButton[variant="danger"]:hover {
    background: #fff5f5;
    border-color: #e9a8a8;
}
QPushButton[chip="true"] {
    background: transparent;
    border: 1px solid transparent;
    border-radius: 15px;
    color: #64748b;
    font-weight: 600;
    min-height: 18px;
    padding: 5px 13px;
}
QPushButton[chip="true"]:hover {
    background: #f4f6fb;
    border-color: #e2e8f2;
}
QPushButton[chip="true"]:checked {
    background: #eef0ff;
    border-color: #dfe3ff;
    color: #4338ca;
}
QPushButton[toggle="true"] {
    border-radius: 15px;
    padding: 5px 12px;
    min-height: 18px;
    color: #64748b;
    background: #f8fafc;
    border: 1px solid #e4e9f2;
}
QPushButton[toggle="true"]:checked {
    background: #eef0ff;
    border-color: #dfe3ff;
    color: #4338ca;
    font-weight: 600;
}
QPushButton[flat="true"] {
    border: none;
    background: transparent;
    padding: 5px 8px;
    color: #64748b;
}
QPushButton[flat="true"]:hover {
    background: #f2f5fb;
    color: #334155;
}

QLineEdit, QComboBox {
    background: #ffffff;
    border: 1px solid #dfe5ef;
    border-radius: 8px;
    color: #1e293b;
    min-height: 22px;
    padding: 6px 10px;
    selection-background-color: #c7d2fe;
    selection-color: #111827;
}
QLineEdit:hover, QComboBox:hover {
    border-color: #c9d3e2;
}
QLineEdit:focus, QComboBox:focus {
    border-color: #818cf8;
}
QLineEdit:disabled, QComboBox:disabled {
    background: #f5f7fa;
    color: #9aa7ba;
}
QComboBox::drop-down {
    border: none;
    width: 26px;
}
QComboBox QAbstractItemView {
    background: #ffffff;
    border: 1px solid #dfe5ef;
    border-radius: 8px;
    padding: 4px;
    selection-background-color: #eef2ff;
    selection-color: #1e293b;
    outline: 0;
}

QTableView, QTableWidget {
    background: #ffffff;
    border: none;
    border-radius: 9px;
    gridline-color: transparent;
    outline: 0;
    selection-background-color: #eef2ff;
    selection-color: #0f172a;
}
QTableView::item, QTableWidget::item {
    border-bottom: 1px solid #f1f4f9;
    padding: 4px 10px;
}
QTableView::item:selected, QTableWidget::item:selected {
    background: #eef2ff;
    color: #0f172a;
}
QHeaderView::section {
    background: #f8fafc;
    border: none;
    border-bottom: 1px solid #e6ebf3;
    color: #64748b;
    font-weight: 600;
    padding: 9px 10px;
}
QHeaderView::section:first {
    border-top-left-radius: 9px;
}
QHeaderView::section:last {
    border-top-right-radius: 9px;
}
QTableCornerButton::section {
    background: #f8fafc;
    border: none;
    border-bottom: 1px solid #e6ebf3;
}

QTabWidget::pane {
    background: #ffffff;
    border: 1px solid #e6eaf2;
    border-radius: 10px;
    top: -1px;
}
QTabBar::tab {
    background: transparent;
    border: none;
    border-bottom: 2px solid transparent;
    color: #64748b;
    margin-right: 6px;
    padding: 8px 14px;
}
QTabBar::tab:hover {
    color: #334155;
}
QTabBar::tab:selected {
    border-bottom: 2px solid #4f46e5;
    color: #4338ca;
    font-weight: 600;
}

QSplitter::handle {
    background: transparent;
}
QSplitter::handle:vertical {
    height: 12px;
}
QSplitter::handle:horizontal {
    width: 12px;
}

QPlainTextEdit, QTextEdit {
    background: #ffffff;
    border: 1px solid #e3e9f2;
    border-radius: 8px;
    color: #334155;
    padding: 7px;
    selection-background-color: #c7d2fe;
    selection-color: #111827;
}
QPlainTextEdit#DiffView {
    background: #0f172a;
    border: 1px solid #1e293b;
    border-radius: 8px;
    color: #cbd5e1;
    font-family: "Cascadia Mono", "Consolas", "JetBrains Mono", monospace;
    font-size: 12px;
    padding: 10px;
    selection-background-color: #334155;
    selection-color: #f8fafc;
}
QPlainTextEdit#MessageView {
    background: #f8fafc;
    border: 1px solid #e6ebf3;
    border-radius: 8px;
    color: #334155;
    font-size: 12px;
    padding: 8px;
}

QScrollBar:vertical {
    background: transparent;
    width: 10px;
    margin: 2px;
}
QScrollBar::handle:vertical {
    background: #cdd7e6;
    border-radius: 4px;
    min-height: 28px;
}
QScrollBar::handle:vertical:hover {
    background: #aebcd1;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical,
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
    background: none;
    border: none;
    height: 0px;
}
QScrollBar:horizontal {
    background: transparent;
    height: 10px;
    margin: 2px;
}
QScrollBar::handle:horizontal {
    background: #cdd7e6;
    border-radius: 4px;
    min-width: 28px;
}
QScrollBar::handle:horizontal:hover {
    background: #aebcd1;
}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal,
QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {
    background: none;
    border: none;
    width: 0px;
}

QMenu {
    background: #ffffff;
    border: 1px solid #dfe5ef;
    border-radius: 8px;
    padding: 5px;
}
QMenu::item {
    border-radius: 5px;
    padding: 7px 22px 7px 12px;
}
QMenu::item:selected {
    background: #eef2ff;
    color: #3730a3;
}
QMenu::separator {
    background: #eef2f7;
    height: 1px;
    margin: 5px 8px;
}

QToolTip {
    background: #111827;
    border: 1px solid #1f2937;
    border-radius: 6px;
    color: #e5e7eb;
    padding: 6px 8px;
}

QProgressBar {
    background: #eef2f8;
    border: none;
    border-radius: 3px;
    max-height: 6px;
    min-height: 6px;
    text-align: center;
}
QProgressBar::chunk {
    background: #6366f1;
    border-radius: 3px;
}

QMessageBox {
    background: #f8fafc;
}
QMessageBox QLabel {
    color: #334155;
}
"""


def pick_ui_font() -> QFont:
    available = set(QFontDatabase.families())
    for family in (
        "Microsoft YaHei UI",
        "Microsoft YaHei",
        "Noto Sans CJK SC",
        "PingFang SC",
        "Segoe UI",
    ):
        if family in available:
            font = QFont(family)
            font.setPointSize(9)
            return font
    return QFont()


def apply_theme(app: QApplication) -> None:
    app.setStyle("Fusion")
    app.setFont(pick_ui_font())
    app.setStyleSheet(APP_QSS)


def make_app_icon(size: int = 64) -> QIcon:
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

    gradient = QLinearGradient(0, 0, size, size)
    gradient.setColorAt(0, QColor("#6366f1"))
    gradient.setColorAt(1, QColor("#4338ca"))
    path = QPainterPath()
    path.addRoundedRect(QRectF(2, 2, size - 4, size - 4), size * 0.24, size * 0.24)
    painter.fillPath(path, gradient)

    painter.setPen(
        QPen(QColor("#ffffff"), size * 0.052, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
    )
    painter.drawLine(QPointF(size * 0.34, size * 0.27), QPointF(size * 0.34, size * 0.73))
    painter.drawLine(QPointF(size * 0.34, size * 0.49), QPointF(size * 0.66, size * 0.49))
    painter.drawLine(QPointF(size * 0.66, size * 0.49), QPointF(size * 0.66, size * 0.68))

    painter.setBrush(QColor("#ffffff"))
    painter.setPen(Qt.PenStyle.NoPen)
    radius = size * 0.075
    for cx, cy in ((0.34, 0.27), (0.34, 0.73), (0.66, 0.49)):
        painter.drawEllipse(QPointF(size * cx, size * cy), radius, radius)

    painter.end()
    return QIcon(pixmap)
