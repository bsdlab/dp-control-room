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
from control_room.utils.logging import logger


@dataclass
class CallbackBroker:
    mod_connections: dict[str, ModuleConnection] = field(default_factory=dict)
    stop_event: threading.Event = threading.Event()

    def listen_for_callbacks(self):
        while not self.stop_event.is_set():
            for mod_name, mod_connection in self.mod_connections.items():
                self.check_for_callback(mod_connection.socket_c)

    def check_for_callback(self, socket: socket):
        """Read from the"""

        fragments = []
        while True:
            chunk = socket.recv(1024)
            if not chunk:
                break
            fragments.append(chunk)
        msg = b"".join(fragments)

        # ignore fully black messages and common start bytes
        msg = msg.replace(b"\r\n", b"")
        msg = msg.replace(b"\xc2", b"")

        if msg != b"":
            msg_arr = msg.decode("ascii").split("|")

            if len(msg_arr) != 3:
                logger.error(
                    "CallbackBroker requires messages of the format:\n"
                    "<target_module_name>|<PCOMM>|{payload}\n"
                    f"Received this: {'|'.join(msg_arr)}"
                )
            else:
                target_module_name, pcomm, payload = msg_arr

                if target_module_name not in self.mod_connections.keys():
                    logger.error(
                        "CallbackBroker received a message for a module that "
                        f"is not registered: {target_module_name}"
                    )
                else:
                    trg_mod = self.mod_connections[target_module_name]
                    trg_mod.pcomms[pcomm](payload)
