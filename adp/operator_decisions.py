"""One bounded signed-data exchange with an existing installed Unix provider.

No provider process is started. This port is neither a semantic oracle nor an
operator approval. The external principal must perform the actual assessment.
"""
from __future__ import annotations

import os
from pathlib import Path
import socket
import stat
import struct
import time

from .config import safe_path
from .errors import ADPError
from .schema import decode, encode, require


def exchange(path, challenge):
    require(os.name=='posix' and hasattr(socket,'SO_PEERCRED'),
        'UNSUPPORTED_PROVIDER: installed Unix peer authentication is unavailable')
    path=safe_path(Path(path))
    def identity():
        info=path.lstat(); parent=path.parent.stat()
        require(stat.S_ISSOCK(info.st_mode) and info.st_uid==os.getuid() and info.st_nlink==1
            and not info.st_mode & 0o077 and parent.st_uid==os.getuid() and not parent.st_mode & 0o077,
            'UNSUPPORTED_PROVIDER: use an existing owned protected Unix socket')
        return info.st_dev,info.st_ino,info.st_uid
    expected=identity()
    raw=encode(challenge,1048576)
    deadline=time.monotonic()+1
    try:
        with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as connection:
            connection.settimeout(max(.001,deadline-time.monotonic()))
            connection.connect(str(path))
            pid,uid,gid=struct.unpack('3i',connection.getsockopt(socket.SOL_SOCKET,socket.SO_PEERCRED,12))
            require(uid==os.getuid() and pid>0 and identity()==expected,'Installed decision peer changed')
            connection.settimeout(max(.001,deadline-time.monotonic()))
            connection.sendall(raw);connection.shutdown(socket.SHUT_WR)
            response=bytearray()
            while True:
                require(time.monotonic()<deadline,'Decision provider deadline exceeded')
                connection.settimeout(max(.001,deadline-time.monotonic()))
                block=connection.recv(65536)
                if not block: break
                response.extend(block)
                require(len(response)<=1048576,'Decision provider response exceeds bounds')
            require(identity()==expected and time.monotonic()<=deadline,'Installed decision peer or deadline changed')
            return decode(bytes(response),1048576)
    except (OSError,ValueError):
        raise ADPError('UNKNOWN_PROVIDER: current independent decision response is unavailable; restore the installed provider') from None
