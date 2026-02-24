import socket
import time


def wait_for_port(host: str = "127.0.0.1", port: int = 9020, timeout: float = 5.0):
    """Wait until a port is open on the given host, or timeout."""
    deadline = time.time() + timeout
    last_err = None
    while time.time() < deadline:
        try:
            with socket.socket() as s:
                s.settimeout(0.5)
                s.connect((host, port))
                s.close()
                return True
        except OSError as e:
            last_err = e
            time.sleep(0.5)
    raise TimeoutError(f"Port {host}:{port} not ready: {last_err}")
