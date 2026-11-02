from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path

from gitman.git_service import GitService
from gitman.models import (
    RepoEntry,
    SYNC_DIVERGED,
    SYNC_LOCAL_AHEAD,
    SYNC_REMOTE_AHEAD,
    SYNC_SYNCED,
)


def git(cwd: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(cwd), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=True,
    )
    return completed.stdout.strip()


class GitServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        self.service = GitService()

        self.remote = self.base / "remote.git"
        git(self.base, "init", "--bare", "-b", "main", str(self.remote))

        self.repo = self.base / "repo"
        git(self.base, "clone", str(self.remote), str(self.repo))
        git(self.repo, "config", "user.name", "Repo User")
        git(self.repo, "config", "user.email", "repo@example.com")

        (self.repo / "README.md").write_text("hello\n", encoding="utf-8")
        git(self.repo, "add", ".")
        git(self.repo, "commit", "-m", "initial commit")
        git(self.repo, "branch", "-M", "main")
        git(self.repo, "push", "-u", "origin", "main")

        self.other = self.base / "other"
        git(self.base, "clone", str(self.remote), str(self.other))
        git(self.other, "config", "user.name", "Other User")
        git(self.other, "config", "user.email", "other@example.com")

        self.entry = RepoEntry(id="repo-1", name="repo", path=str(self.repo))

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_clean_repo_is_synced(self) -> None:
        status = self.service.inspect_repo(self.entry, fetch=False)
        self.assertTrue(status.ok, status.error)
        self.assertEqual(status.branch, "main")
        self.assertEqual(status.sync_state, SYNC_SYNCED)
        self.assertEqual(status.change_count, 0)
        self.assertTrue(status.has_upstream)
        self.assertEqual(status.upstream, "origin/main")
        self.assertIsNotNone(status.last_commit)
        self.assertEqual(status.last_commit.subject, "initial commit")

    def test_local_dirty_and_ahead(self) -> None:
        (self.repo / "README.md").write_text("hello local\n", encoding="utf-8")
        (self.repo / "new.txt").write_text("new\n", encoding="utf-8")
        git(self.repo, "add", "README.md")
        git(self.repo, "commit", "-m", "local change")

        status = self.service.inspect_repo(self.entry, fetch=False)
        self.assertTrue(status.ok, status.error)
        self.assertEqual(status.sync_state, SYNC_LOCAL_AHEAD)
        self.assertEqual(status.ahead, 1)
        self.assertEqual(status.untracked_count, 1)
        self.assertEqual(status.change_count, 1)

    def test_remote_ahead_after_fetch(self) -> None:
        (self.other / "remote.txt").write_text("remote\n", encoding="utf-8")
        git(self.other, "add", ".")
        git(self.other, "commit", "-m", "remote change")
        git(self.other, "push")

        status = self.service.inspect_repo(self.entry, fetch=True)
        self.assertTrue(status.ok, status.error)
        self.assertEqual(status.sync_state, SYNC_REMOTE_AHEAD)
        self.assertEqual(status.behind, 1)
        self.assertEqual(status.ahead, 0)

    def test_diverged(self) -> None:
        (self.repo / "local.txt").write_text("local\n", encoding="utf-8")
        git(self.repo, "add", ".")
        git(self.repo, "commit", "-m", "local change")

        (self.other / "remote.txt").write_text("remote\n", encoding="utf-8")
        git(self.other, "add", ".")
        git(self.other, "commit", "-m", "remote change")
        git(self.other, "push")

        status = self.service.inspect_repo(self.entry, fetch=True)
        self.assertTrue(status.ok, status.error)
        self.assertEqual(status.sync_state, SYNC_DIVERGED)
        self.assertEqual(status.ahead, 1)
        self.assertEqual(status.behind, 1)

    def test_untracked_branch_compares_with_remote_namesake(self) -> None:
        git(self.repo, "branch", "--unset-upstream")
        status = self.service.inspect_repo(self.entry, fetch=False)
        self.assertTrue(status.ok, status.error)
        self.assertFalse(status.has_upstream)
        self.assertEqual(status.compare_ref, "origin/main")
        self.assertEqual(status.sync_state, SYNC_SYNCED)

        (self.repo / "ahead.txt").write_text("ahead\n", encoding="utf-8")
        git(self.repo, "add", ".")
        git(self.repo, "commit", "-m", "ahead without upstream")
        status = self.service.inspect_repo(self.entry, fetch=False)
        self.assertEqual(status.sync_state, SYNC_LOCAL_AHEAD)
        self.assertEqual(status.ahead, 1)

    def test_commit_list_and_detail(self) -> None:
        commits = self.service.list_commits(self.repo)
        self.assertEqual(len(commits), 1)
        self.assertEqual(commits[0].subject, "initial commit")

        detail = self.service.commit_detail(self.repo, commits[0].hash)
        self.assertIn("initial commit", detail.message)
        self.assertEqual(len(detail.files), 1)
        self.assertEqual(detail.files[0].path, "README.md")
        self.assertIn("+hello", detail.diff)

    def test_probe_finds_root_from_subfolder(self) -> None:
        sub = self.repo / "nested" / "folder"
        sub.mkdir(parents=True)
        root = self.service.probe_repository(sub)
        self.assertEqual(root.resolve(), self.repo.resolve())

    def test_non_repo_returns_error_status(self) -> None:
        plain = self.base / "plain"
        plain.mkdir()
        entry = RepoEntry(id="plain", name="plain", path=str(plain))
        status = self.service.inspect_repo(entry, fetch=False)
        self.assertFalse(status.ok)
        self.assertTrue(status.error)


if __name__ == "__main__":
    unittest.main()
