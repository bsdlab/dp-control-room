# The socket communication, mainly clients
import socket
import time

from control_room.utils.logging import logger

MAX_CONNECT_RETRIES = 3


def create_socket_client(
    host_ip: str, port: int, retry_connection_after_s: float = 1, timeout: float = 0.1
) -> socket.socket:
    """
    Create a socket client and attempt to connect to a specified host and port.

    This function attempts to establish a TCP connection to the specified host and port.
    It retries the connection up to a maximum number of times (3) if the connection is refused or times out.
    If the connection is successful, the socket object is returned.

    Parameters
    ----------
    host_ip : str
        The IP address of the host to connect to.
    port : int
        The port number on the host to connect to.
    retry_connection_after_s : float, optional
        The number of seconds to wait between connection attempts, by default 1.
    timeout : float, optional
        The timeout duration for the socket connection in seconds, by default 0.1.

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
            s = socket.create_connection((host_ip, port), timeout=timeout)
            logger.debug(f"Connected to: {host_ip=}, {port=} using {s=}")
            return s
        except ConnectionRefusedError:
            logger.debug(f"Connection refused: {host_ip=}, {port=}, try={conn_try + 1}")

            # Close the socket and start fresh as otherwise
            # we will get a an Errno 22 in the second try
            s.close()

            if conn_try == MAX_CONNECT_RETRIES - 1:
                raise ConnectionRefusedError(
                    f"Creating socket failed. Connection refused after {MAX_CONNECT_RETRIES} tries: {host_ip=}, {port=}"
                )
            time.sleep(retry_connection_after_s)
        except TimeoutError:
            logger.debug(
                f"Connection timed out: {host_ip=}, {port=}, try={conn_try + 1}"
            )
            time.sleep(retry_connection_after_s)

            if conn_try == MAX_CONNECT_RETRIES - 1:
                raise TimeoutError(
                    f"Creating socket failed. Connection timed out after {MAX_CONNECT_RETRIES} tries: {host_ip=}, {port=}"
                )
        except Exception as e:
            logger.error(f"Unexpected error when creating socket: {e}")
            try:
                s.close()
            except:
                pass

            if conn_try == MAX_CONNECT_RETRIES - 1:
                raise type(e)(
                    f"Creating socket failed. Unknown error after {MAX_CONNECT_RETRIES} tries: {host_ip=}, {port=}"
                ) from e
            time.sleep(retry_connection_after_s)
        conn_try += 1
