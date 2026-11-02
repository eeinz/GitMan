"""Repository table model and filtering proxy."""

from __future__ import annotations

from PySide6.QtCore import (
    QAbstractTableModel,
    QModelIndex,
    QObject,
    QSortFilterProxyModel,
    Qt,
)
from PySide6.QtGui import QBrush, QColor, QFont

from ..models import CATEGORY_LABELS, RepoEntry, RepoStatus
from .formatting import (
    Badge,
    branch_text,
    branch_tooltip,
    category_badge,
    sync_badge,
    worktree_badge,
)


class Roles:
    RepoId = int(Qt.ItemDataRole.UserRole) + 1
    BadgeText = int(Qt.ItemDataRole.UserRole) + 2
    BadgeFg = int(Qt.ItemDataRole.UserRole) + 3
    BadgeBg = int(Qt.ItemDataRole.UserRole) + 4


class RepoTableModel(QAbstractTableModel):
    HEADERS = ("仓库", "分类", "当前分支", "工作区", "同步状态", "最近提交", "本地路径")
    COLUMN_REPO = 0
    COLUMN_CATEGORY = 1
    COLUMN_BRANCH = 2
    COLUMN_WORKTREE = 3
    COLUMN_SYNC = 4
    COLUMN_COMMIT = 5
    COLUMN_PATH = 6

    def __init__(self, parent: QObject | None = None):
        super().__init__(parent)
        self.entries: list[RepoEntry] = []
        self.statuses: dict[str, RepoStatus] = {}
        self.loading_ids: set[str] = set()
        self._row_by_id: dict[str, int] = {}

    # ------------------------------------------------------------- basic model
    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self.entries)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self.HEADERS)

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = 0):
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            return self.HEADERS[section]
        return None

    def data(self, index: QModelIndex, role: int = 0):
        if not index.isValid() or not (0 <= index.row() < len(self.entries)):
            return None
        entry = self.entries[index.row()]
        status = self.statuses.get(entry.id)
        loading = entry.id in self.loading_ids
        column = index.column()

        if role == Roles.RepoId:
            return entry.id

        if role == Qt.ItemDataRole.DisplayRole:
            if column == self.COLUMN_REPO:
                return entry.name
            if column == self.COLUMN_CATEGORY:
                return category_badge(entry.category).text
            if column == self.COLUMN_BRANCH:
                return branch_text(status, loading)
            if column == self.COLUMN_WORKTREE:
                return worktree_badge(status, loading).text
            if column == self.COLUMN_SYNC:
                return sync_badge(status, loading).text
            if column == self.COLUMN_COMMIT:
                if loading and not status:
                    return "读取中…"
                if status and not status.ok:
                    return status.error
                if status and status.last_commit:
                    return status.last_commit.subject
                return "（无提交）" if status else "—"
            if column == self.COLUMN_PATH:
                return entry.path
            return None

        if role == Roles.BadgeText and column in {
            self.COLUMN_CATEGORY,
            self.COLUMN_WORKTREE,
            self.COLUMN_SYNC,
        }:
            badge = self._badge_for(entry, status, loading, column)
            return badge.text

        if role == Roles.BadgeFg and column in {
            self.COLUMN_CATEGORY,
            self.COLUMN_WORKTREE,
            self.COLUMN_SYNC,
        }:
            return self._badge_for(entry, status, loading, column).fg

        if role == Roles.BadgeBg and column in {
            self.COLUMN_CATEGORY,
            self.COLUMN_WORKTREE,
            self.COLUMN_SYNC,
        }:
            return self._badge_for(entry, status, loading, column).bg

        if role == Qt.ItemDataRole.ToolTipRole:
            return self._tooltip(entry, status, loading, column)

        if role == Qt.ItemDataRole.FontRole:
            if column == self.COLUMN_REPO:
                font = QFont()
                font.setWeight(QFont.Weight.DemiBold)
                return font
            return None

        if role == Qt.ItemDataRole.ForegroundRole:
            if column == self.COLUMN_REPO:
                return QBrush(QColor("#b91c1c" if status and not status.ok else "#0f172a"))
            if column == self.COLUMN_BRANCH:
                return QBrush(QColor("#475569"))
            if column == self.COLUMN_COMMIT:
                if status and not status.ok:
                    return QBrush(QColor("#b91c1c"))
                return QBrush(QColor("#475569"))
            if column == self.COLUMN_PATH:
                return QBrush(QColor("#94a3b8"))
            return None

        if role == Qt.ItemDataRole.TextAlignmentRole:
            return int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

        if role == Qt.ItemDataRole.BackgroundRole and status and not status.ok:
            return QBrush(QColor("#fffafa"))

        return None

    def _badge_for(
        self,
        entry: RepoEntry,
        status: RepoStatus | None,
        loading: bool,
        column: int,
    ) -> Badge:
        if column == self.COLUMN_CATEGORY:
            return category_badge(entry.category)
        if column == self.COLUMN_WORKTREE:
            return worktree_badge(status, loading)
        return sync_badge(status, loading)

    def _tooltip(
        self,
        entry: RepoEntry,
        status: RepoStatus | None,
        loading: bool,
        column: int,
    ) -> str:
        if column == self.COLUMN_REPO:
            lines = [entry.name, entry.path]
            if status and not status.ok:
                lines.append(f"错误：{status.error}")
            elif loading:
                lines.append("正在刷新…")
            elif status:
                lines.append(f"分支：{status.branch or '—'}")
                if status.remote_url:
                    lines.append(f"远程：{status.remote_url}")
            return "\n".join(lines)
        if column == self.COLUMN_CATEGORY:
            return f"分类：{CATEGORY_LABELS.get(entry.category, entry.category)}"
        if column == self.COLUMN_BRANCH:
            return branch_tooltip(status)
        if column == self.COLUMN_WORKTREE:
            return worktree_badge(status, loading).tooltip
        if column == self.COLUMN_SYNC:
            return sync_badge(status, loading).tooltip
        if column == self.COLUMN_COMMIT:
            if not status:
                return "尚未读取最近提交"
            if not status.ok:
                return status.error
            commit = status.last_commit
            if not commit:
                return "仓库还没有提交"
            return (
                f"{commit.hash}\n{commit.author} · {commit.date_display}\n\n{commit.subject}"
            )
        if column == self.COLUMN_PATH:
            return entry.path
        return ""

    # ------------------------------------------------------------- mutations
    def set_entries(self, entries: list[RepoEntry]) -> None:
        self.beginResetModel()
        self.entries = list(entries)
        self._rebuild_index()
        self.endResetModel()

    def _rebuild_index(self) -> None:
        self._row_by_id = {entry.id: row for row, entry in enumerate(self.entries)}

    def row_for_id(self, repo_id: str) -> int:
        return self._row_by_id.get(repo_id, -1)

    def entry_at(self, row: int) -> RepoEntry | None:
        if 0 <= row < len(self.entries):
            return self.entries[row]
        return None

    def status_for(self, repo_id: str) -> RepoStatus | None:
        return self.statuses.get(repo_id)

    def set_loading(self, repo_ids: set[str]) -> None:
        self.loading_ids = set(repo_ids)
        if self.entries:
            self.dataChanged.emit(
                self.index(0, 0),
                self.index(len(self.entries) - 1, len(self.HEADERS) - 1),
                [
                    Qt.ItemDataRole.DisplayRole,
                    Qt.ItemDataRole.ToolTipRole,
                    Roles.BadgeText,
                    Roles.BadgeFg,
                    Roles.BadgeBg,
                ],
            )

    def update_status(self, status: RepoStatus) -> None:
        row = self._row_by_id.get(status.repo_id, -1)
        self.statuses[status.repo_id] = status
        self.loading_ids.discard(status.repo_id)
        if row < 0:
            return
        self.dataChanged.emit(
            self.index(row, 0),
            self.index(row, len(self.HEADERS) - 1),
            [
                Qt.ItemDataRole.DisplayRole,
                Qt.ItemDataRole.ToolTipRole,
                Qt.ItemDataRole.ForegroundRole,
                Qt.ItemDataRole.BackgroundRole,
                Roles.BadgeText,
                Roles.BadgeFg,
                Roles.BadgeBg,
            ],
        )

    def remove_status(self, repo_id: str) -> None:
        self.statuses.pop(repo_id, None)
        self.loading_ids.discard(repo_id)

    def clear_statuses(self) -> None:
        self.statuses.clear()
        self.loading_ids.clear()
        if self.entries:
            self.dataChanged.emit(
                self.index(0, 0),
                self.index(len(self.entries) - 1, len(self.HEADERS) - 1),
            )


class RepoFilterProxyModel(QSortFilterProxyModel):
    def __init__(self, parent: QObject | None = None):
        super().__init__(parent)
        self._category = ""
        self._query = ""
        self.setDynamicSortFilter(True)

    def set_category(self, category: str) -> None:
        if category == self._category:
            return
        self._category = category
        self.invalidateFilter()

    def set_query(self, query: str) -> None:
        normalized = query.strip().casefold()
        if normalized == self._query:
            return
        self._query = normalized
        self.invalidateFilter()

    def filterAcceptsRow(self, source_row: int, source_parent: QModelIndex) -> bool:
        model = self.sourceModel()
        if not isinstance(model, RepoTableModel):
            return True
        entry = model.entry_at(source_row)
        if entry is None:
            return False
        if self._category and entry.category != self._category:
            return False
        if not self._query:
            return True

        status = model.status_for(entry.id)
        searchable = [
            entry.name,
            entry.path,
            CATEGORY_LABELS.get(entry.category, ""),
            status.branch if status else "",
            status.upstream if status else "",
            status.remote_url if status else "",
        ]
        haystack = "\n".join(searchable).casefold()
        return self._query in haystack
