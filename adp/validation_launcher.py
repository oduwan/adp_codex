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
    # Linux x86_64 only. Reject other ABIs and the x32 syscall namespace.
    load, equal, greater_equal, bits, ret = 0x20, 0x15, 0x35, 0x45, 0x06
    kill, allow = 0x80000000, 0x7fff0000
    rows = [(load, 0, 0, 4), (equal, 1, 0, 0xc000003e), (ret, 0, 0, kill),
            (load, 0, 0, 0), (greater_equal, 0, 1, 0x40000000), (ret, 0, 0, kill)]
    # No process/thread creation, socket creation, namespace/privilege changes,
    # filesystem mutations, tracing, kernel interfaces or alternative open API.
    denied = (29, 30, 31, 53, 56, 57, 58, 62, 64, 65, 66, 67, 68, 69,
              70, 71, 76, 77, 82, 83, 84, 85, 86, 87, 88,
              90, 91, 92, 93, 94, 101, 103, 132, 133, 155, 161, 165, 166,
              167, 168, 169, 175, 176, 188, 189, 190, 197, 198, 199, 200,
              112, 220, 234, 235, 246, 248, 249, 250, 258, 259, 260, 261, 263, 264,
              265, 266, 268, 272, 280, 285, 298, 303, 304, 308, 310, 311,
              313, 316, 317, 321, 323, 425, 426, 427, 435, 437, 438)
    for number in denied:
        rows.extend(((equal, 0, 1, number), (ret, 0, 0, kill)))
    # libc's NSS startup probes AF_UNIX even without a passwd file. Deny that
    # socket with EPERM (never allow it); Internet/raw sockets kill the process.
    rows.extend(((equal, 0, 5, 41), (load, 0, 0, 16), (equal, 0, 1, 1),
                 (ret, 0, 0, 0x00050001), (ret, 0, 0, kill), (load, 0, 0, 0)))
    writable = os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND | 0x400000
    for number, argument in ((2, 1), (257, 2)):  # open/openat flags
        rows.extend(((equal, 0, 4, number), (load, 0, 0, 16 + argument * 8),
                     (bits, 0, 1, writable), (ret, 0, 0, kill), (load, 0, 0, 0)))
    rows.append((ret, 0, 0, allow))
    return b''.join(struct.pack('HBBI', *row) for row in rows)


def arguments(binary: str, image: str, source: str, descriptor: int, argv: tuple[str, ...]) -> tuple[str, ...]:
    return (binary, '--unshare-user', '--unshare-net', '--unshare-pid', '--unshare-ipc',
            '--unshare-uts', '--die-with-parent', '--new-session', '--cap-drop', 'ALL',
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
