"""About dialog for GitMan."""

from __future__ import annotations

import platform
import shutil
import subprocess
import sys
from pathlib import Path

import PySide6
from PySide6.QtCore import Qt, QUrl, qVersion
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from .. import __version__
from .theme import make_app_icon


def _git_version_text() -> str:
    executable = shutil.which("git")
    if not executable:
        return "未检测到 Git"
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if sys.platform == "win32" else 0
    try:
        completed = subprocess.run(
            [executable, "--version"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=4,
            creationflags=creationflags,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return "无法读取 Git 版本"
    output = completed.stdout.strip() or completed.stderr.strip()
    return output or "无法读取 Git 版本"


class AboutDialog(QDialog):
    def __init__(self, config_path: Path, parent=None):
        super().__init__(parent)
        self.config_path = Path(config_path)
        self.setWindowTitle("关于 GitMan")
        self.setWindowIcon(make_app_icon())
        self.setModal(True)
        self.setMinimumWidth(640)
        self.setWindowFlag(Qt.WindowType.WindowContextHelpButtonHint, False)
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 22)
        root.setSpacing(14)

        header = QHBoxLayout()
        header.setSpacing(18)

        icon = QLabel()
        icon.setPixmap(make_app_icon(128).pixmap(64, 64))
        icon.setFixedSize(64, 64)
        header.addWidget(icon, 0, Qt.AlignmentFlag.AlignTop)

        title_box = QVBoxLayout()
        title_box.setSpacing(5)
        title_line = QHBoxLayout()
        title_line.setSpacing(10)
        title = QLabel("GitMan")
        title.setObjectName("AppTitle")
        title_line.addWidget(title)

        version = QLabel(f"v{__version__}")
        version.setStyleSheet(
            "QLabel {"
            "background: #eef0ff; color: #4338ca; border-radius: 10px;"
            "padding: 3px 9px; font-size: 11px; font-weight: 600;"
            "}"
        )
        title_line.addWidget(version)
        title_line.addStretch(1)
        title_box.addLayout(title_line)

        subtitle = QLabel("多仓库状态看板 · 一键掌握本地与远程差异")
        subtitle.setObjectName("Muted")
        title_box.addWidget(subtitle)

        description = QLabel(
            "集中管理多个本地 Git 仓库，按私有 / 共享分类，快速查看分支、"
            "工作区变更以及本地与远程的提交差异。\n"
            "copyright © 2026 eein@163.com, MIT License.\n"
            "任何人都可以免费使用、修改和分发 GitMan，遇到问题可以在 GitHub 上提交 issue 或 pull request。或直接联系作者邮箱 eein@163.com\n"
        )
        description.setObjectName("Hint")
        description.setWordWrap(True)
        title_box.addWidget(description)
        header.addLayout(title_box, 1)
        root.addLayout(header)

        root.addWidget(self._divider())
        root.addWidget(self._build_features())
        root.addWidget(self._build_environment())
        root.addWidget(self._build_config_section())

        footer = QLabel(
            "GitMan 对仓库保持只读；刷新时仅执行 git fetch 更新远程跟踪引用。"
        )
        footer.setObjectName("Hint")
        footer.setWordWrap(True)
        root.addWidget(footer)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        close_button = QPushButton("关闭")
        close_button.setProperty("variant", "primary")
        close_button.setDefault(True)
        close_button.clicked.connect(self.accept)
        buttons.addWidget(close_button)
        root.addLayout(buttons)

    @staticmethod
    def _divider() -> QFrame:
        divider = QFrame()
        divider.setFrameShape(QFrame.Shape.HLine)
        divider.setStyleSheet("color: #edf1f7;")
        return divider

    def _build_features(self) -> QWidget:
        panel = QFrame()
        panel.setObjectName("SubPanel")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(16, 13, 16, 14)
        layout.setSpacing(9)

        title = QLabel("主要功能")
        title.setObjectName("SectionTitle")
        layout.addWidget(title)

        grid = QGridLayout()
        grid.setHorizontalSpacing(26)
        grid.setVerticalSpacing(7)
        features = (
            "多仓库统一管理与分类筛选",
            "一键抓取远程并刷新状态",
            "本地新 / 远程新 / 分叉提示",
            "提交历史、变更文件与补丁查看",
            "工作区暂存 / 未暂存 / 冲突统计",
            "配置随 EXE 同目录保存",
        )
        for index, text in enumerate(features):
            item = QLabel(f"•  {text}")
            item.setStyleSheet("color: #475569;")
            grid.addWidget(item, index // 2, index % 2)
        layout.addLayout(grid)
        return panel

    def _build_environment(self) -> QWidget:
        panel = QFrame()
        panel.setObjectName("SubPanel")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(16, 13, 16, 14)
        layout.setSpacing(8)

        title = QLabel("运行环境")
        title.setObjectName("SectionTitle")
        layout.addWidget(title)

        grid = QGridLayout()
        grid.setHorizontalSpacing(18)
        grid.setVerticalSpacing(6)
        grid.setColumnStretch(1, 1)
        rows = (
            ("版本", f"{__version__}"),
            ("运行方式", "打包版" if getattr(sys, "frozen", False) else "源码运行"),
            ("Python", platform.python_version()),
            ("PySide6 / Qt", f"{PySide6.__version__} / {qVersion()}"),
            ("Git", _git_version_text()),
        )
        for row, (label_text, value_text) in enumerate(rows):
            label = QLabel(label_text)
            label.setStyleSheet("color: #7b879b;")
            value = QLabel(value_text)
            value.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            value.setStyleSheet("color: #334155;")
            grid.addWidget(label, row, 0)
            grid.addWidget(value, row, 1)
        layout.addLayout(grid)
        return panel

    def _build_config_section(self) -> QWidget:
        panel = QFrame()
        panel.setObjectName("SubPanel")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(16, 13, 16, 14)
        layout.setSpacing(8)

        title = QLabel("配置文件")
        title.setObjectName("SectionTitle")
        layout.addWidget(title)

        hint = QLabel("仓库列表与刷新设置保存在程序所在目录的 config.json。")
        hint.setObjectName("Hint")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        row = QHBoxLayout()
        row.setSpacing(8)
        path_edit = QLineEdit(str(self.config_path))
        path_edit.setReadOnly(True)
        path_edit.setCursorPosition(0)
        path_edit.setToolTip(str(self.config_path))
        row.addWidget(path_edit, 1)

        copy_button = QPushButton("复制路径")
        copy_button.clicked.connect(self._copy_config_path)
        row.addWidget(copy_button)

        open_button = QPushButton("打开目录")
        open_button.clicked.connect(self._open_config_directory)
        row.addWidget(open_button)
        layout.addLayout(row)
        return panel

    def _copy_config_path(self) -> None:
        QApplication.clipboard().setText(str(self.config_path))
        QMessageBox.information(self, "已复制", "配置文件路径已复制到剪贴板。")

    def _open_config_directory(self) -> None:
        directory = self.config_path.parent
        if not directory.exists():
            QMessageBox.warning(self, "目录不存在", f"找不到目录：\n{directory}")
            return
        if not QDesktopServices.openUrl(QUrl.fromLocalFile(str(directory))):
            QMessageBox.warning(self, "无法打开", f"系统无法打开目录：\n{directory}")
