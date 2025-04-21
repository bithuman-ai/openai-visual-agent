"""Utility helper functions for the bitHuman Visual Agent Application."""

import io
import os
import signal
import socket
import sys
from contextlib import redirect_stderr

from loguru import logger

from daemon.utils.logging import system


def is_terminal():
    """Check if we're running in a terminal environment."""
    return os.isatty(sys.stdin.fileno()) if hasattr(sys.stdin, "fileno") else False


def is_port_in_use(port: int) -> bool:
    """Check if a port is in use."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind(("0.0.0.0", port))
            return False
        except OSError:
            return True


def force_exit():
    """Force exit the program."""
    system("Forcing program exit...", level="WARNING")
    os._exit(0)


def setup_signal_handlers(shutdown_event):
    """Set up signal handlers for graceful shutdown."""

    def signal_handler(signum, frame):
        """Handle shutdown signals."""
        if not shutdown_event.is_set():
            system("Received shutdown signal. Cleaning up...", level="WARNING")
            shutdown_event.set()
            # Force exit immediately
            force_exit()

    # Register signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)


# Functions from common.py
def safe_emit(socketio_instance, event_name, data, **kwargs):
    """Safely emit a SocketIO event, handling Werkzeug errors."""
    try:
        socketio_instance.emit(event_name, data, **kwargs)
    except AssertionError as e:
        if "write() before start_response" in str(e):
            logger.warning(f"Suppressed Werkzeug error: {e}")
        else:
            raise
    except Exception as e:
        logger.error(f"Error in safe_emit: {e}")


def completely_silent_emit(socketio_instance, event_name, data, **kwargs):
    """Completely silent version of emit that suppresses all errors and output."""
    # Redirect stderr to suppress any error messages
    null_stderr = io.StringIO()
    try:
        with redirect_stderr(null_stderr):
            # Try the emission wrapped in a try-except that catches everything
            try:
                socketio_instance.emit(event_name, data, **kwargs)
            except:
                # Suppress all exceptions completely
                pass
    except:
        # Suppress any errors from redirect_stderr as well
        pass
