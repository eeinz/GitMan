"""Presentation helpers shared by the UI widgets."""

from __future__ import annotations

from dataclasses import dataclass

from ..models import (
    CATEGORY_LABELS,
    CATEGORY_PRIVATE,
    RepoStatus,
    SYNC_DETACHED,
    SYNC_DIVERGED,
    SYNC_LOCAL_AHEAD,
    SYNC_NO_UPSTREAM,
    SYNC_REMOTE_AHEAD,
    SYNC_SYNCED,
    SYNC_UNKNOWN,
)


@dataclass(frozen=True, slots=True)
class Badge:
    text: str
    fg: str
    bg: str
    tooltip: str = ""


GRAY_FG = "#64748b"
GRAY_BG = "#f1f5f9"
GREEN_FG = "#15803d"
GREEN_BG = "#e9f8ef"
AMBER_FG = "#b45309"
AMBER_BG = "#fff5e6"
BLUE_FG = "#1d4ed8"
BLUE_BG = "#eaf1ff"
RED_FG = "#b91c1c"
RED_BG = "#feecec"
PURPLE_FG = "#6d28d9"
PURPLE_BG = "#f2ecff"
TEAL_FG = "#0f766e"
TEAL_BG = "#e6fbf8"


def category_badge(category: str) -> Badge:
    if category == CATEGORY_PRIVATE:
        return Badge(CATEGORY_LABELS[CATEGORY_PRIVATE], PURPLE_FG, PURPLE_BG)
    return Badge(CATEGORY_LABELS.get(category, category), TEAL_FG, TEAL_BG)


def worktree_badge(status: RepoStatus | None, loading: bool = False) -> Badge:
    if loading:
        return Badge("刷新中", BLUE_FG, BLUE_BG, "正在读取仓库状态…")
    if status is None:
        return Badge("待刷新", GRAY_FG, GRAY_BG, "按 F5 或点击“一键刷新”")
    if not status.ok:
        return Badge("不可用", RED_FG, RED_BG, status.error or "无法读取仓库")
    if status.conflict_count:
        detail = _change_detail(status)
        return Badge(
            f"冲突 {status.conflict_count}",
            RED_FG,
            RED_BG,
            detail,
        )
    if status.dirty:
        return Badge(
            f"{status.change_count} 项变更",
            AMBER_FG,
            AMBER_BG,
            _change_detail(status),
        )
    return Badge("干净", GREEN_FG, GREEN_BG, "工作区没有未提交变更")


def sync_badge(status: RepoStatus | None, loading: bool = False) -> Badge:
    if loading:
        return Badge("检查中", BLUE_FG, BLUE_BG, "正在比较本地与远程…")
    if status is None:
        return Badge("待刷新", GRAY_FG, GRAY_BG)
    if not status.ok:
        return Badge("错误", RED_FG, RED_BG, status.error)

    notes: list[str] = []
    if status.has_upstream:
        notes.append(f"上游分支：{status.upstream}")
    elif status.compare_ref:
        notes.append(f"未设置上游，与 {status.compare_ref} 比较")
    if status.sync_note:
        notes.append(status.sync_note)
    if status.ahead or status.behind:
        notes.append(f"本地领先 {status.ahead} 个提交，远程领先 {status.behind} 个提交")
    if status.fetch_performed:
        notes.append("刷新时已执行 git fetch")
    if status.fetch_error:
        notes.append(f"远程抓取失败：{status.fetch_error}（远程数据可能不是最新）")
    tooltip = "\n".join(dict.fromkeys(notes))

    if status.sync_state == SYNC_SYNCED:
        return Badge("已同步", GREEN_FG, GREEN_BG, tooltip or "本地与远程一致")
    if status.sync_state == SYNC_LOCAL_AHEAD:
        return Badge(f"本地新 {status.ahead}", AMBER_FG, AMBER_BG, tooltip)
    if status.sync_state == SYNC_REMOTE_AHEAD:
        return Badge(f"远程新 {status.behind}", BLUE_FG, BLUE_BG, tooltip)
    if status.sync_state == SYNC_DIVERGED:
        return Badge(
            f"已分叉 +{status.ahead}/-{status.behind}",
            RED_FG,
            RED_BG,
            tooltip,
        )
    if status.sync_state == SYNC_NO_UPSTREAM:
        return Badge("仅本地", GRAY_FG, GRAY_BG, tooltip or "未关联远程分支")
    if status.sync_state == SYNC_DETACHED:
        return Badge("分离 HEAD", PURPLE_FG, PURPLE_BG, tooltip or "当前没有位于分支上")
    if status.sync_state == SYNC_UNKNOWN:
        return Badge("无法比较", GRAY_FG, GRAY_BG, tooltip)
    return Badge("—", GRAY_FG, GRAY_BG, tooltip)


def _change_detail(status: RepoStatus) -> str:
    lines = [
        f"共 {status.change_count} 项变更",
        f"已暂存 {status.staged_count} · 未暂存 {status.unstaged_count} · "
        f"未跟踪 {status.untracked_count} · 冲突 {status.conflict_count}",
    ]
    if status.last_commit:
        lines.append(f"最近提交：{status.last_commit.short_hash} {status.last_commit.subject}")
    return "\n".join(lines)


def branch_text(status: RepoStatus | None, loading: bool = False) -> str:
    if loading:
        return "读取中…"
    if status is None:
        return "—"
    if not status.ok:
        return "—"
    if status.detached:
        return "分离 HEAD"
    return status.branch or "—"


def branch_tooltip(status: RepoStatus | None) -> str:
    if not status:
        return ""
    lines: list[str] = []
    if status.branch:
        lines.append(f"当前分支：{status.branch}")
    if status.head_hash:
        lines.append(f"HEAD：{status.head_hash[:12]}")
    if status.has_upstream:
        lines.append(f"上游：{status.upstream}")
    elif status.compare_ref:
        lines.append(f"对比分支：{status.compare_ref}（未设置上游）")
    if status.duration_ms:
        lines.append(f"扫描耗时：{status.duration_ms} ms")
    return "\n".join(lines)


def sync_summary(status: RepoStatus | None) -> str:
    if not status or not status.ok:
        return ""
    if status.sync_state == SYNC_SYNCED:
        return "本地与远程一致"
    if status.sync_state == SYNC_LOCAL_AHEAD:
        return f"本地领先远程 {status.ahead} 个提交"
    if status.sync_state == SYNC_REMOTE_AHEAD:
        return f"远程领先本地 {status.behind} 个提交"
    if status.sync_state == SYNC_DIVERGED:
        return f"本地领先 {status.ahead}，远程领先 {status.behind}"
    if status.sync_state == SYNC_NO_UPSTREAM:
        return "本地分支未关联远程"
    if status.sync_state == SYNC_DETACHED:
        return "分离 HEAD"
    return "无法比较"


def working_change_labels(change) -> tuple[str, str, str]:
    """Return (state, staged, unstaged) labels for a WorkingChange."""

    if change.is_untracked:
        return "未跟踪", "—", "✓"
    if change.is_conflicted:
        return "冲突", "—", "—"

    x_label = _code_label(change.x)
    y_label = _code_label(change.y)
    labels = [label for label in (x_label, y_label) if label]
    state = " / ".join(dict.fromkeys(labels)) or "变更"
    staged = "✓" if change.is_staged else "—"
    unstaged = "✓" if change.is_unstaged else "—"
    return state, staged, unstaged


def _code_label(code: str) -> str:
    return {
        "A": "新增",
        "C": "复制",
        "D": "删除",
        "M": "修改",
        "R": "重命名",
        "T": "类型变更",
        "U": "冲突",
    }.get(code, "")


def commit_file_label(status: str) -> str:
    code = status[:1]
    return {
        "A": "新增",
        "C": "复制",
        "D": "删除",
        "M": "修改",
        "R": "重命名",
        "T": "类型变更",
        "U": "冲突",
    }.get(code, status or "变更")
