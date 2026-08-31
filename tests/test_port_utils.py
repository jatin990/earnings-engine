"""Unit tests for port management utilities."""

import socket
from earnings_engine.port_utils import (
    is_port_in_use,
    get_pids_on_port,
    kill_process_on_port,
    ensure_port_available,
)


def test_is_port_in_use_free_port():
    # Find a dynamically available port
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        free_port = s.getsockname()[1]
    
    # Once closed, it should not be in use
    assert not is_port_in_use(free_port, "127.0.0.1")


def test_is_port_in_use_bound_port():
    # Bind a temporary socket
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("127.0.0.1", 0))
    sock.listen(1)
    bound_port = sock.getsockname()[1]

    try:
        assert is_port_in_use(bound_port, "127.0.0.1")
    finally:
        sock.close()


def test_ensure_port_available_free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        free_port = s.getsockname()[1]

    killed = ensure_port_available(free_port, "127.0.0.1")
    assert killed == []
