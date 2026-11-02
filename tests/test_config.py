from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from gitman.config import (
    ConfigStore,
    application_directory,
    default_config_path,
)
from gitman.models import (
    AppConfig,
    AppSettings,
    CATEGORY_SHARED,
    RepoEntry,
)


class ConfigStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "config.json"
        self.store = ConfigStore(self.path)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_round_trip(self) -> None:
        config = AppConfig(
            repos=[
                RepoEntry(
                    id="abc",
                    name="Demo",
                    path=str(Path(self.temp.name) / "demo"),
                    category=CATEGORY_SHARED,
                )
            ],
            settings=AppSettings(fetch_on_refresh=False),
        )
        self.store.save(config)
        loaded, error = self.store.load()
        self.assertIsNone(error)
        self.assertEqual(len(loaded.repos), 1)
        self.assertEqual(loaded.repos[0].name, "Demo")
        self.assertEqual(loaded.repos[0].category, CATEGORY_SHARED)
        self.assertFalse(loaded.settings.fetch_on_refresh)

    def test_missing_file_is_empty(self) -> None:
        loaded, error = self.store.load()
        self.assertIsNone(error)
        self.assertEqual(loaded.repos, [])

    def test_default_config_is_next_to_executable(self) -> None:
        exe = Path(self.temp.name) / "GitMan" / "GitMan.exe"
        exe.parent.mkdir()
        exe.touch()
        env = {key: value for key, value in os.environ.items() if key != "GITMAN_CONFIG"}
        with mock.patch.dict(os.environ, env, clear=True):
            with mock.patch.object(sys, "frozen", True, create=True):
                with mock.patch.object(sys, "executable", str(exe)):
                    self.assertEqual(
                        default_config_path(), exe.resolve().parent / "config.json"
                    )

    def test_source_config_is_in_project_root(self) -> None:
        env = {key: value for key, value in os.environ.items() if key != "GITMAN_CONFIG"}
        with mock.patch.dict(os.environ, env, clear=True):
            self.assertEqual(
                default_config_path(),
                application_directory() / "config.json",
            )

    def test_corrupt_file_returns_error(self) -> None:
        self.path.write_text("{not json", encoding="utf-8")
        loaded, error = self.store.load()
        self.assertIsNotNone(error)
        self.assertEqual(loaded.repos, [])

    def test_duplicate_repos_are_ignored(self) -> None:
        data = {
            "version": 1,
            "repos": [
                {"id": "a", "name": "One", "path": "C:/demo", "category": "private"},
                {"id": "b", "name": "Two", "path": "c:\\demo", "category": "shared"},
            ],
        }
        self.path.write_text(json.dumps(data), encoding="utf-8")
        loaded, error = self.store.load()
        self.assertIsNotNone(error)
        self.assertEqual(len(loaded.repos), 1)

    def test_invalid_sections_do_not_crash(self) -> None:
        self.path.write_text(
            json.dumps({"version": 1, "repos": {"bad": True}, "settings": []}),
            encoding="utf-8",
        )
        loaded, error = self.store.load()
        self.assertIsNotNone(error)
        self.assertEqual(loaded.repos, [])
        self.assertTrue(loaded.settings.fetch_on_refresh)


if __name__ == "__main__":
    unittest.main()
