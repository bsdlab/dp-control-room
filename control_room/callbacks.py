# Implement a callback handler, which will loop over the socket clients and check
# if there is a message to be read. If so, it will be passed according to the
# payload.
#
# Think of how to do the name mapping correctly
#
# Put this handling into another thread.

import threading
from dataclasses import dataclass, field
from socket import socket

from control_room.connection import ModuleConnection
from control_room.gui.callbacks import make_ao_payload_from_json
from control_room.utils.logging import logger


@dataclass
class CallbackBroker:
    """
    A class to handle callbacks from socket clients.

    This class manages connections to various modules and listens for callbacks
    on these connections. It processes the received messages and forwards them
    to the appropriate target modules.

    Attributes
    ----------
    mod_connections : dict[str, ModuleConnection]
        A dictionary mapping module names to their connections.
    stop_event : threading.Event
        An event to signal the stopping of the callback listening loop.
    """

    mod_connections: dict[str, ModuleConnection] = field(default_factory=dict)
    stop_event: threading.Event = threading.Event()

    def listen_for_callbacks(self):
        """
        Start listening for callbacks from connected modules.

        This method runs in a loop, checking each connected module for callbacks.
        If a callback is received, it is processed and forwarded to the appropriate
        target module. The loop continues until the stop event is set.

        Notes
        -----
        This loop could be a performance bottleneck if multiple modules need to be
        checked. Consider creating a whitelist of modules to be checked for callbacks.
        """
        while not self.stop_event.is_set():
            # TODO: This loop could be a performance bottleneck, if multiple
            # modules need to be checked --> potentially create a whitelist
            # of modules which are to be checked for callbacks.
            for mod_name, mod_connection in self.mod_connections.items():
                self.check_for_callback(mod_connection.socket_c, mod_name)

    def check_for_callback(self, msocket: socket, mod_name: str):
        """
        Check for callbacks on the given socket.

        This method reads messages from the provided socket and processes them.
        If a valid callback message is received, it is forwarded to the appropriate
        target module. The method handles message formatting and validation.

        Parameters
        ----------
        msocket : socket
            The socket to check for callbacks.
        mod_name : str
            The name of the module associated with the socket.

        Notes
        -----
        This method ignores fully blank messages and common start bytes.
        """
        # logger.debug(f"Checking for callbacks in {msocket=}")
        fragments = []
        while True:
            try:
                chunk = msocket.recv(1024)
                if not chunk:
                    break
                fragments.append(chunk)
            # break in case of timeout
            except TimeoutError:
                break

        msg = b"".join(fragments)

        # ignore fully black messages and common start bytes
        msg = msg.replace(b"\r\n", b"")
        msg = msg.replace(b"\xc2", b"")

        if msg != b"":
            logger.debug(f"Received callback {msg=}")
            msg_arr = msg.decode("ascii").split("|")
            logger.info(f"{msg_arr=}")

            if len(msg_arr) != 3:
                logger.error(
                    "CallbackBroker requires messages of the format:\n"
                    "<target_module_name>|<PCOMM>|{payload}\n"
                    f"Received this: {'|'.join(msg_arr)}"
                )
            else:
                target_module_name, pcomm, payload = msg_arr

                # Assert that the target module is registered
                if target_module_name not in self.mod_connections.keys():
                    logger.error(
                        "CallbackBroker received a message for a module that "
                        f"is not registered: {target_module_name}"
                    )
                # Assert that the target module supports the PCOMM
                elif pcomm not in self.mod_connections[target_module_name].pcomms:
                    logger.error(
                        "CallbackBroker received a message for a module that "
                        f"does not support the PCOMM: {pcomm}"
                    )
                else:
                    trg_mod = self.mod_connections[target_module_name]

                    if trg_mod.name.startswith("dp-ao-communication"):
                        payload = make_ao_payload_from_json(payload)

                    cmd = pcomm + "|" + payload
                    trg_mod.socket_c.sendall(cmd.encode())
