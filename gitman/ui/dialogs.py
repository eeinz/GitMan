"""Dialogs for adding and editing repositories."""

from __future__ import annotations

import os
import uuid
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QButtonGroup,
    QDialog,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..git_service import GitService, GitServiceError
from ..models import CATEGORY_LABELS, CATEGORY_PRIVATE, CATEGORY_SHARED, RepoEntry


def _path_key(path: str) -> str:
    return os.path.normcase(os.path.abspath(path))


class CategorySelector(QWidget):
    """A small two-option segmented control for private / shared."""

    def __init__(self, selected: str = CATEGORY_PRIVATE, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        self.group = QButtonGroup(self)
        self.group.setExclusive(True)
        self.buttons: dict[str, QPushButton] = {}
        for index, category in enumerate((CATEGORY_PRIVATE, CATEGORY_SHARED)):
            button = QPushButton(CATEGORY_LABELS[category])
            button.setCheckable(True)
            button.setProperty("chip", True)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            self.group.addButton(button, index)
            self.buttons[category] = button
            layout.addWidget(button)
        layout.addStretch(1)
        self.set_category(selected)

    def set_category(self, category: str) -> None:
        button = self.buttons.get(category) or self.buttons[CATEGORY_PRIVATE]
        button.setChecked(True)

    def category(self) -> str:
        for category, button in self.buttons.items():
            if button.isChecked():
                return category
        return CATEGORY_PRIVATE


class AddRepoDialog(QDialog):
    def __init__(
        self,
        service: GitService,
        existing_paths: set[str],
        default_category: str = CATEGORY_PRIVATE,
        parent=None,
    ):
        super().__init__(parent)
        self.service = service
        self.existing_paths = {_path_key(path) for path in existing_paths}
        self.result_entry: RepoEntry | None = None
        self._auto_name = True

        self.setWindowTitle("添加仓库")
        self.setModal(True)
        self.setMinimumWidth(640)
        self._build_ui(default_category)

    def _build_ui(self, default_category: str) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(26, 24, 26, 22)
        root.setSpacing(14)

        title = QLabel("添加 Git 仓库")
        title.setObjectName("DetailTitle")
        subtitle = QLabel("选择一个本地 Git 文件夹，GitMan 会自动识别仓库根目录。")
        subtitle.setObjectName("Muted")
        subtitle.setWordWrap(True)
        root.addWidget(title)
        root.addWidget(subtitle)

        divider = QFrame()
        divider.setFrameShape(QFrame.Shape.HLine)
        divider.setStyleSheet("color: #edf1f7;")
        root.addWidget(divider)

        path_label = QLabel("本地仓库文件夹")
        path_label.setObjectName("SectionTitle")
        root.addWidget(path_label)

        path_row = QHBoxLayout()
        path_row.setSpacing(8)
        self.path_edit = QLineEdit()
        self.path_edit.setPlaceholderText(r"例如：E:\Projects\my-repository")
        self.path_edit.setClearButtonEnabled(True)
        browse = QPushButton("浏览…")
        browse.clicked.connect(self._browse)
        path_row.addWidget(self.path_edit, 1)
        path_row.addWidget(browse)
        root.addLayout(path_row)

        name_label = QLabel("显示名称")
        name_label.setObjectName("SectionTitle")
        root.addWidget(name_label)
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("默认使用文件夹名称")
        root.addWidget(self.name_edit)

        category_label = QLabel("仓库分类")
        category_label.setObjectName("SectionTitle")
        root.addWidget(category_label)
        self.category_selector = CategorySelector(default_category)
        root.addWidget(self.category_selector)

        hint = QLabel("私有与共享仅用于分组筛选，不会改变仓库本身。")
        hint.setObjectName("Hint")
        root.addWidget(hint)

        root.addStretch(1)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        cancel = QPushButton("取消")
        cancel.clicked.connect(self.reject)
        add = QPushButton("添加仓库")
        add.setProperty("variant", "primary")
        add.setDefault(True)
        add.clicked.connect(self._accept)
        buttons.addWidget(cancel)
        buttons.addWidget(add)
        root.addLayout(buttons)

        self.path_edit.textChanged.connect(self._path_changed)
        self.name_edit.textEdited.connect(self._name_edited)

    def _path_changed(self, text: str) -> None:
        if not self._auto_name:
            return
        stripped = text.strip().rstrip("\\/")
        name = Path(stripped).name if stripped else ""
        self.name_edit.setText(name)

    def _name_edited(self, _text: str) -> None:
        self._auto_name = False

    def _browse(self) -> None:
        start = self.path_edit.text().strip() or str(Path.home())
        selected = QFileDialog.getExistingDirectory(self, "选择本地 Git 仓库", start)
        if selected:
            self.path_edit.setText(selected)
            self.name_edit.setText(Path(selected.rstrip("\\/")).name)
            self._auto_name = True

    def _accept(self) -> None:
        raw_path = self.path_edit.text().strip()
        if len(raw_path) >= 2 and raw_path[0] == raw_path[-1] and raw_path[0] in {'"', "'"}:
            raw_path = raw_path[1:-1].strip()
        if not raw_path:
            QMessageBox.warning(self, "路径为空", "请填写或选择本地 Git 仓库文件夹。")
            self.path_edit.setFocus()
            return

        try:
            root = self.service.probe_repository(raw_path)
        except GitServiceError as exc:
            QMessageBox.warning(
                self,
                "不是有效的 Git 仓库",
                f"无法使用这个文件夹：\n{exc}\n\n请选择包含 .git 的本地仓库目录。",
            )
            self.path_edit.setFocus()
            return

        key = _path_key(str(root))
        if key in self.existing_paths:
            QMessageBox.information(self, "仓库已存在", "这个仓库已经在管理列表中。")
            return

        name = self.name_edit.text().strip()
        if self._auto_name or not name:
            name = root.name or str(root)
        category = self.category_selector.category()
        self.result_entry = RepoEntry(
            id=uuid.uuid4().hex,
            name=name,
            path=str(root),
            category=str(category),
        )
        self.accept()


class EditRepoDialog(QDialog):
    def __init__(self, entry: RepoEntry, parent=None):
        super().__init__(parent)
        self.entry = entry
        self.result_entry: RepoEntry | None = None

        self.setWindowTitle("编辑仓库")
        self.setModal(True)
        self.setMinimumWidth(560)
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(26, 24, 26, 22)
        root.setSpacing(14)

        title = QLabel("编辑仓库")
        title.setObjectName("DetailTitle")
        root.addWidget(title)

        path_label = QLabel("本地路径")
        path_label.setObjectName("SectionTitle")
        root.addWidget(path_label)
        path_edit = QLineEdit(self.entry.path)
        path_edit.setReadOnly(True)
        path_edit.setStyleSheet("background: #f8fafc; color: #7b879b;")
        root.addWidget(path_edit)

        name_label = QLabel("显示名称")
        name_label.setObjectName("SectionTitle")
        root.addWidget(name_label)
        self.name_edit = QLineEdit(self.entry.name)
        root.addWidget(self.name_edit)

        category_label = QLabel("仓库分类")
        category_label.setObjectName("SectionTitle")
        root.addWidget(category_label)
        self.category_selector = CategorySelector(self.entry.category)
        root.addWidget(self.category_selector)

        root.addStretch(1)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        cancel = QPushButton("取消")
        cancel.clicked.connect(self.reject)
        save = QPushButton("保存")
        save.setProperty("variant", "primary")
        save.setDefault(True)
        save.clicked.connect(self._accept)
        buttons.addWidget(cancel)
        buttons.addWidget(save)
        root.addLayout(buttons)

    def _accept(self) -> None:
        name = self.name_edit.text().strip() or Path(self.entry.path).name
        category = self.category_selector.category()
        self.result_entry = RepoEntry(
            id=self.entry.id,
            name=name,
            path=self.entry.path,
            category=str(category),
        )
        self.accept()
