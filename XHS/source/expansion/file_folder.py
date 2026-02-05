from contextlib import suppress
from pathlib import Path
import os


def file_switch(path: Path) -> None:
    if path.exists():
        path.unlink()
    else:
        path.touch()


def remove_empty_directories(path: Path) -> None:
    exclude = {
        "\\.",
        "\\_",
        "\\__",
    }
    # 使用 os.walk() 代替 Path.walk() 以兼容 Python 3.11
    for dir_path, dir_names, file_names in os.walk(
        str(path),
        topdown=False,
    ):
        if any(i in dir_path for i in exclude):
            continue
        if not dir_names and not file_names:
            with suppress(OSError):
                Path(dir_path).rmdir()
