"""Trusted Linux launcher for the explicit single-process validation profile.

Run outside the product. Bubblewrap applies this seccomp program only after
building namespaces/mounts. No product file is imported by this launcher.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import platform
import resource
import struct


def seccomp_program() -> bytes:
    # Linux x86_64 only. Unknown/new and x32 syscalls fail closed.
    load, equal, greater_equal, bits, mask, ret = 0x20, 0x15, 0x35, 0x45, 0x54, 0x06
    kill, allow = 0x80000000, 0x7fff0000
    rows = [(load, 0, 0, 4), (equal, 1, 0, 0xc000003e), (ret, 0, 0, kill),
            (load, 0, 0, 0), (greater_equal, 0, 1, 0x40000000), (ret, 0, 0, kill)]

    def branch(number, body):
        rows.append((equal, 0, len(body), number))
        rows.extend(body)

    # Only the original stdout/stderr pipes are writable. They cannot be
    # closed, replaced, duplicated or marked close-on-exec by the target.
    for number in (1, 20):  # write/writev
        branch(number, [(load, 0, 0, 16), (equal, 1, 0, 1), (equal, 0, 1, 2),
                        (ret, 0, 0, allow), (ret, 0, 0, kill)])
    branch(3, [(load, 0, 0, 16), (greater_equal, 1, 0, 3),
               (ret, 0, 0, kill), (ret, 0, 0, allow)])
    writable = os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND | 0x400000
    for number, argument in ((2, 1), (257, 2)):  # open/openat flags
        branch(number, [(load, 0, 0, 16 + argument * 8), (bits, 0, 1, writable),
                        (ret, 0, 0, kill), (ret, 0, 0, allow)])
    # libc NSS may probe AF_UNIX during startup. EPERM is denial, never ALLOW.
    branch(41, [(load, 0, 0, 16), (equal, 0, 1, 1),
                (ret, 0, 0, 0x00050001), (ret, 0, 0, kill)])
    branch(16, [(load, 0, 0, 24), (equal, 0, 1, 0x5401), (ret, 0, 0, allow),
                (equal, 0, 1, 0x5413), (ret, 0, 0, allow), (ret, 0, 0, kill)])
    branch(72, [(load, 0, 0, 24), (equal, 0, 1, 1), (ret, 0, 0, allow),
                (equal, 0, 1, 3), (ret, 0, 0, allow), (ret, 0, 0, kill)])
    branch(302, [(load, 0, 0, 32), (equal, 0, 3, 0), (load, 0, 0, 36),
                 (equal, 0, 1, 0), (ret, 0, 0, allow), (ret, 0, 0, kill)])
    branch(157, [(load, 0, 0, 16), (equal, 0, 1, 39), (ret, 0, 0, allow),
                 (equal, 0, 1, 21), (ret, 0, 0, allow), (ret, 0, 0, kill)])
    # Only private mappings can exist after exec. This prevents shared-file
    # mutation and later mprotect upgrades without pretending to track VMAs.
    branch(9, [(load, 0, 0, 40), (mask, 0, 0, 0x0f), (equal, 0, 1, 2),
               (ret, 0, 0, allow), (ret, 0, 0, kill)])
    advice = [(load, 0, 0, 32)]
    for value in (0, 4, 8):  # NORMAL/DONTNEED/FREE affect private memory only.
        advice.extend(((equal, 0, 1, value), (ret, 0, 0, allow)))
    advice.append((ret, 0, 0, kill))
    branch(28, advice)  # MADV_REMOVE, privileged and unknown advice are fatal.
    # Read-only queries, process-local memory/signal/timer operations, bounded
    # pipe/event descriptors and lifecycle exit/wait. No filesystem mutator,
    # process creator, network effect, credential change or new syscall is here.
    allowed = (0, 4, 5, 6, 7, 8, 10, 11, 12, 13, 14, 15, 17, 19, 21, 22,
               23, 24, 25, 27, 34, 35, 36, 37, 38, 39, 59, 60, 61, 63,
               78, 79, 80, 81, 89, 95, 96, 97, 98, 99, 100, 102, 104, 107,
               108, 110, 111, 115, 118, 120, 121, 124, 125, 127, 128, 130,
               131, 137, 138, 140, 143, 145, 146, 147, 148, 158, 186, 201,
               202, 204, 213, 217, 218, 219, 221, 222, 223, 224, 225, 226,
               228, 229, 230, 231, 232, 233, 247, 262, 267, 269, 270, 271,
               273, 281, 282, 283, 284, 286, 287, 289, 290, 291, 293, 318,
               332, 334, 439, 441, 449, 462)
    for number in allowed:
        rows.extend(((equal, 0, 1, number), (ret, 0, 0, allow)))
    rows.append((ret, 0, 0, kill))
    return b''.join(struct.pack('HBBI', *row) for row in rows)


def arguments(binary: str, image: str, source: str, descriptor: int, argv: tuple[str, ...]) -> tuple[str, ...]:
    return (binary, '--unshare-user', '--unshare-net', '--unshare-pid', '--unshare-ipc',
            '--unshare-uts', '--as-pid-1', '--die-with-parent', '--new-session', '--cap-drop', 'ALL',
            '--clearenv', '--setenv', 'PATH', '/runtime/bin', '--setenv', 'LANG', 'C',
            '--setenv', 'PYTHONDONTWRITEBYTECODE', '1', '--ro-bind', image, '/',
            '--ro-bind', source, '/work', '--proc', '/proc', '--remount-ro', '/proc',
            '--dev', '/dev', '--remount-ro', '/dev', '--chdir', '/work',
            '--seccomp', str(descriptor), '--', *argv)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--binary', required=True)
    parser.add_argument('--image', required=True)
    parser.add_argument('--source', required=True)
    parser.add_argument('--limits', required=True)
    parser.add_argument('command', nargs=argparse.REMAINDER)
    args = parser.parse_args()
    if platform.system() != 'Linux' or platform.machine() != 'x86_64':
        return 78
    limits = json.loads(args.limits)
    if set(limits) != {'memory_bytes', 'cpu_seconds', 'descriptors'}:
        return 78
    descriptor = os.memfd_create('adp-validation-seccomp', flags=0)
    try:
        os.write(descriptor, seccomp_program())
        os.lseek(descriptor, 0, os.SEEK_SET)
        os.set_inheritable(descriptor, True)
        resource.setrlimit(resource.RLIMIT_AS, (limits['memory_bytes'], limits['memory_bytes']))
        resource.setrlimit(resource.RLIMIT_CPU, (limits['cpu_seconds'], limits['cpu_seconds']))
        resource.setrlimit(resource.RLIMIT_NOFILE, (limits['descriptors'], limits['descriptors']))
        resource.setrlimit(resource.RLIMIT_FSIZE, (0, 0))
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
        command = tuple(args.command[1:] if args.command[:1] == ['--'] else args.command)
        os.execv(args.binary, arguments(args.binary, args.image, args.source, descriptor, command))
    finally:
        os.close(descriptor)
    return 78


if __name__ == '__main__':
    raise SystemExit(main())
