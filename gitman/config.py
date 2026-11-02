"""Configuration persistence for GitMan."""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any

from .models import AppConfig, AppSettings, RepoEntry


CONFIG_VERSION = 1


def application_directory() -> Path:
    """Return the directory that contains the running application.

    In a PyInstaller build this is the directory containing GitMan.exe.  When
    running from source it is the project root, so the app remains portable.
    """

    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def default_config_path() -> Path:
    override = os.environ.get("GITMAN_CONFIG")
    if override:
        return Path(override).expanduser()
    return application_directory() / "config.json"


class ConfigStore:
    """Loads and atomically saves the JSON configuration."""

    def __init__(self, path: Path):
        self.path = Path(path)

    def load(self) -> tuple[AppConfig, str | None]:
        if not self.path.exists():
            return AppConfig(), None

        try:
            with self.path.open("r", encoding="utf-8") as handle:
                raw: Any = json.load(handle)
        except (OSError, json.JSONDecodeError) as exc:
            return AppConfig(), f"配置文件读取失败：{exc}"

        if not isinstance(raw, dict):
            return AppConfig(), "配置文件格式错误：根节点必须是对象。"

        repos: list[RepoEntry] = []
        seen_ids: set[str] = set()
        seen_paths: set[str] = set()
        invalid = 0
        raw_repos = raw.get("repos", [])
        if not isinstance(raw_repos, list):
            invalid += 1
            raw_repos = []
        for item in raw_repos:
            if not isinstance(item, dict):
                invalid += 1
                continue
            try:
                entry = RepoEntry.from_dict(item)
            except (KeyError, TypeError, ValueError):
                invalid += 1
                continue
            if not entry.name:
                entry.name = Path(entry.path).name or entry.path
            path_key = os.path.normcase(os.path.abspath(entry.path))
            if entry.id in seen_ids or path_key in seen_paths:
                invalid += 1
                continue
            seen_ids.add(entry.id)
            seen_paths.add(path_key)
            repos.append(entry)

        settings_data = raw.get("settings")
        if not isinstance(settings_data, dict):
            settings_data = {}
        settings = AppSettings.from_dict(settings_data)
        error = f"配置中有 {invalid} 条无效或重复的仓库记录，已忽略。" if invalid else None
        return AppConfig(repos=repos, settings=settings), error

    def save(self, config: AppConfig) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": CONFIG_VERSION,
            "settings": config.settings.to_dict(),
            "repos": [repo.to_dict() for repo in config.repos],
        }
        serialized = json.dumps(payload, ensure_ascii=False, indent=2)
        fd, temp_name = tempfile.mkstemp(
            prefix=".gitman-", suffix=".json", dir=str(self.path.parent)
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
                handle.write(serialized)
                handle.write("\n")
            os.replace(temp_name, self.path)
        finally:
            try:
                os.unlink(temp_name)
            except OSError:
                pass
