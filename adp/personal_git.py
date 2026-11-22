"""Read-only physical product administration binding for personal consent."""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import stat

from .config import safe_path
from .git import value
from .schema import require


def administration(root: Path):
    def identity(path):
        safe_path(path)
        info = path.lstat()
        require(info.st_uid == os.getuid() and not info.st_mode & 0o022,
                "Product administration must be owned and protected from foreign writers")
        require(stat.S_ISREG(info.st_mode) or stat.S_ISDIR(info.st_mode), "Unsafe product administration entry")
        row = {"path": str(path), "device": info.st_dev, "inode": info.st_ino, "uid": info.st_uid, "mode": info.st_mode}
        if stat.S_ISREG(info.st_mode):
            require(info.st_nlink == 1 and info.st_size <= 4096, "Unsafe product Git indirection")
            row["content"] = hashlib.sha256(path.read_bytes()).hexdigest()
        return row
    common = safe_path(Path(value(root, "rev-parse", "--path-format=absolute", "--git-common-dir")))
    directory = safe_path(Path(value(root, "rev-parse", "--absolute-git-dir")))
    require(common.is_dir() and directory.is_dir() and value(root, "rev-parse", "--show-toplevel") == str(root),
            "Product Git administration is not the selected checkout")
    return {"root": identity(root), "marker": identity(root / ".git"), "common": identity(common), "directory": identity(directory)}
