"""Background workers for git operations."""

from __future__ import annotations

import logging

from PySide6.QtCore import QObject, QRunnable, Signal, Slot

from .git_service import GitService, GitServiceError
from .models import RepoEntry, RepoStatus


LOGGER = logging.getLogger(__name__)


class ScanSignals(QObject):
    result = Signal(str, object)  # repo id, RepoStatus


class ScanRepoWorker(QRunnable):
    def __init__(self, service: GitService, entry: RepoEntry, fetch: bool):
        super().__init__()
        self.service = service
        self.entry = entry
        self.fetch = fetch
        self.signals = ScanSignals()
        self.setAutoDelete(True)

    @Slot()
    def run(self) -> None:
        try:
            status = self.service.inspect_repo(self.entry, fetch=self.fetch)
        except Exception as exc:  # never let a worker die silently
            LOGGER.exception("Repository scan failed for %s", self.entry.path)
            status = RepoStatus(
                repo_id=self.entry.id,
                path=self.entry.path,
                ok=False,
                error=f"读取仓库失败：{exc}",
            )
        try:
            self.signals.result.emit(self.entry.id, status)
        except RuntimeError:
            # The owning window has already been destroyed.
            pass


class CommitListSignals(QObject):
    loaded = Signal(str, int, object)  # repo id, request id, list[CommitInfo]
    failed = Signal(str, int, str)


class CommitListWorker(QRunnable):
    def __init__(
        self,
        service: GitService,
        repo_id: str,
        path: str,
        request_id: int,
        limit: int = 200,
    ):
        super().__init__()
        self.service = service
        self.repo_id = repo_id
        self.path = path
        self.request_id = request_id
        self.limit = limit
        self.signals = CommitListSignals()
        self.setAutoDelete(True)

    @Slot()
    def run(self) -> None:
        try:
            commits = self.service.list_commits(self.path, self.limit)
        except Exception as exc:
            LOGGER.warning("Loading commits failed for %s: %s", self.path, exc)
            self._emit_failure(str(exc))
            return
        try:
            self.signals.loaded.emit(self.repo_id, self.request_id, commits)
        except RuntimeError:
            pass

    def _emit_failure(self, message: str) -> None:
        try:
            self.signals.failed.emit(self.repo_id, self.request_id, message)
        except RuntimeError:
            pass


class CommitDetailSignals(QObject):
    loaded = Signal(str, int, str, object)  # repo id, request id, hash, CommitDetail
    failed = Signal(str, int, str, str)


class CommitDetailWorker(QRunnable):
    def __init__(
        self,
        service: GitService,
        repo_id: str,
        path: str,
        request_id: int,
        commit_hash: str,
    ):
        super().__init__()
        self.service = service
        self.repo_id = repo_id
        self.path = path
        self.request_id = request_id
        self.commit_hash = commit_hash
        self.signals = CommitDetailSignals()
        self.setAutoDelete(True)

    @Slot()
    def run(self) -> None:
        try:
            detail = self.service.commit_detail(self.path, self.commit_hash)
        except GitServiceError as exc:
            self._emit_failure(str(exc))
            return
        except Exception as exc:
            LOGGER.exception("Loading commit detail failed")
            self._emit_failure(f"读取提交详情失败：{exc}")
            return
        try:
            self.signals.loaded.emit(
                self.repo_id, self.request_id, self.commit_hash, detail
            )
        except RuntimeError:
            pass

    def _emit_failure(self, message: str) -> None:
        try:
            self.signals.failed.emit(
                self.repo_id, self.request_id, self.commit_hash, message
            )
        except RuntimeError:
            pass
