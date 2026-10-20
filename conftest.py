"""Local shim for Windows (untracked, see .git/info/exclude).

asyncio on Windows needs an AF_INET socketpair for the event loop's self-pipe,
which pytest-homeassistant-custom-component blocks with pytest_socket.disable_socket.
On Windows, that call only restricts connects to loopback, so no test reaches the
network while the loop can still be created.
"""
import sys

if sys.platform == "win32":
    import pytest_socket

    def _disable_socket_windows(allow_unix_socket: bool = False) -> None:
        pytest_socket.socket_allow_hosts(["127.0.0.1"])

    pytest_socket.disable_socket = _disable_socket_windows
