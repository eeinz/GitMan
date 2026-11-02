"""Main application window."""

from __future__ import annotations

import logging
import os
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import (
    QModelIndex,
    QPoint,
    QSettings,
    Qt,
    QThreadPool,
    QTimer,
    QUrl,
)
from PySide6.QtGui import (
    QColor,
    QDesktopServices,
    QFont,
    QKeySequence,
    QShortcut,
)
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QStackedWidget,
    QTabWidget,
    QTableView,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..config import ConfigStore
from ..git_service import GitService
from ..models import (
    AppConfig,
    CATEGORY_PRIVATE,
    CATEGORY_SHARED,
    CommitDetail,
    CommitInfo,
    RepoEntry,
    RepoStatus,
)
from ..workers import CommitDetailWorker, CommitListWorker, ScanRepoWorker
from .about_dialog import AboutDialog
from .delegates import BadgeDelegate
from .dialogs import AddRepoDialog, EditRepoDialog
from .formatting import (
    Badge,
    commit_file_label,
    category_badge,
    sync_badge,
    sync_summary,
    working_change_labels,
)
from .repo_model import RepoFilterProxyModel, RepoTableModel, Roles
from .syntax import DiffHighlighter
from .theme import make_app_icon


LOGGER = logging.getLogger(__name__)


class MainWindow(QMainWindow):
    COMMIT_LIMIT = 200
    COMMIT_CACHE_LIMIT = 80

    def __init__(
        self,
        store: ConfigStore,
        config: AppConfig,
        startup_message: str | None = None,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self.store = store
        self.entries = list(config.repos)
        self.settings = config.settings
        self.service = GitService()
        self.pool = QThreadPool(self)
        self.pool.setMaxThreadCount(max(4, min(8, (os.cpu_count() or 4))))

        self._scan_generation = 0
        self._scan_pending: set[str] = set()
        self._scan_total = 0
        self._scan_done = 0
        self._refresh_active = False
        self._last_refresh: datetime | None = None
        self._selected_repo_id: str | None = None
        self._closing = False
        self._scan_workers: list[ScanRepoWorker] = []
        self._commit_workers: list[object] = []
        self._commit_detail_workers: list[object] = []

        self._commit_list_request = 0
        self._commit_detail_request = 0
        self._commits_repo_id: str | None = None
        self._commits_head: str | None = None
        self._commit_cache: dict[tuple[str, str], CommitDetail] = {}
        self._startup_message = startup_message

        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(220)
        self._search_timer.timeout.connect(self._apply_search)

        self._build_ui()
        self.model.set_entries(self.entries)
        self._restore_window_state()
        self._refresh_counts()
        self._update_empty_state()
        self._update_scan_label()
        self._update_detail_panel(None)
        if self.entries:
            self._ensure_selection()

        QTimer.singleShot(120, self._startup)

    # ================================================================== UI setup
    def _build_ui(self) -> None:
        self.setWindowTitle("GitMan · 多仓库状态看板")
        self.setMinimumSize(1080, 720)
        self.resize(1380, 900)
        self.setWindowIcon(make_app_icon())

        central = QWidget()
        central.setObjectName("Central")
        root = QVBoxLayout(central)
        root.setContentsMargins(16, 12, 16, 12)
        root.setSpacing(10)
        self.setCentralWidget(central)

        root.addWidget(self._build_header())
        self.main_splitter = QSplitter(Qt.Orientation.Vertical)
        self.main_splitter.setChildrenCollapsible(False)
        self.repo_panel = self._build_repo_panel()
        self.repo_panel.setMinimumHeight(235)
        self.main_splitter.addWidget(self.repo_panel)
        self.detail_panel = self._build_detail_panel()
        self.detail_panel.setMinimumHeight(355)
        self.main_splitter.addWidget(self.detail_panel)
        self.main_splitter.setStretchFactor(0, 5)
        self.main_splitter.setStretchFactor(1, 4)
        self.main_splitter.setSizes([520, 300])
        root.addWidget(self.main_splitter, 1)

        self._build_shortcuts()

    def _build_header(self) -> QWidget:
        header = QFrame()
        header.setObjectName("AppHeader")
        layout = QHBoxLayout(header)
        layout.setContentsMargins(18, 10, 16, 10)
        layout.setSpacing(12)

        logo = QLabel()
        logo.setPixmap(make_app_icon(72).pixmap(36, 36))
        logo.setFixedSize(36, 36)
        layout.addWidget(logo)

        title_box = QVBoxLayout()
        title_box.setSpacing(1)
        title = QLabel("GitMan")
        title.setObjectName("AppTitle")
        subtitle = QLabel("多仓库状态看板 · 一键掌握本地与远程差异")
        subtitle.setObjectName("AppSubtitle")
        title_box.addWidget(title)
        title_box.addWidget(subtitle)
        layout.addLayout(title_box)
        layout.addStretch(1)

        self.scan_label = QLabel()
        self.scan_label.setObjectName("Hint")
        self.scan_label.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        layout.addWidget(self.scan_label)

        self.about_button = QPushButton("关于")
        self.about_button.setProperty("flat", True)
        self.about_button.setToolTip("关于 GitMan（F1）")
        self.about_button.clicked.connect(self._show_about)
        layout.addWidget(self.about_button)

        self.add_button = QPushButton("＋  添加仓库")
        self.add_button.clicked.connect(self._add_repo)
        layout.addWidget(self.add_button)

        self.refresh_button = QPushButton("⟳  一键刷新")
        self.refresh_button.setProperty("variant", "primary")
        self.refresh_button.setToolTip("抓取远程并刷新所有仓库状态（F5）")
        self.refresh_button.clicked.connect(self.refresh_all)
        layout.addWidget(self.refresh_button)
        return header

    def _build_repo_panel(self) -> QWidget:
        panel = QFrame()
        panel.setObjectName("Panel")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(14, 12, 14, 10)
        layout.setSpacing(8)

        top = QHBoxLayout()
        top.setSpacing(8)
        section = QLabel("仓库总览")
        section.setObjectName("SectionTitle")
        top.addWidget(section)

        self.category_group = QButtonGroup(self)
        self.category_group.setExclusive(True)
        self.category_buttons: list[QPushButton] = []
        for index, text in enumerate(("全部", "私有", "共享")):
            button = QPushButton(text)
            button.setCheckable(True)
            button.setProperty("chip", True)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            self.category_group.addButton(button, index)
            self.category_buttons.append(button)
            top.addWidget(button)
        self.category_buttons[0].setChecked(True)
        self.category_group.idClicked.connect(self._on_category_filter)
        top.addStretch(1)

        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("搜索名称 / 路径 / 分支")
        self.search_edit.setClearButtonEnabled(True)
        self.search_edit.setFixedWidth(250)
        self.search_edit.textChanged.connect(lambda _text: self._search_timer.start())
        top.addWidget(self.search_edit)

        self.fetch_toggle = QPushButton("抓取远程")
        self.fetch_toggle.setCheckable(True)
        self.fetch_toggle.setProperty("toggle", True)
        self.fetch_toggle.setChecked(self.settings.fetch_on_refresh)
        self.fetch_toggle.setCursor(Qt.CursorShape.PointingHandCursor)
        self.fetch_toggle.setToolTip(
            "开启后，一键刷新会先执行 git fetch --all --prune（只更新远程跟踪分支，不改工作区）。"
            "\n关闭后仅比较已有的远程跟踪信息，状态可能过期。"
        )
        self.fetch_toggle.toggled.connect(self._on_fetch_toggled)
        top.addWidget(self.fetch_toggle)
        layout.addLayout(top)

        sub = QHBoxLayout()
        sub.setSpacing(8)
        self.summary_label = QLabel()
        self.summary_label.setObjectName("Hint")
        sub.addWidget(self.summary_label)
        sub.addStretch(1)
        self.selected_hint = QLabel("双击仓库可在资源管理器中打开")
        self.selected_hint.setObjectName("Hint")
        sub.addWidget(self.selected_hint)
        layout.addLayout(sub)

        self.repo_stack = QStackedWidget()
        self.repo_stack.addWidget(self._build_repo_table())
        self.repo_stack.addWidget(self._build_empty_page())
        layout.addWidget(self.repo_stack, 1)

        self.scan_progress = QProgressBar()
        self.scan_progress.setTextVisible(False)
        self.scan_progress.setRange(0, 1)
        self.scan_progress.setValue(0)
        self.scan_progress.setVisible(False)
        layout.addWidget(self.scan_progress)
        return panel

    def _build_repo_table(self) -> QWidget:
        self.model = RepoTableModel(self)
        self.proxy = RepoFilterProxyModel(self)
        self.proxy.setSourceModel(self.model)

        self.table = QTableView()
        self.table.setModel(self.proxy)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setShowGrid(False)
        self.table.setWordWrap(False)
        self.table.setAlternatingRowColors(False)
        self.table.setTextElideMode(Qt.TextElideMode.ElideMiddle)
        self.table.setMouseTracking(True)
        self.table.viewport().setMouseTracking(True)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(38)
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._show_context_menu)
        self.table.doubleClicked.connect(lambda _index: self._open_selected_folder())

        header = self.table.horizontalHeader()
        header.setHighlightSections(False)
        header.setMinimumSectionSize(64)
        header.setSectionResizeMode(RepoTableModel.COLUMN_REPO, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(
            RepoTableModel.COLUMN_CATEGORY, QHeaderView.ResizeMode.Fixed
        )
        header.setSectionResizeMode(
            RepoTableModel.COLUMN_BRANCH, QHeaderView.ResizeMode.Interactive
        )
        header.setSectionResizeMode(
            RepoTableModel.COLUMN_WORKTREE, QHeaderView.ResizeMode.Fixed
        )
        header.setSectionResizeMode(
            RepoTableModel.COLUMN_SYNC, QHeaderView.ResizeMode.Fixed
        )
        header.setSectionResizeMode(
            RepoTableModel.COLUMN_COMMIT, QHeaderView.ResizeMode.Stretch
        )
        header.setSectionResizeMode(
            RepoTableModel.COLUMN_PATH, QHeaderView.ResizeMode.Interactive
        )
        self.table.setColumnWidth(RepoTableModel.COLUMN_REPO, 175)
        self.table.setColumnWidth(RepoTableModel.COLUMN_CATEGORY, 78)
        self.table.setColumnWidth(RepoTableModel.COLUMN_BRANCH, 128)
        self.table.setColumnWidth(RepoTableModel.COLUMN_WORKTREE, 126)
        self.table.setColumnWidth(RepoTableModel.COLUMN_SYNC, 146)
        self.table.setColumnWidth(RepoTableModel.COLUMN_PATH, 178)

        badge_delegate = BadgeDelegate(self.table)
        for column in (
            RepoTableModel.COLUMN_CATEGORY,
            RepoTableModel.COLUMN_WORKTREE,
            RepoTableModel.COLUMN_SYNC,
        ):
            self.table.setItemDelegateForColumn(column, badge_delegate)

        self.table.selectionModel().currentChanged.connect(self._on_current_changed)
        return self.table

    def _build_empty_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.addStretch(1)

        icon = QLabel()
        icon.setPixmap(make_app_icon(128).pixmap(64, 64))
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(icon)

        title = QLabel("还没有管理中的仓库")
        title.setObjectName("EmptyTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        body = QLabel(
            "点击“添加仓库”，填写本地 Git 文件夹地址。\n"
            "可以按私有 / 共享分类，刷新后即可查看分支、工作区与远程差异。"
        )
        body.setObjectName("EmptyBody")
        body.setAlignment(Qt.AlignmentFlag.AlignCenter)
        body.setWordWrap(True)
        layout.addWidget(body)

        add = QPushButton("＋  添加第一个仓库")
        add.setProperty("variant", "primary")
        add.setFixedWidth(170)
        add.clicked.connect(self._add_repo)
        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(add)
        row.addStretch(1)
        layout.addSpacing(8)
        layout.addLayout(row)
        layout.addStretch(1)
        return page

    def _build_detail_panel(self) -> QWidget:
        panel = QFrame()
        panel.setObjectName("Panel")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(8)

        header_row = QHBoxLayout()
        header_row.setSpacing(10)
        name_box = QVBoxLayout()
        name_box.setSpacing(3)

        name_line = QHBoxLayout()
        name_line.setSpacing(8)
        self.detail_name = QLabel("未选择仓库")
        self.detail_name.setObjectName("DetailTitle")
        name_line.addWidget(self.detail_name)
        self.detail_category = QLabel()
        self.detail_category.setVisible(False)
        name_line.addWidget(self.detail_category)
        self.detail_sync = QLabel()
        self.detail_sync.setVisible(False)
        name_line.addWidget(self.detail_sync)
        name_line.addStretch(1)
        name_box.addLayout(name_line)

        self.detail_path = QLabel("")
        self.detail_path.setObjectName("Muted")
        self.detail_path.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.detail_path.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        name_box.addWidget(self.detail_path)

        self.detail_note = QLabel("")
        self.detail_note.setObjectName("Hint")
        self.detail_note.setSizePolicy(
            QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred
        )
        name_box.addWidget(self.detail_note)
        header_row.addLayout(name_box, 1)

        self.open_button = QPushButton("打开文件夹")
        self.open_button.setEnabled(False)
        self.open_button.clicked.connect(self._open_selected_folder)
        header_row.addWidget(self.open_button, 0, Qt.AlignmentFlag.AlignTop)
        layout.addLayout(header_row)

        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_commit_tab(), "提交记录")
        self.tabs.addTab(self._build_worktree_tab(), "工作区变更")
        layout.addWidget(self.tabs, 1)
        return panel

    def _build_commit_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(10, 8, 10, 10)
        layout.setSpacing(6)

        bar = QHBoxLayout()
        bar.setSpacing(8)
        self.commit_branch_label = QLabel("提交记录")
        self.commit_branch_label.setObjectName("SectionTitle")
        bar.addWidget(self.commit_branch_label)
        self.commit_hint = QLabel("选择仓库后加载当前分支提交")
        self.commit_hint.setObjectName("Hint")
        bar.addWidget(self.commit_hint)
        bar.addStretch(1)
        self.commit_refresh_button = QPushButton("刷新提交")
        self.commit_refresh_button.setFlat(True)
        self.commit_refresh_button.setProperty("flat", True)
        self.commit_refresh_button.clicked.connect(lambda: self._load_commits(force=True))
        bar.addWidget(self.commit_refresh_button)
        layout.addLayout(bar)

        self.commit_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.commit_splitter.setChildrenCollapsible(False)

        self.commit_table = QTableWidget(0, 4)
        self.commit_table.setHorizontalHeaderLabels(("时间", "提交", "作者", "说明"))
        self._configure_commit_table()
        self.commit_splitter.addWidget(self.commit_table)

        detail = QFrame()
        detail.setObjectName("SubPanel")
        detail_layout = QVBoxLayout(detail)
        detail_layout.setContentsMargins(12, 11, 12, 12)
        detail_layout.setSpacing(7)

        self.commit_subject = QLabel("提交详情")
        self.commit_subject.setObjectName("CommitSubject")
        self.commit_subject.setWordWrap(True)
        self.commit_subject.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        detail_layout.addWidget(self.commit_subject)

        self.commit_meta = QLabel("从左侧选择一条提交查看文件变更与补丁。")
        self.commit_meta.setObjectName("CommitMeta")
        self.commit_meta.setWordWrap(True)
        self.commit_meta.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        detail_layout.addWidget(self.commit_meta)

        self.commit_detail_stack = QStackedWidget()
        placeholder = QLabel("选择一条提交后，可查看变更文件和完整补丁。")
        placeholder.setObjectName("DiffPlaceholder")
        placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        placeholder.setWordWrap(True)
        self.commit_detail_stack.addWidget(placeholder)

        self.commit_info_tabs = QTabWidget()
        self.commit_info_tabs.setDocumentMode(True)

        files_page = QWidget()
        files_layout = QVBoxLayout(files_page)
        files_layout.setContentsMargins(4, 8, 4, 4)
        self.commit_files = QTableWidget(0, 2)
        self.commit_files.setHorizontalHeaderLabels(("状态", "文件"))
        self._configure_commit_files()
        files_layout.addWidget(self.commit_files)
        self.commit_info_tabs.addTab(files_page, "变更文件")

        diff_page = QWidget()
        diff_layout = QVBoxLayout(diff_page)
        diff_layout.setContentsMargins(4, 8, 4, 4)
        self.diff_view = QPlainTextEdit()
        self.diff_view.setObjectName("DiffView")
        self.diff_view.setReadOnly(True)
        self.diff_view.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.diff_view.setPlaceholderText("该提交没有可显示的补丁内容。")
        self._diff_highlighter = DiffHighlighter(self.diff_view.document())
        diff_layout.addWidget(self.diff_view)
        self.commit_info_tabs.addTab(diff_page, "补丁")

        message_page = QWidget()
        message_layout = QVBoxLayout(message_page)
        message_layout.setContentsMargins(4, 8, 4, 4)
        self.message_view = QPlainTextEdit()
        self.message_view.setObjectName("MessageView")
        self.message_view.setReadOnly(True)
        message_layout.addWidget(self.message_view)
        self.commit_info_tabs.addTab(message_page, "提交说明")
        self.commit_info_tabs.setCurrentIndex(1)

        self.commit_detail_stack.addWidget(self.commit_info_tabs)
        detail_layout.addWidget(self.commit_detail_stack, 1)

        self.commit_splitter.addWidget(detail)
        self.commit_splitter.setStretchFactor(0, 6)
        self.commit_splitter.setStretchFactor(1, 5)
        self.commit_splitter.setSizes([620, 480])
        layout.addWidget(self.commit_splitter, 1)

        self.commit_table.itemSelectionChanged.connect(self._on_commit_selection_changed)
        return tab

    def _configure_commit_table(self) -> None:
        table = self.commit_table
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setShowGrid(False)
        table.setWordWrap(False)
        table.setAlternatingRowColors(False)
        table.setTextElideMode(Qt.TextElideMode.ElideRight)
        table.verticalHeader().setVisible(False)
        table.verticalHeader().setDefaultSectionSize(38)
        header = table.horizontalHeader()
        header.setHighlightSections(False)
        header.setMinimumSectionSize(55)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        table.setColumnWidth(0, 150)
        table.setColumnWidth(1, 84)
        table.setColumnWidth(2, 115)

    def _configure_commit_files(self) -> None:
        table = self.commit_files
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setShowGrid(False)
        table.setWordWrap(False)
        table.verticalHeader().setVisible(False)
        table.verticalHeader().setDefaultSectionSize(34)
        header = table.horizontalHeader()
        header.setHighlightSections(False)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        table.setColumnWidth(0, 88)

    def _build_worktree_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(10, 8, 10, 10)
        layout.setSpacing(6)

        bar = QHBoxLayout()
        self.worktree_title = QLabel("工作区变更")
        self.worktree_title.setObjectName("SectionTitle")
        bar.addWidget(self.worktree_title)
        self.worktree_hint = QLabel("")
        self.worktree_hint.setObjectName("Hint")
        bar.addWidget(self.worktree_hint)
        bar.addStretch(1)
        layout.addLayout(bar)

        self.worktree_table = QTableWidget(0, 4)
        self.worktree_table.setHorizontalHeaderLabels(("状态", "暂存", "未暂存", "文件"))
        self.worktree_table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.worktree_table.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection
        )
        self.worktree_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.worktree_table.setShowGrid(False)
        self.worktree_table.setWordWrap(False)
        self.worktree_table.verticalHeader().setVisible(False)
        self.worktree_table.verticalHeader().setDefaultSectionSize(34)
        header = self.worktree_table.horizontalHeader()
        header.setHighlightSections(False)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.worktree_table.setColumnWidth(0, 125)
        self.worktree_table.setColumnWidth(1, 70)
        self.worktree_table.setColumnWidth(2, 78)
        layout.addWidget(self.worktree_table, 1)
        return tab

    def _build_shortcuts(self) -> None:
        QShortcut(QKeySequence("F5"), self, activated=self.refresh_all)
        QShortcut(QKeySequence("Ctrl+N"), self, activated=self._add_repo)
        QShortcut(QKeySequence("Ctrl+F"), self, activated=self._focus_search)
        QShortcut(QKeySequence("F1"), self, activated=self._show_about)

    def _show_about(self) -> None:
        dialog = AboutDialog(self.store.path, self)
        dialog.exec()

    # ================================================================= startup
    def _startup(self) -> None:
        if self._startup_message:
            QMessageBox.warning(self, "配置提示", self._startup_message)
            self._startup_message = None
        if self.entries:
            self.refresh_all()
        else:
            self._update_empty_state()

    def _focus_search(self) -> None:
        self.search_edit.setFocus()
        self.search_edit.selectAll()

    # =================================================================== refresh
    def refresh_all(self) -> None:
        if self._closing:
            return
        if not self.entries:
            self._update_empty_state()
            return
        self._scan_generation += 1
        generation = self._scan_generation
        self._scan_pending = {entry.id for entry in self.entries}
        self._scan_total = len(self.entries)
        self._scan_done = 0
        self._refresh_active = True
        # Keep strong references to running QRunnables.  Without them PySide
        # can garbage-collect the worker's signal object before the queued
        # signal is delivered, leaving the refresh stuck at N-1 repos.
        self._scan_workers = []

        self.model.set_loading({entry.id for entry in self.entries})
        self.refresh_button.setEnabled(False)
        self.refresh_button.setText("刷新中…")
        self.scan_progress.setVisible(True)
        self.scan_progress.setRange(0, self._scan_total)
        self.scan_progress.setValue(0)
        self._update_scan_label()
        self._update_summary()
        self._update_empty_state()

        for entry in self.entries:
            worker = ScanRepoWorker(
                self.service,
                entry,
                fetch=self.settings.fetch_on_refresh,
            )
            worker.signals.result.connect(
                lambda repo_id, status, gen=generation: self._on_scan_result(
                    gen, repo_id, status
                )
            )
            self._scan_workers.append(worker)
            self.pool.start(worker)

    def _on_scan_result(
        self, generation: int, repo_id: str, status: RepoStatus
    ) -> None:
        if self._closing or generation != self._scan_generation:
            return
        self._scan_pending.discard(repo_id)
        self._scan_done = self._scan_total - len(self._scan_pending)
        self.model.update_status(status)
        if self.search_edit.text().strip():
            self.proxy.invalidateFilter()
        self.scan_progress.setValue(self._scan_done)
        self._update_scan_label()
        self._update_summary()
        self._refresh_counts()

        if repo_id == self._selected_repo_id:
            self._update_detail_panel(self._selected_entry())
            self._ensure_commits()

        if not self._scan_pending:
            self._finish_scan()

    def _finish_scan(self) -> None:
        self._refresh_active = False
        self._last_refresh = datetime.now()
        self.refresh_button.setEnabled(True)
        self.refresh_button.setText("⟳  一键刷新")
        self.scan_progress.setVisible(False)
        self._update_scan_label()
        self._update_summary()
        self._update_empty_state()
        if self._selected_repo_id:
            self._update_detail_panel(self._selected_entry())
            self._ensure_commits()
        self._scan_workers.clear()

    def _update_scan_label(self) -> None:
        if self._refresh_active:
            self.scan_label.setText(f"正在刷新 {self._scan_done}/{self._scan_total} …")
            return
        if self._last_refresh:
            self.scan_label.setText(
                f"上次刷新 {self._last_refresh.strftime('%H:%M:%S')} · {len(self.entries)} 个仓库"
            )
        else:
            self.scan_label.setText("尚未刷新")

    def _on_fetch_toggled(self, checked: bool) -> None:
        self.settings.fetch_on_refresh = checked
        self._save_config()

    # ==================================================================== filters
    def _on_category_filter(self, button_id: int) -> None:
        category = ("", CATEGORY_PRIVATE, CATEGORY_SHARED)[button_id]
        self.proxy.set_category(category)
        self._ensure_selection()

    def _apply_search(self) -> None:
        self.proxy.set_query(self.search_edit.text())
        self._ensure_selection()

    def _ensure_selection(self) -> None:
        if self.proxy.rowCount() == 0:
            self._selected_repo_id = None
            self._update_detail_panel(None)
            return
        current = self.table.currentIndex()
        if current.isValid():
            return
        self.table.selectRow(0)
        index = self.proxy.index(0, 0)
        self.table.setCurrentIndex(index)

    def _ensure_selection_by_id(self, repo_id: str) -> None:
        for row in range(self.proxy.rowCount()):
            proxy_index = self.proxy.index(row, 0)
            if proxy_index.data(Roles.RepoId) == repo_id:
                self.table.setCurrentIndex(proxy_index)
                self.table.selectRow(row)
                return
        if self.proxy.rowCount():
            self.table.setCurrentIndex(self.proxy.index(0, 0))

    # ================================================================== selection
    def _on_current_changed(
        self, current: QModelIndex, _previous: QModelIndex
    ) -> None:
        entry = self._entry_from_proxy(current)
        if entry is None:
            self._selected_repo_id = None
            self._update_detail_panel(None)
            return
        self._selected_repo_id = entry.id
        self._update_detail_panel(entry)
        self._ensure_commits()

    def _entry_from_proxy(self, index: QModelIndex) -> RepoEntry | None:
        if not index.isValid():
            return None
        source = self.proxy.mapToSource(index)
        return self.model.entry_at(source.row())

    def _selected_entry(self) -> RepoEntry | None:
        if not self._selected_repo_id:
            return None
        for entry in self.entries:
            if entry.id == self._selected_repo_id:
                return entry
        return None

    # =============================================================== detail panel
    def _update_detail_panel(self, entry: RepoEntry | None) -> None:
        if entry is None:
            self._selected_repo_id = None
            self._commit_detail_request += 1
            self.detail_name.setText("未选择仓库")
            self.detail_category.setVisible(False)
            self.detail_sync.setVisible(False)
            self.detail_path.setText("")
            self.detail_note.setText("")
            self.open_button.setEnabled(False)
            self.commit_branch_label.setText("提交记录")
            self.commit_hint.setText("选择仓库后加载当前分支提交")
            self.commit_table.setRowCount(0)
            self._clear_commit_detail("选择一条提交后，可查看变更文件和完整补丁。")
            self.worktree_title.setText("工作区变更")
            self.worktree_hint.setText("")
            self.worktree_table.setRowCount(0)
            self.tabs.setTabText(1, "工作区变更")
            return

        self.detail_name.setText(entry.name)
        self.detail_category.setVisible(True)
        self._apply_chip(self.detail_category, category_badge(entry.category))
        self.detail_path.setText(entry.path)
        self.detail_path.setToolTip(entry.path)
        self.open_button.setEnabled(True)

        status = self.model.status_for(entry.id)
        if status is None:
            self.detail_sync.setVisible(False)
            self.detail_note.setText("等待刷新仓库状态…")
            self._update_worktree_tab(None)
        elif not status.ok:
            self.detail_sync.setVisible(True)
            self._apply_chip(self.detail_sync, sync_badge(status))
            self.detail_note.setText(f"仓库不可用：{status.error}")
            self.detail_note.setStyleSheet("color: #b91c1c;")
            self._update_worktree_tab(status)
        else:
            self.detail_sync.setVisible(True)
            self._apply_chip(self.detail_sync, sync_badge(status))
            self.detail_note.setStyleSheet("")
            pieces = []
            if status.branch:
                branch = "分离 HEAD" if status.detached else status.branch
                pieces.append(f"分支 {branch}")
            if status.upstream:
                pieces.append(f"上游 {status.upstream}")
            elif status.compare_ref:
                pieces.append(f"对比 {status.compare_ref}")
            pieces.append(sync_summary(status))
            if status.remote_url:
                pieces.append(status.remote_url)
            if status.fetch_error:
                pieces.append("远程抓取失败，远程状态可能过期")
            self.detail_note.setText(" · ".join(item for item in pieces if item))
            self.detail_note.setToolTip(
                "\n".join(
                    item
                    for item in (
                        status.sync_note,
                        f"远程抓取失败：{status.fetch_error}" if status.fetch_error else "",
                    )
                    if item
                )
            )
            self._update_worktree_tab(status)

    def _apply_chip(self, label: QLabel, badge: Badge) -> None:
        label.setText(badge.text)
        label.setToolTip(badge.tooltip)
        label.setStyleSheet(
            "QLabel {"
            f"background: {badge.bg}; color: {badge.fg};"
            "border-radius: 10px; padding: 3px 10px;"
            "font-size: 11px; font-weight: 600;"
            "}"
        )

    def _update_worktree_tab(self, status: RepoStatus | None) -> None:
        table = self.worktree_table
        table.setUpdatesEnabled(False)
        table.setRowCount(0)
        try:
            if status is None:
                self.worktree_title.setText("工作区变更")
                self.worktree_hint.setText("刷新仓库后显示未提交变更")
                self.tabs.setTabText(1, "工作区变更")
                return
            if not status.ok:
                self.worktree_title.setText("工作区变更")
                self.worktree_hint.setText("无法读取仓库")
                self.tabs.setTabText(1, "工作区变更")
                return
            if not status.changes:
                self.worktree_title.setText("工作区变更")
                self.worktree_hint.setText("工作区干净，没有未提交变更")
                self.tabs.setTabText(1, "工作区变更")
                return

            self.worktree_title.setText(f"工作区变更 · {status.change_count}")
            self.worktree_hint.setText(
                f"已暂存 {status.staged_count} · 未暂存 {status.unstaged_count} · "
                f"未跟踪 {status.untracked_count} · 冲突 {status.conflict_count}"
            )
            self.tabs.setTabText(1, f"工作区变更 ({status.change_count})")
            table.setRowCount(len(status.changes))
            for row, change in enumerate(status.changes):
                state, staged, unstaged = working_change_labels(change)
                state_item = QTableWidgetItem(state)
                state_item.setForeground(QColor(self._state_color(state)))
                state_item.setToolTip(f"git status: {change.code}")
                staged_item = QTableWidgetItem(staged)
                staged_item.setForeground(QColor("#15803d" if staged == "✓" else "#94a3b8"))
                staged_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                unstaged_item = QTableWidgetItem(unstaged)
                unstaged_item.setForeground(
                    QColor("#d97706" if unstaged == "✓" else "#94a3b8")
                )
                unstaged_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                path_item = QTableWidgetItem(change.display_path)
                path_item.setToolTip(change.display_path)
                table.setItem(row, 0, state_item)
                table.setItem(row, 1, staged_item)
                table.setItem(row, 2, unstaged_item)
                table.setItem(row, 3, path_item)
        finally:
            table.setUpdatesEnabled(True)

    @staticmethod
    def _state_color(state: str) -> str:
        if "冲突" in state:
            return "#b91c1c"
        if "删除" in state:
            return "#dc2626"
        if "新增" in state:
            return "#15803d"
        if "未跟踪" in state:
            return "#7c3aed"
        if "重命名" in state or "复制" in state:
            return "#7c3aed"
        return "#b45309"

    # ==================================================================== commits
    def _ensure_commits(self) -> None:
        if self._closing:
            return
        entry = self._selected_entry()
        if entry is None:
            return
        status = self.model.status_for(entry.id)
        if status is None:
            if self._refresh_active:
                self.commit_hint.setText("仓库刷新中，完成后加载提交")
            return
        if not status.ok:
            self.commit_table.setRowCount(0)
            self._commits_repo_id = entry.id
            self._commits_head = None
            self._commit_detail_request += 1
            self.commit_branch_label.setText("提交记录")
            self.commit_hint.setText(f"读取失败：{status.error}")
            self._clear_commit_detail("仓库不可用，无法读取提交。")
            return
        if self._commits_repo_id != entry.id:
            self._commits_head = None
        branch_label = "分离 HEAD" if status.detached else status.branch
        if branch_label:
            self.commit_branch_label.setText(f"分支 {branch_label}")
        if (
            self._commits_repo_id == entry.id
            and self._commits_head == status.head_hash
            and self.commit_table.rowCount() > 0
        ):
            return
        self._load_commits()

    def _load_commits(self, force: bool = False) -> None:
        entry = self._selected_entry()
        if entry is None:
            return
        status = self.model.status_for(entry.id)
        if status is None or not status.ok:
            self.commit_hint.setText("等待仓库刷新完成后加载提交")
            return
        if (
            not force
            and self._commits_repo_id == entry.id
            and self._commits_head == status.head_hash
            and self.commit_table.rowCount() > 0
        ):
            return

        self._commit_list_request += 1
        request_id = self._commit_list_request
        self._commit_detail_request += 1
        self._commits_repo_id = entry.id
        self._commits_head = status.head_hash
        self.commit_table.setRowCount(0)
        self.commit_branch_label.setText("提交记录")
        self.commit_hint.setText("正在读取提交记录…")
        self._clear_commit_detail("正在读取提交记录…")

        worker = CommitListWorker(
            self.service,
            entry.id,
            entry.path,
            request_id,
            self.COMMIT_LIMIT,
        )
        worker.signals.loaded.connect(self._on_commits_loaded)
        worker.signals.failed.connect(self._on_commits_failed)
        self._commit_workers = [worker]
        self.pool.start(worker)

    def _on_commits_loaded(
        self, repo_id: str, request_id: int, commits: list[CommitInfo]
    ) -> None:
        if request_id != self._commit_list_request:
            return
        if repo_id != self._selected_repo_id:
            return
        entry = self._selected_entry()
        if entry is None:
            return
        branch = "—"
        status = self.model.status_for(entry.id)
        if status:
            branch = "分离 HEAD" if status.detached else status.branch
        self.commit_branch_label.setText(f"分支 {branch}")
        self.commit_hint.setText(f"{len(commits)} 条提交")
        self.commit_table.setUpdatesEnabled(False)
        self.commit_table.blockSignals(True)
        try:
            self.commit_table.setRowCount(len(commits))
            mono = QFont("Cascadia Mono")
            mono.setStyleHint(QFont.StyleHint.Monospace)
            mono.setPointSize(8)
            for row, commit in enumerate(commits):
                date_item = QTableWidgetItem(commit.date_display)
                date_item.setForeground(QColor("#64748b"))
                date_item.setToolTip(commit.date)
                hash_item = QTableWidgetItem(commit.short_hash)
                hash_item.setFont(mono)
                hash_item.setForeground(QColor("#4338ca"))
                hash_item.setData(Qt.ItemDataRole.UserRole, commit.hash)
                hash_item.setToolTip(commit.hash)
                author_item = QTableWidgetItem(commit.author)
                author_item.setForeground(QColor("#475569"))
                author_item.setToolTip(commit.email)
                subject_item = QTableWidgetItem(commit.subject)
                if commit.refs:
                    subject_item.setToolTip(f"{commit.subject}\n\n{commit.refs}")
                self.commit_table.setItem(row, 0, date_item)
                self.commit_table.setItem(row, 1, hash_item)
                self.commit_table.setItem(row, 2, author_item)
                self.commit_table.setItem(row, 3, subject_item)
        finally:
            self.commit_table.blockSignals(False)
            self.commit_table.setUpdatesEnabled(True)

        if commits:
            self.commit_table.selectRow(0)
            self._on_commit_selection_changed()
        else:
            self._clear_commit_detail("这个仓库还没有提交记录。")
            self.commit_hint.setText("0 条提交")

    def _on_commits_failed(self, repo_id: str, request_id: int, message: str) -> None:
        if request_id != self._commit_list_request or repo_id != self._selected_repo_id:
            return
        self._commit_detail_request += 1
        self.commit_table.setRowCount(0)
        self.commit_branch_label.setText("提交记录")
        self.commit_hint.setText(f"读取失败：{message}")
        self._clear_commit_detail("无法读取提交记录。")

    def _on_commit_selection_changed(self) -> None:
        if self._closing:
            return
        row = self.commit_table.currentRow()
        if row < 0:
            return
        item = self.commit_table.item(row, 1)
        if item is None:
            return
        commit_hash = item.data(Qt.ItemDataRole.UserRole)
        if not commit_hash or not self._selected_repo_id:
            return

        key = (self._selected_repo_id, str(commit_hash))
        self._commit_detail_request += 1
        cached = self._commit_cache.get(key)
        if cached is not None:
            self._show_commit_detail(cached)
            return

        request_id = self._commit_detail_request
        self._clear_commit_detail("正在读取提交详情…")

        entry = self._selected_entry()
        if entry is None:
            return
        worker = CommitDetailWorker(
            self.service,
            entry.id,
            entry.path,
            request_id,
            str(commit_hash),
        )
        worker.signals.loaded.connect(self._on_commit_detail_loaded)
        worker.signals.failed.connect(self._on_commit_detail_failed)
        self._commit_detail_workers = [worker]
        self.pool.start(worker)

    def _on_commit_detail_loaded(
        self,
        repo_id: str,
        request_id: int,
        commit_hash: str,
        detail: CommitDetail,
    ) -> None:
        if request_id != self._commit_detail_request:
            return
        if repo_id != self._selected_repo_id:
            return
        self._commit_cache[(repo_id, commit_hash)] = detail
        if len(self._commit_cache) > self.COMMIT_CACHE_LIMIT:
            oldest = next(iter(self._commit_cache))
            self._commit_cache.pop(oldest, None)
        self._show_commit_detail(detail)

    def _on_commit_detail_failed(
        self, repo_id: str, request_id: int, _commit_hash: str, message: str
    ) -> None:
        if request_id != self._commit_detail_request or repo_id != self._selected_repo_id:
            return
        self._clear_commit_detail(f"读取提交详情失败：{message}")

    def _show_commit_detail(self, detail: CommitDetail) -> None:
        self.commit_subject.setText(detail.subject)
        merge_note = " · 合并提交" if len(detail.parents) > 1 else ""
        self.commit_meta.setText(
            f"{detail.author} <{detail.email}> · {detail.date_display} · "
            f"{detail.hash[:12]}{merge_note}"
        )
        self.message_view.setPlainText(detail.message.strip())

        files = self.commit_files
        files.setUpdatesEnabled(False)
        files.setRowCount(len(detail.files))
        try:
            for row, change in enumerate(detail.files):
                status_item = QTableWidgetItem(commit_file_label(change.status))
                status_item.setToolTip(change.status)
                status_item.setForeground(
                    QColor(self._commit_file_color(change.status[:1]))
                )
                path = (
                    f"{change.old_path} → {change.path}"
                    if change.old_path
                    else change.path
                )
                path_item = QTableWidgetItem(path)
                path_item.setToolTip(path)
                files.setItem(row, 0, status_item)
                files.setItem(row, 1, path_item)
        finally:
            files.setUpdatesEnabled(True)

        diff = detail.diff or "该提交没有文件变更。"
        self.diff_view.setPlainText(diff)
        self.commit_detail_stack.setCurrentIndex(1)

    @staticmethod
    def _commit_file_color(code: str) -> str:
        return {
            "A": "#15803d",
            "D": "#dc2626",
            "M": "#b45309",
            "R": "#7c3aed",
            "C": "#7c3aed",
            "U": "#b91c1c",
        }.get(code, "#64748b")

    def _clear_commit_detail(self, text: str) -> None:
        self.commit_subject.setText("提交详情")
        self.commit_meta.setText(text)
        self.commit_detail_stack.setCurrentIndex(0)
        self.commit_files.setRowCount(0)
        self.diff_view.clear()
        self.message_view.clear()

    # ==================================================================== actions
    def _add_repo(self) -> None:
        existing = {entry.path for entry in self.entries}
        default_category = CATEGORY_PRIVATE
        checked = self.category_group.checkedId()
        if checked == 2:
            default_category = CATEGORY_SHARED
        dialog = AddRepoDialog(self.service, existing, default_category, self)
        if dialog.exec() != AddRepoDialog.DialogCode.Accepted:
            return
        entry = dialog.result_entry
        if entry is None:
            return

        self.entries.append(entry)
        self._save_config()
        self.model.set_entries(self.entries)
        self.category_buttons[0].setChecked(True)
        self.proxy.set_category("")
        self.search_edit.clear()
        self.proxy.set_query("")
        self._refresh_counts()
        self._update_empty_state()
        self._ensure_selection_by_id(entry.id)
        self.refresh_all()

    def _edit_selected(self) -> None:
        entry = self._selected_entry()
        if entry is None:
            return
        dialog = EditRepoDialog(entry, self)
        if dialog.exec() != EditRepoDialog.DialogCode.Accepted:
            return
        updated = dialog.result_entry
        if updated is None:
            return
        for index, item in enumerate(self.entries):
            if item.id == entry.id:
                self.entries[index] = updated
                break
        self._save_config()
        self.model.set_entries(self.entries)
        self._refresh_counts()
        self._ensure_selection_by_id(updated.id)
        self._ensure_selection()
        self._update_detail_panel(self._selected_entry())

    def _remove_selected(self) -> None:
        entry = self._selected_entry()
        if entry is None:
            return
        answer = QMessageBox.question(
            self,
            "移除仓库",
            f"确定从 GitMan 中移除仓库 “{entry.name}” 吗？\n\n"
            "只会删除列表记录，不会删除或修改本地仓库文件。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return

        self.entries = [item for item in self.entries if item.id != entry.id]
        self.model.remove_status(entry.id)
        self._save_config()
        self.model.set_entries(self.entries)
        self._refresh_counts()
        self._update_empty_state()
        if self.entries:
            self._ensure_selection_by_id(self.entries[0].id)
            self._ensure_selection()
        else:
            self._selected_repo_id = None
            self._update_detail_panel(None)

    def _open_selected_folder(self) -> None:
        entry = self._selected_entry()
        if entry is None:
            return
        path = Path(entry.path)
        if not path.exists():
            QMessageBox.warning(self, "路径不存在", f"找不到文件夹：\n{entry.path}")
            return
        if not QDesktopServices.openUrl(QUrl.fromLocalFile(str(path))):
            QMessageBox.warning(self, "无法打开", f"系统无法打开文件夹：\n{entry.path}")

    def _show_context_menu(self, position: QPoint) -> None:
        index = self.table.indexAt(position)
        if not index.isValid():
            return
        self.table.setCurrentIndex(index)
        self.table.selectRow(index.row())
        entry = self._entry_from_proxy(index)
        if entry is None:
            return

        menu = QMenu(self.table)
        open_action = menu.addAction("打开文件夹")
        copy_action = menu.addAction("复制路径")
        menu.addSeparator()
        edit_action = menu.addAction("编辑名称 / 分类")
        menu.addSeparator()
        remove_action = menu.addAction("从列表移除")

        chosen = menu.exec(self.table.viewport().mapToGlobal(position))
        if chosen == open_action:
            self._open_selected_folder()
        elif chosen == copy_action:
            QApplication.clipboard().setText(entry.path)
        elif chosen == edit_action:
            self._edit_selected()
        elif chosen == remove_action:
            self._remove_selected()

    # ==================================================================== summary
    def _refresh_counts(self) -> None:
        total = len(self.entries)
        private_count = sum(1 for entry in self.entries if entry.category == CATEGORY_PRIVATE)
        shared_count = sum(1 for entry in self.entries if entry.category == CATEGORY_SHARED)
        self.category_buttons[0].setText(f"全部 {total}")
        self.category_buttons[1].setText(f"私有 {private_count}")
        self.category_buttons[2].setText(f"共享 {shared_count}")
        self._update_summary()

    def _update_summary(self) -> None:
        statuses = [self.model.status_for(entry.id) for entry in self.entries]
        known = [status for status in statuses if status is not None]
        dirty = sum(1 for status in known if status.ok and status.dirty)
        ahead = sum(
            1
            for status in known
            if status.ok and status.sync_state in {"local_ahead", "diverged"}
        )
        behind = sum(
            1
            for status in known
            if status.ok and status.sync_state in {"remote_ahead", "diverged"}
        )
        errors = sum(1 for status in known if not status.ok)
        fetch_errors = sum(1 for status in known if status.ok and status.fetch_error)

        if self._refresh_active:
            self.summary_label.setText(
                f"已扫描 {self._scan_done}/{self._scan_total} · "
                f"{dirty} 个有本地变更 · {behind} 个有远程更新"
            )
            return

        parts = [f"{len(self.entries)} 个仓库"]
        if dirty:
            parts.append(f"{dirty} 个有本地变更")
        if behind:
            parts.append(f"{behind} 个有远程更新")
        if ahead:
            parts.append(f"{ahead} 个本地领先")
        if errors:
            parts.append(f"{errors} 个异常")
        if fetch_errors:
            parts.append(f"{fetch_errors} 个抓取失败")
        if len(known) < len(self.entries):
            parts.append(f"{len(self.entries) - len(known)} 个待刷新")
        self.summary_label.setText(" · ".join(parts))

    def _update_empty_state(self) -> None:
        has_entries = bool(self.entries)
        self.repo_stack.setCurrentIndex(0 if has_entries else 1)
        self.detail_panel.setVisible(has_entries)
        self.refresh_button.setEnabled(has_entries and not self._refresh_active)
        self.selected_hint.setVisible(has_entries)

    # ================================================================= persistence
    def _save_config(self) -> None:
        try:
            self.store.save(AppConfig(repos=self.entries, settings=self.settings))
        except OSError as exc:
            LOGGER.exception("Could not save configuration")
            self.scan_label.setText(f"配置保存失败：{exc}")

    def _settings(self) -> QSettings:
        return QSettings("GitMan", "GitMan")

    def _restore_window_state(self) -> None:
        settings = self._settings()
        geometry = settings.value("window/geometry")
        if geometry:
            self.restoreGeometry(geometry)
        else:
            screen = QApplication.primaryScreen()
            if screen:
                available = screen.availableGeometry()
                self.move(
                    available.center().x() - self.width() // 2,
                    available.center().y() - self.height() // 2,
                )

        main_state = settings.value("window/main_splitter")
        if main_state:
            self.main_splitter.restoreState(main_state)
        commit_state = settings.value("window/commit_splitter")
        if commit_state:
            self.commit_splitter.restoreState(commit_state)
        header_state = settings.value("window/table_header")
        if header_state:
            self.table.horizontalHeader().restoreState(header_state)

    def _save_window_state(self) -> None:
        settings = self._settings()
        settings.setValue("window/geometry", self.saveGeometry())
        settings.setValue("window/main_splitter", self.main_splitter.saveState())
        settings.setValue("window/commit_splitter", self.commit_splitter.saveState())
        settings.setValue("window/table_header", self.table.horizontalHeader().saveState())
        settings.sync()

    def closeEvent(self, event) -> None:
        self._closing = True
        self._save_config()
        self._save_window_state()
        self.pool.clear()
        self.pool.waitForDone(1200)
        super().closeEvent(event)
