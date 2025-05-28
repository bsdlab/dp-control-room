from pathlib import Path

from dareplane_utils.logging.server import LogRecordSocketReceiver

logfile = Path("dareplane_cr_all.log")


def run_log_server():
    """
    Start the log server and begin receiving log records on default port 9020 (logging.handlers.DEFAULT_TCP_LOGGING_PORT).

    This function initializes a LogRecordSocketReceiver with the specified log file
    and starts serving log records until the server is stopped.
    """
    rcv = LogRecordSocketReceiver(logfile=logfile)
    rcv.serve_until_stopped()


if __name__ == "__main__":
    run_log_server()
