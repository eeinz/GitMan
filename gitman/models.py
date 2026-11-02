"""Domain models used by the GitMan application."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


CATEGORY_PRIVATE = "private"
CATEGORY_SHARED = "shared"
CATEGORY_LABELS = {
    CATEGORY_PRIVATE: "私有",
    CATEGORY_SHARED: "共享",
}

SYNC_SYNCED = "synced"
SYNC_LOCAL_AHEAD = "local_ahead"
SYNC_REMOTE_AHEAD = "remote_ahead"
SYNC_DIVERGED = "diverged"
SYNC_NO_UPSTREAM = "no_upstream"
SYNC_DETACHED = "detached"
SYNC_UNKNOWN = "unknown"


@dataclass(slots=True)
class RepoEntry:
    """A repository configured by the user."""

    id: str
    name: str
    path: str
    category: str = CATEGORY_PRIVATE

    def to_dict(self) -> dict[str, str]:
        return {
            "id": self.id,
            "name": self.name,
            "path": self.path,
            "category": self.category,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RepoEntry":
        repo_id = data.get("id")
        raw_path = data.get("path")
        if not repo_id or not isinstance(raw_path, str) or not raw_path.strip():
            raise ValueError("仓库记录缺少 id 或 path")
        category = str(data.get("category", CATEGORY_PRIVATE))
        if category not in CATEGORY_LABELS:
            category = CATEGORY_PRIVATE
        return cls(
            id=str(repo_id),
            name=str(data.get("name") or ""),
            path=raw_path,
            category=category,
        )


@dataclass(slots=True)
class AppSettings:
    fetch_on_refresh: bool = True

    def to_dict(self) -> dict[str, bool]:
        return {"fetch_on_refresh": self.fetch_on_refresh}

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "AppSettings":
        if not isinstance(data, dict):
            data = {}
        return cls(fetch_on_refresh=bool(data.get("fetch_on_refresh", True)))


@dataclass(slots=True)
class AppConfig:
    repos: list[RepoEntry] = field(default_factory=list)
    settings: AppSettings = field(default_factory=AppSettings)


@dataclass(slots=True)
class CommitInfo:
    hash: str
    short_hash: str
    author: str
    email: str
    date: str
    subject: str
    refs: str = ""

    @property
    def date_display(self) -> str:
        return format_git_date(self.date)


@dataclass(slots=True)
class CommitFileChange:
    status: str
    path: str
    old_path: str = ""


@dataclass(slots=True)
class CommitDetail:
    hash: str
    author: str
    email: str
    date: str
    parents: list[str]
    message: str
    files: list[CommitFileChange]
    diff: str
    diff_truncated: bool = False

    @property
    def subject(self) -> str:
        return self.message.strip().splitlines()[0] if self.message.strip() else "（无提交说明）"

    @property
    def date_display(self) -> str:
        return format_git_date(self.date)


@dataclass(slots=True)
class WorkingChange:
    """One entry from ``git status --porcelain=v1``."""

    x: str
    y: str
    path: str
    orig_path: str = ""

    @property
    def code(self) -> str:
        return f"{self.x}{self.y}"

    @property
    def is_untracked(self) -> bool:
        return self.x == "?" and self.y == "?"

    @property
    def is_conflicted(self) -> bool:
        return self.code in {"DD", "AU", "UD", "UA", "DU", "AA", "UU"} or "U" in self.code

    @property
    def is_staged(self) -> bool:
        return not self.is_untracked and not self.is_conflicted and self.x not in {" ", "?"}

    @property
    def is_unstaged(self) -> bool:
        return not self.is_untracked and not self.is_conflicted and self.y not in {" ", "?"}

    @property
    def display_path(self) -> str:
        if self.orig_path:
            return f"{self.orig_path} → {self.path}"
        return self.path


@dataclass(slots=True)
class RepoStatus:
    repo_id: str
    path: str
    ok: bool = False
    error: str = ""
    root: str = ""
    branch: str = ""
    detached: bool = False
    head_hash: str = ""
    upstream: str = ""
    compare_ref: str = ""
    has_upstream: bool = False
    ahead: int = 0
    behind: int = 0
    sync_state: str = SYNC_UNKNOWN
    sync_note: str = ""
    remotes: list[str] = field(default_factory=list)
    remote_url: str = ""
    fetch_performed: bool = False
    fetch_error: str = ""
    changes: list[WorkingChange] = field(default_factory=list)
    last_commit: CommitInfo | None = None
    scanned_at: datetime = field(default_factory=datetime.now)
    duration_ms: int = 0

    @property
    def staged_count(self) -> int:
        return sum(1 for change in self.changes if change.is_staged)

    @property
    def unstaged_count(self) -> int:
        return sum(1 for change in self.changes if change.is_unstaged)

    @property
    def untracked_count(self) -> int:
        return sum(1 for change in self.changes if change.is_untracked)

    @property
    def conflict_count(self) -> int:
        return sum(1 for change in self.changes if change.is_conflicted)

    @property
    def change_count(self) -> int:
        return len(self.changes)

    @property
    def dirty(self) -> bool:
        return bool(self.changes)


def format_git_date(value: str) -> str:
    """Convert an ISO-8601 git date into a compact local timestamp."""

    if not value:
        return ""
    text = value.strip()
    try:
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        parsed = datetime.fromisoformat(text)
        return parsed.astimezone().strftime("%Y-%m-%d %H:%M")
    except (ValueError, OSError):
        return value[:19].replace("T", " ")
