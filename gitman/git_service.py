"""Thin, read-only wrapper around the git command line."""

from __future__ import annotations

import logging
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

from .models import (
    CommitDetail,
    CommitFileChange,
    CommitInfo,
    RepoEntry,
    RepoStatus,
    SYNC_DETACHED,
    SYNC_DIVERGED,
    SYNC_LOCAL_AHEAD,
    SYNC_NO_UPSTREAM,
    SYNC_REMOTE_AHEAD,
    SYNC_SYNCED,
    SYNC_UNKNOWN,
    WorkingChange,
)


LOGGER = logging.getLogger(__name__)
HASH_RE = re.compile(r"^[0-9a-fA-F]{4,64}$")


class GitServiceError(RuntimeError):
    pass


@dataclass(slots=True)
class GitResult:
    returncode: int
    stdout: str = ""
    stderr: str = ""

    @property
    def ok(self) -> bool:
        return self.returncode == 0


class GitService:
    """All git operations used by the UI.

    The service never changes tracked content.  The only write operation is an
    optional ``git fetch`` during refresh, which updates remote-tracking refs.
    """

    def __init__(self, git_executable: str = "git"):
        self.git_executable = git_executable

    # ------------------------------------------------------------------ command
    def run(
        self,
        repository: str | Path,
        arguments: list[str],
        *,
        timeout: float = 20.0,
    ) -> GitResult:
        command = [
            self.git_executable,
            "-c",
            "core.quotepath=false",
            "-c",
            "color.ui=false",
            "-C",
            str(repository),
            *arguments,
        ]
        env = os.environ.copy()
        env.update(
            {
                "GIT_PAGER": "cat",
                "PAGER": "cat",
                "GIT_TERMINAL_PROMPT": "0",
                "GCM_INTERACTIVE": "never",
            }
        )
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if sys.platform == "win32" else 0
        try:
            completed = subprocess.run(
                command,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
                env=env,
                creationflags=creationflags,
                check=False,
            )
        except FileNotFoundError as exc:
            raise GitServiceError("未找到 git 命令，请安装 Git 并加入 PATH。") from exc
        except subprocess.TimeoutExpired:
            return GitResult(124, "", f"命令执行超时（{int(timeout)} 秒）")
        except OSError as exc:
            raise GitServiceError(f"无法启动 git：{exc}") from exc

        return GitResult(
            returncode=completed.returncode,
            stdout=completed.stdout or "",
            stderr=(completed.stderr or "").strip(),
        )

    # ------------------------------------------------------------------- probe
    def probe_repository(self, path: str | Path) -> Path:
        candidate = Path(os.path.expandvars(os.path.expanduser(str(path))))
        try:
            candidate = candidate.resolve()
        except OSError:
            candidate = candidate.absolute()

        if not candidate.exists():
            raise GitServiceError("文件夹不存在")
        if not candidate.is_dir():
            raise GitServiceError("路径不是文件夹")

        result = self.run(candidate, ["rev-parse", "--show-toplevel"], timeout=10)
        if not result.ok:
            detail = result.stderr.splitlines()[-1] if result.stderr else "不是有效的 Git 仓库"
            raise GitServiceError(detail)

        root_text = result.stdout.strip().splitlines()[0] if result.stdout.strip() else ""
        if not root_text:
            raise GitServiceError("无法确定 Git 仓库根目录")
        root = Path(root_text)
        return root.resolve() if root.exists() else root

    # ------------------------------------------------------------------ status
    def inspect_repo(self, entry: RepoEntry, fetch: bool = True) -> RepoStatus:
        started = time.perf_counter()
        status = RepoStatus(repo_id=entry.id, path=entry.path)

        try:
            root = self.probe_repository(entry.path)
            status.root = str(root)

            remotes = self._remotes(root)
            status.remotes = remotes
            status.remote_url = self._remote_url(root, remotes)

            if fetch and remotes:
                fetch_result = self.run(
                    root,
                    [
                        "fetch",
                        "--all",
                        "--prune",
                        "--quiet",
                        "--no-recurse-submodules",
                    ],
                    timeout=30,
                )
                status.fetch_performed = fetch_result.ok
                if not fetch_result.ok:
                    status.fetch_error = (
                        fetch_result.stderr or "git fetch 执行失败"
                    ).splitlines()[-1]

            branch_result = self.run(root, ["symbolic-ref", "--short", "-q", "HEAD"])
            if branch_result.ok and branch_result.stdout.strip():
                status.branch = branch_result.stdout.strip()
            else:
                short_result = self.run(root, ["rev-parse", "--short", "HEAD"])
                status.detached = True
                if short_result.ok:
                    status.head_hash = short_result.stdout.strip()
                    status.branch = f"HEAD@{status.head_hash}"
                else:
                    status.branch = "HEAD"

            head_result = self.run(root, ["rev-parse", "--verify", "HEAD"])
            has_head = head_result.ok
            if has_head:
                status.head_hash = head_result.stdout.strip()

            compare_ref = ""
            upstream_result = self.run(
                root,
                ["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"],
            )
            if upstream_result.ok and upstream_result.stdout.strip():
                status.has_upstream = True
                status.upstream = upstream_result.stdout.strip()
                compare_ref = status.upstream
                upstream_remote = status.upstream.split("/", 1)[0]
                if upstream_remote in remotes:
                    status.remote_url = self._remote_url(root, [upstream_remote])
            elif status.branch and not status.detached:
                compare_ref = self._find_remote_branch(root, status.branch, remotes)

            status.compare_ref = compare_ref
            if status.detached:
                status.sync_state = SYNC_DETACHED
                status.sync_note = "当前处于分离 HEAD 状态"
            elif not compare_ref:
                status.sync_state = SYNC_NO_UPSTREAM
                status.sync_note = "本地分支未关联远程分支"
            elif not has_head:
                status.sync_state = SYNC_UNKNOWN
                status.sync_note = "仓库还没有提交，无法比较"
            else:
                counts = self.run(
                    root,
                    ["rev-list", "--left-right", "--count", f"HEAD...{compare_ref}"],
                )
                if counts.ok:
                    parts = counts.stdout.split()
                    if len(parts) >= 2:
                        status.ahead = int(parts[0])
                        status.behind = int(parts[1])
                        status.sync_state = self._sync_state(status.ahead, status.behind)
                else:
                    status.sync_state = SYNC_UNKNOWN
                    status.sync_note = "无法比较本地与远程提交"

                if not status.has_upstream:
                    status.sync_note = f"未设置上游分支，正在与 {compare_ref} 比较"

            status.changes = self._working_changes(root)
            status.last_commit = self._last_commit(root)
            status.ok = True
        except GitServiceError as exc:
            status.error = str(exc)
        except Exception as exc:  # defensive: a broken repo must not stop a refresh
            LOGGER.exception("Unexpected error while inspecting %s", entry.path)
            status.error = f"读取仓库失败：{exc}"

        status.duration_ms = int((time.perf_counter() - started) * 1000)
        return status

    def _remotes(self, root: Path) -> list[str]:
        result = self.run(root, ["remote"])
        if not result.ok:
            return []
        return [line.strip() for line in result.stdout.splitlines() if line.strip()]

    def _remote_url(self, root: Path, remotes: list[str]) -> str:
        if not remotes:
            return ""
        remote = "origin" if "origin" in remotes else remotes[0]
        result = self.run(root, ["remote", "get-url", remote])
        if not result.ok:
            return ""
        return mask_remote_url(result.stdout.strip())

    def _find_remote_branch(
        self, root: Path, branch: str, remotes: list[str]
    ) -> str:
        if not branch or not remotes:
            return ""
        result = self.run(
            root,
            ["for-each-ref", "--format=%(refname:short)", "refs/remotes"],
        )
        if not result.ok:
            return ""
        refs = {line.strip() for line in result.stdout.splitlines() if line.strip()}
        ordered = sorted(remotes, key=lambda item: (item != "origin", item.lower()))
        for remote in ordered:
            candidate = f"{remote}/{branch}"
            if candidate in refs:
                return candidate
        return ""

    @staticmethod
    def _sync_state(ahead: int, behind: int) -> str:
        if ahead and behind:
            return SYNC_DIVERGED
        if ahead:
            return SYNC_LOCAL_AHEAD
        if behind:
            return SYNC_REMOTE_AHEAD
        return SYNC_SYNCED

    def _working_changes(self, root: Path) -> list[WorkingChange]:
        result = self.run(
            root,
            ["status", "--porcelain=v1", "-z", "--untracked-files=normal"],
        )
        if not result.ok:
            raise GitServiceError(result.stderr or "无法读取工作区状态")

        tokens = result.stdout.split("\0")
        changes: list[WorkingChange] = []
        index = 0
        while index < len(tokens):
            token = tokens[index]
            index += 1
            if not token or len(token) < 4:
                continue
            x, y, path = token[0], token[1], token[3:]
            orig_path = ""
            if x in {"R", "C"} or y in {"R", "C"}:
                if index < len(tokens):
                    orig_path = tokens[index]
                    index += 1
            changes.append(WorkingChange(x=x, y=y, path=path, orig_path=orig_path))
        return changes

    def _last_commit(self, root: Path) -> CommitInfo | None:
        result = self.run(
            root,
            [
                "log",
                "-1",
                "--no-show-signature",
                "--date=iso-strict",
                "--pretty=format:%H%x1f%h%x1f%an%x1f%ae%x1f%aI%x1f%s%x1f%D",
            ],
        )
        if not result.ok:
            return None
        return self._parse_commit_line(result.stdout.strip())

    # ----------------------------------------------------------------- commits
    def list_commits(self, path: str | Path, limit: int = 200) -> list[CommitInfo]:
        root = self.probe_repository(path)
        limit = max(1, min(int(limit), 1000))
        head = self.run(root, ["rev-parse", "--verify", "HEAD"])
        if not head.ok:
            return []

        result = self.run(
            root,
            [
                "log",
                f"-n{limit}",
                "--no-show-signature",
                "--date=iso-strict",
                "--pretty=format:%H%x1f%h%x1f%an%x1f%ae%x1f%aI%x1f%s%x1f%D",
                "HEAD",
            ],
        )
        if not result.ok:
            raise GitServiceError(result.stderr or "无法读取提交记录")

        commits: list[CommitInfo] = []
        for line in result.stdout.splitlines():
            commit = self._parse_commit_line(line)
            if commit:
                commits.append(commit)
        return commits

    @staticmethod
    def _parse_commit_line(line: str) -> CommitInfo | None:
        parts = line.split("\x1f", 6)
        if len(parts) < 6:
            return None
        return CommitInfo(
            hash=parts[0],
            short_hash=parts[1],
            author=parts[2],
            email=parts[3],
            date=parts[4],
            subject=parts[5],
            refs=parts[6] if len(parts) > 6 else "",
        )

    def commit_detail(self, path: str | Path, commit_hash: str) -> CommitDetail:
        if not HASH_RE.fullmatch(commit_hash):
            raise GitServiceError("提交哈希格式不正确")

        root = self.probe_repository(path)
        normalized = self.run(
            root, ["rev-parse", "--verify", f"{commit_hash}^{{commit}}"], timeout=15
        )
        if not normalized.ok:
            raise GitServiceError("找不到指定提交")
        full_hash = normalized.stdout.strip()

        meta = self.run(
            root,
            [
                "show",
                "-s",
                "--no-show-signature",
                "--date=iso-strict",
                "--format=%H%x1f%an%x1f%ae%x1f%aI%x1f%P%x1f%B",
                full_hash,
            ],
        )
        if not meta.ok:
            raise GitServiceError(meta.stderr or "无法读取提交信息")
        fields = meta.stdout.split("\x1f", 5)
        if len(fields) < 6:
            raise GitServiceError("提交信息格式异常")

        files_result = self.run(
            root,
            [
                "show",
                "--no-show-signature",
                "--format=",
                "--name-status",
                "--find-renames",
                "--first-parent",
                full_hash,
            ],
            timeout=30,
        )
        files: list[CommitFileChange] = []
        if files_result.ok:
            for line in files_result.stdout.splitlines():
                parts = line.split("\t")
                if len(parts) < 2:
                    continue
                status_code = parts[0]
                if status_code[:1] in {"R", "C"} and len(parts) >= 3:
                    files.append(
                        CommitFileChange(
                            status=status_code,
                            path=parts[2],
                            old_path=parts[1],
                        )
                    )
                else:
                    files.append(CommitFileChange(status=status_code, path=parts[1]))

        diff_result = self.run(
            root,
            [
                "show",
                "--no-show-signature",
                "--format=",
                "--no-color",
                "--no-ext-diff",
                "--find-renames",
                "--first-parent",
                full_hash,
            ],
            timeout=45,
        )
        diff = diff_result.stdout if diff_result.ok else ""
        if not diff_result.ok and diff_result.stderr:
            diff = f"无法读取差异：{diff_result.stderr}\n"

        truncated = False
        max_chars = 2_000_000
        if len(diff) > max_chars:
            diff = diff[:max_chars] + "\n\n... 差异内容过大，已截断 ...\n"
            truncated = True

        return CommitDetail(
            hash=fields[0],
            author=fields[1],
            email=fields[2],
            date=fields[3],
            parents=[item for item in fields[4].split() if item],
            message=fields[5],
            files=files,
            diff=diff,
            diff_truncated=truncated,
        )


def mask_remote_url(url: str) -> str:
    """Hide credentials embedded in HTTP(S) remote URLs."""

    if not url:
        return ""
    return re.sub(r"(?i)^(https?://)[^/@\s]+@", r"\1***@", url)
