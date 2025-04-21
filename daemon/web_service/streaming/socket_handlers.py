"""SocketIO event handlers for the bitHuman Visual Agent.

This module provides handlers for SocketIO events like connecting, disconnecting,
and various custom events used by the web clients.
"""

from typing import TYPE_CHECKING

from flask import request
from flask_socketio import SocketIO
from loguru import logger

from daemon.web_service.utils.socket_utils import emit_status_update

if TYPE_CHECKING:
    from daemon.core.model_loader import ModelLoader


def register_socket_handlers(socketio: SocketIO, model_loader: "ModelLoader"):
    """Register handlers for socket events.

    Args:
        socketio: The SocketIO instance
        model_loader: The model loader instance for status updates
    """

    @socketio.on("connect")
    def handle_connect():
        """Handle client connection to socket."""
        logger.info("Client connected to socketio")
        if model_loader:
            try:
                status = model_loader.get_status()
                emit_status_update(socketio, status, client_id=request.sid)
            except Exception as e:
                logger.error(f"Error sending initial status to client: {e}")

    @socketio.on("disconnect")
    def handle_disconnect():
        """Handle client disconnection from socket."""
        logger.info("Client disconnected from socketio")

    @socketio.on("get_status")
    def handle_get_status():
        """Handle client request for current status."""
        if model_loader:
            try:
                status = model_loader.get_status()
                emit_status_update(socketio, status, client_id=request.sid)
            except Exception as e:
                logger.error(f"Error handling get_status request: {e}")

    @socketio.on("request_reload")
    def handle_request_reload(data):
        """Handle client request to reload a model.

        Args:
            data: Dictionary containing model_path and other options
        """
        if model_loader and data and "model_path" in data:
            try:
                model_path = data["model_path"]
                force_reload = data.get("force_reload", False)
                logger.info(f"Socket client requested model reload: {model_path}")

                success = model_loader.request_reload(
                    model_path, force_reload=force_reload
                )

                socketio.emit(
                    "reload-request-response",
                    {"success": success, "model_path": model_path},
                    to=request.sid,
                )

            except Exception as e:
                logger.error(f"Error handling request_reload: {e}")
                socketio.emit(
                    "reload-request-response",
                    {"success": False, "error": str(e)},
                    to=request.sid,
                )

    @socketio.on("toggle_mute")
    def handle_toggle_mute():
        """Handle client request to toggle mute state."""
        if model_loader:
            try:
                # Toggle mute state
                is_muted = model_loader.toggle_mute()
                logger.info(f"Client requested toggle mute to {is_muted}")

                # Broadcast the new state to all clients
                socketio.emit("mute-state-changed", {"muted": is_muted})

                # Also send confirmation to the requesting client
                socketio.emit(
                    "toggle-mute-response",
                    {"success": True, "muted": is_muted},
                    to=request.sid,
                )

            except Exception as e:
                logger.error(f"Error handling toggle_mute: {e}")
                socketio.emit(
                    "toggle-mute-response",
                    {"success": False, "error": str(e), "muted": False},
                    to=request.sid,
                )
        else:
            socketio.emit(
                "toggle-mute-response",
                {
                    "success": False,
                    "error": "No active visual agent runner",
                    "muted": False,
                },
                to=request.sid,
            )

    logger.info("Socket event handlers registered")
