"""SocketIO utility functions for the bitHuman Visual Agent API.

This module provides helper functions for working with SocketIO, including
error handling and safe emission of events.
"""

import io
from contextlib import redirect_stderr
from typing import Any

from flask_socketio import SocketIO
from loguru import logger


def safe_socket_emit(socketio, event_name, data, **kwargs):
    """Safely emit a SocketIO event, handling Werkzeug errors.

    A wrapper around SocketIO.emit that handles common errors that can occur
    when emitting events, particularly the Werkzeug "write() before start_response"
    error that can occur with Flask-SocketIO.

    Args:
        socketio: The SocketIO instance
        event_name: Name of the event to emit
        data: Data to send with the event
        **kwargs: Additional arguments to pass to emit
    """
    try:
        # Suppress stdout/stderr during emit to prevent noise
        with redirect_stderr(io.StringIO()):
            socketio.emit(event_name, data, **kwargs)
    except AssertionError as e:
        if "write() before start_response" in str(e):
            # This is a common benign error in Flask-SocketIO that we can ignore
            logger.debug(f"Suppressed Werkzeug error during {event_name} event: {e}")
        else:
            # Re-raise other assertion errors
            logger.warning(f"AssertionError in socket.emit({event_name}): {e}")
    except Exception as e:
        logger.error(f"Error in socket.emit({event_name}): {e}")


def emit_status_update(
    socketio: SocketIO,
    status: dict[str, Any],
    client_id: str = None,
    namespace: str = "/",
):
    """Emit a status update to clients.

    Sends the current status to either a specific client or broadcasts to all clients.

    Args:
        socketio: The SocketIO instance
        status: Status data to send
        client_id: Optional client ID to send to (broadcasts to all if None)
        namespace: SocketIO namespace to use
    """
    try:
        if client_id:
            safe_socket_emit(
                socketio, "status-update", status, to=client_id, namespace=namespace
            )
        else:
            safe_socket_emit(socketio, "status-update", status, namespace=namespace)

        # Also emit loading state for convenience
        is_loading = status.get("is_reloading", False) or not status.get(
            "is_ready", False
        )

        if client_id:
            safe_socket_emit(
                socketio, "loading-state", is_loading, to=client_id, namespace=namespace
            )
        else:
            safe_socket_emit(socketio, "loading-state", is_loading, namespace=namespace)

    except Exception as e:
        logger.error(f"Error emitting status update: {e}")


def emit_loading_state(
    socketio: SocketIO, is_loading: bool, client_id: str = None, namespace: str = "/"
):
    """Emit loading state to clients.

    Sends the current loading state to either a specific client or broadcasts to all clients.

    Args:
        socketio: The SocketIO instance
        is_loading: Whether the system is currently loading
        client_id: Optional client ID to send to (broadcasts to all if None)
        namespace: SocketIO namespace to use
    """
    try:
        if client_id:
            safe_socket_emit(
                socketio, "loading-state", is_loading, to=client_id, namespace=namespace
            )
        else:
            safe_socket_emit(socketio, "loading-state", is_loading, namespace=namespace)
    except Exception as e:
        logger.error(f"Error emitting loading state: {e}")


def setup_socket_handlers(socketio: SocketIO, model_loader=None):
    """Setup default socket event handlers.

    Registers event handlers for common socket events like connect/disconnect.

    Args:
        socketio: The SocketIO instance
        model_loader: The model loader instance for status updates
    """

    @socketio.on("connect")
    def handle_connect():
        """Handle client connection."""
        logger.info("Client connected to socketio")
        if model_loader:
            try:
                from flask import request

                status = model_loader.get_status()
                emit_status_update(socketio, status, client_id=request.sid)
            except Exception as e:
                logger.error(f"Error sending initial status to client: {e}")

    @socketio.on("disconnect")
    def handle_disconnect():
        """Handle client disconnection."""
        logger.info("Client disconnected from socketio")

    @socketio.on("get_status")
    def handle_get_status():
        """Handle explicit status request from client."""
        if model_loader:
            try:
                from flask import request

                status = model_loader.get_status()
                emit_status_update(socketio, status, client_id=request.sid)
            except Exception as e:
                logger.error(f"Error handling status request: {e}")

    logger.info("Socket event handlers registered")
