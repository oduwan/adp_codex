"""Owned runtime images for OS qualification, never a production installer."""
from __future__ import annotations

import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import sysconfig

from adp.validation_sandbox import SandboxPolicy, file_digest, image_digest


def runtime_image(root: Path) -> Path:
    root.mkdir()
    for name in ('work', 'proc', 'dev', 'tmp'):
        (root / name).mkdir()
    executable = root / 'runtime/bin/python'
    executable.parent.mkdir(parents=True)
    shutil.copy2(Path(sys.executable).resolve(), executable)
    stdlib = Path(sysconfig.get_path('stdlib'))
    destination = root / 'runtime/lib' / stdlib.name
    shutil.copytree(stdlib, destination, ignore=shutil.ignore_patterns('__pycache__', 'site-packages',
                    'dist-packages', 'test', 'tests', 'idlelib', 'tkinter', 'ensurepip', 'config-*'))
    # Trusted installed interpreter/library dependencies only; no target code,
    # credential stores, whole /usr mount, package installation or shell.
    dependencies = {Path(sys.executable).resolve(), *stdlib.glob('lib-dynload/*.so')}
    libraries = set()
    for dependency in sorted(dependencies):
        result = subprocess.run(('ldd', str(dependency)), stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                text=True, timeout=5, check=False)
        for name in re.findall(r'(/[A-Za-z0-9_./+:-]+)', result.stdout):
            path = Path(name)
            if path.is_file():
                libraries.add(path)
    for path in sorted(libraries):
        target = root / str(path).lstrip('/')
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)
        # Relocated CPython builds may use $ORIGIN/../lib. Preserve that
        # dedicated-runtime closure without inheriting host LD_LIBRARY_PATH.
        if path.name.startswith('libpython') and '.so' in path.name:
            runtime_library = root / 'runtime/lib' / path.name
            runtime_library.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, runtime_library)
    return root


def policy(image: Path, *, binary: Path | None = None) -> SandboxPolicy:
    # Test selection only. Production never reads this environment variable.
    binary = binary or Path(os.environ.get('ADP_TEST_BWRAP_PATH', '/usr/bin/bwrap'))
    binary = binary.resolve(strict=True)  # Trusted fixture input, not production policy normalization.
    return SandboxPolicy(image, image_digest(image), binary, file_digest(binary), '/runtime/bin/python')


def git(root: Path, *args: str) -> str:
    return subprocess.check_output(('git', '-c', 'core.hooksPath=/dev/null', '-C', str(root), *args), stderr=subprocess.DEVNULL).decode().strip()


def project(root: Path) -> str:
    root.mkdir()
    git(root, 'init', '--initial-branch=qualification')
    git(root, 'config', 'user.name', 'Disposable Fixture')
    git(root, 'config', 'user.email', 'fixture@example.org')
    (root / 'tracked').write_text('original')
    git(root, 'add', 'tracked')
    git(root, 'commit', '-m', 'Disposable validation baseline')
    return git(root, 'rev-parse', 'HEAD')
