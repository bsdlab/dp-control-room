# The socket communication, mainly clients
import socket
import time

from control_room.utils.logging import logger

MAX_CONNECT_RETRIES = 3


def create_socket_client(
    host_ip: str, port: int, retry_connection_after_s: float = 1
) -> socket.socket:
    """
    Create a socket client and attempt to connect to a specified host and port.

    This function attempts to establish a TCP connection to the specified host and port.
    It retries the connection up to a maximum number of times (3) if the connection is refused.
    If the connection is successful, the socket object is returned.

    Parameters
    ----------
    host_ip : str
        The IP address of the host to connect to.
    port : int
        The port number on the host to connect to.
    retry_connection_after_s : float, optional
        The number of seconds to wait between connection attempts, by default 1.

    Returns
    -------
    socket.socket
        A socket object representing the connection to the host.

    Raises
    ------
    ConnectionRefusedError
        If the connection is refused after the maximum number of 3 retries.
    """
    conn_try = 0
    while conn_try < MAX_CONNECT_RETRIES:
        try:
            logger.debug(f"Trying connection to: {host_ip=}, {port=}")
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.connect((host_ip, port))
            logger.debug(f"Connected to: {host_ip=}, {port=} using {s=}")
            break
        except ConnectionRefusedError:
            logger.debug(f"Connection refused: {host_ip=}, {port=}, try={conn_try + 1}")

            # Close the socket and start fresh as otherwise
            # we will get a an Errno 22 in the second try
            s.close()

            time.sleep(retry_connection_after_s)
            pass
        conn_try += 1

    return s
