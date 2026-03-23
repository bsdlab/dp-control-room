import time

from dareplane_utils.module_handling.module_connection import ModuleConnection


class DPModuleConnection(ModuleConnection):
    """ModuleConection subclass that adds dp-specific functions such as getting pcomms."""

    def get_pcommands(self):
        self.communicator.send(b"GET_PCOMMS")
        time.sleep(0.1)
        msg = self.communicator.receive(2048 * 8)
        decoded = msg.decode().strip()
        if decoded:
            self.pcomms = decoded.split("|")
