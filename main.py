"""GitMan application entry point."""

from __future__ import annotations

import argparse
import logging
import shutil
import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication

from gitman import __version__
from gitman.config import ConfigStore, default_config_path
from gitman.ui.main_window import MainWindow
from gitman.ui.theme import apply_theme, make_app_icon


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="GitMan 多仓库状态看板")
    parser.add_argument(
        "--config",
        type=Path,
        help="使用指定的配置文件（默认位于程序所在目录的 config.json）",
    )
    parser.add_argument("--version", action="version", version=f"GitMan {__version__}")
    return parser.parse_args(argv)


def _set_windows_app_id() -> None:
    if sys.platform != "win32":
        return
    try:
        import ctypes

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            "GitMan.MultiRepoDashboard.1"
        )
    except Exception:
        pass


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    _set_windows_app_id()

    app = QApplication(sys.argv[:1])
    app.setApplicationName("GitMan")
    app.setApplicationDisplayName("GitMan")
    app.setOrganizationName("GitMan")
    app.setOrganizationDomain("gitman.local")
    app.setApplicationVersion(__version__)
    apply_theme(app)
    app.setWindowIcon(make_app_icon())

    store = ConfigStore(args.config or default_config_path())
    config, config_error = store.load()

    startup_messages: list[str] = []
    if config_error:
        startup_messages.append(config_error)
    if shutil.which("git") is None:
        startup_messages.append(
            "未在 PATH 中找到 git 命令。请安装 Git 后再刷新仓库。"
        )
    startup_message = "\n\n".join(startup_messages) if startup_messages else None

    window = MainWindow(store, config, startup_message=startup_message)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
