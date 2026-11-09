"""Bounded source/admin seals supplement the supported worker OS sandbox."""
from __future__ import annotations

import hashlib
import os
import stat
from pathlib import Path

from .discovery_schema import digest
from .git import git, value
from .schema import require


def source_seal(root: Path, admitted=()):
    rows, total = [], 0
    for directory, names, files in os.walk(root, followlinks=False):
        names[:] = sorted(n for n in names if not (Path(directory) == root and n == '.git'))
        for name in sorted(files + names):
            path = Path(directory)/name
            relative = path.relative_to(root).as_posix()
            if relative == '.git' or any(relative == a or relative.startswith(a + '/') for a in admitted):
                continue
            info = path.lstat()
            require(stat.S_ISREG(info.st_mode) or stat.S_ISLNK(info.st_mode) or stat.S_ISDIR(info.st_mode), 'Unsupported worker filesystem entry')
            total += info.st_size
            require(total <= 32*1024*1024 and len(rows) < 4096, 'Worker workspace inventory exceeds containment bounds')
            content = (os.readlink(path).encode() if stat.S_ISLNK(info.st_mode)
                       else b'' if stat.S_ISDIR(info.st_mode) else path.read_bytes())
            rows.append((relative, info.st_mode, hashlib.sha256(content).hexdigest()))
    return digest(rows)


def admin_seal(root: Path):
    config = git(root, 'config', '--null', '--list')
    require(not any(row.lower().startswith(b'filter.') for row in config.split(b'\0')),
            'UNSUPPORTED_GIT_FILTER: executable clean/smudge filters require a contained Git port')
    return hashlib.sha256(config + git(root, 'ls-files', '--stage', '-z')
        + git(root, 'for-each-ref', '--format=%(refname) %(objectname)')
        + git(root, 'symbolic-ref', 'HEAD')).hexdigest()
