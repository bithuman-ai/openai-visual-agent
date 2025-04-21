"""Core server implementation for the bitHuman Visual Agent Web Service.

This module provides the main Flask/SocketIO server implementation, handling:
- Server configuration and initialization
- Socket.IO event handling
- Web routes (UI and API endpoints)
- Error suppression and handling

Other modules can access the socketio instance via get_socketio().
"""

import io
import logging
import socket
import threading
from contextlib import redirect_stderr

from flask import Flask, jsonify, request
from flask_cors import CORS
from flask_socketio import SocketIO

from daemon.utils import assets_manager
from daemon.utils.logging import error, info, ui, warning
from daemon.web_service.streaming.socket_handlers import register_socket_handlers
from daemon.web_service.templates import HTML_TEMPLATE

# Global variables
app = None
socketio = None
shutdown_event = threading.Event()

# Initialize logging for this module
log = logging.getLogger("server")  # Fallback for standard logging


def init_socketio(socket_instance):
    """Initialize the global socketio instance.

    Args:
        socket_instance: SocketIO instance to use for emitting frames
    """
    global socketio
    socketio = socket_instance
    ui("Initialized socketio for frame streamer")


def get_socketio():
    """Get the global socketio instance.

    Returns:
        The global SocketIO instance
    """
    global socketio
    return socketio


def create_app(model_loader) -> tuple[Flask, SocketIO]:
    """Create and configure the Flask application.

    Sets up the Flask application, configures SocketIO, registers routes,
    and applies performance and error handling patches.

    Args:
        model_loader: The ModelLoader instance

    Returns:
        Tuple of (Flask app, SocketIO instance)
    """
    global app, socketio

    # Apply Werkzeug patch to suppress common errors
    _apply_werkzeug_patch()

    # Choose SocketIO async mode
    async_mode = _select_async_mode()

    # Check if we're in production mode
    is_production = assets_manager.get_server_mode() == "production"

    # Create and configure Flask app
    app = Flask(__name__)
    app.config["DEBUG"] = not is_production  # Only enable debug in development
    app.config["SECRET_KEY"] = assets_manager.get_setting(
        "server.flaskSecretKey", "bithuman_secret_key!"
    )

    # Enable CORS for all routes
    CORS(app, resources={r"/*": {"origins": "*"}})

    # Increase default socket timeout
    socket.setdefaulttimeout(120)  # 2 minutes

    # Create socketio instance
    socketio = SocketIO(async_mode=async_mode)

    # Initialize socketio with best-practices config
    _configure_socketio(socketio, app)

    # Configure Flask logging
    app.logger.setLevel(logging.WARNING if is_production else logging.INFO)

    # Setup the default socket handlers
    register_socket_handlers(socketio, model_loader)

    # Add development request logging if needed
    if not is_production:
        _configure_request_logging(app)

    # Setup main UI route
    @app.route("/")
    def index():
        """Main page - Visual Agent web player."""
        # Get the port number from settings.json
        port = assets_manager.get_server_port()
        # Inject the port number into the template
        html = HTML_TEMPLATE.replace("'{{port}}'", f"'{port}'")
        return html

    # API endpoint to access settings
    @app.route("/api/settings", methods=["GET"])
    def get_settings():
        """Return server settings information."""
        try:
            # Return selected settings that clients might need
            server_settings = {
                "server": {
                    "port": assets_manager.get_server_port(),
                    "mode": assets_manager.get_server_mode(),
                    "debug": assets_manager.get_debug_mode(),
                },
                "ui": {"showDebug": assets_manager.get_setting("ui.showDebug", False)},
            }
            log.info(f"Returning settings: {server_settings}")
            return jsonify(server_settings)
        except Exception as e:
            import traceback

            log.error(f"Error retrieving settings: {str(e)}")
            log.error(f"Traceback: {traceback.format_exc()}")
            return jsonify({"error": "Failed to retrieve settings"}), 500

    # Direct toggle-mute endpoint - simple and reliable implementation
    @app.route("/api/direct-toggle-mute", methods=["POST"])
    def direct_toggle_mute():
        """Direct endpoint to toggle mute."""
        try:
            if model_loader:
                is_muted = model_loader.toggle_mute()
                log.info(f"Direct API toggle mute: {is_muted}")
                return jsonify({"success": True, "muted": is_muted}), 200
            else:
                log.error("No model loader available in direct endpoint")
                return jsonify(
                    {"error": "Model loader not available", "muted": False}
                ), 500
        except Exception as e:
            log.error(f"Error in direct toggle mute: {e}")
            import traceback

            log.error(traceback.format_exc())
            return jsonify({"error": str(e), "muted": False}), 500

    # Register all API endpoints from endpoint modules
    from daemon.web_service.endpoints import register_all_endpoints

    register_all_endpoints(app, model_loader)

    return app, socketio


def _apply_werkzeug_patch():
    """Apply Werkzeug server patch to suppress common errors."""
    try:
        from werkzeug.serving import WSGIRequestHandler

        # Store the original run_wsgi method
        original_run_wsgi = WSGIRequestHandler.run_wsgi

        # Create a patched version that handles the assertion error and suppresses stderr
        def patched_run_wsgi(self):
            try:
                # Redirect stderr during the operation to suppress any errors
                null_stderr = io.StringIO()
                with redirect_stderr(null_stderr):
                    return original_run_wsgi(self)
            except AssertionError as e:
                if "write() before start_response" in str(e):
                    # Just return empty result but don't log anything
                    return []
                raise

        # Apply the monkey patch
        WSGIRequestHandler.run_wsgi = patched_run_wsgi
        log.info("Applied Werkzeug server patch to suppress common errors")

    except Exception as e:
        log.warning(f"Failed to apply Werkzeug server patch: {e}")


def _select_async_mode():
    """Select the SocketIO async mode based on settings or available packages."""
    # Get async mode from settings
    async_mode = assets_manager.get_setting("server.asyncMode", "threading")

    # Only try eventlet/gevent if explicitly configured
    if async_mode == "eventlet":
        try:
            import eventlet

            eventlet.monkey_patch()
            log.info("Using eventlet for SocketIO")
        except ImportError:
            async_mode = "threading"
            log.warning("Failed to import eventlet, falling back to threading mode")
    elif async_mode == "gevent":
        try:
            import gevent
            import gevent.monkey

            gevent.monkey.patch_all()
            log.info("Using gevent for SocketIO")
        except ImportError:
            async_mode = "threading"
            log.warning("Failed to import gevent, falling back to threading mode")
    else:
        log.info(f"Using {async_mode} mode for SocketIO")

    return async_mode


def _configure_socketio(socketio, app):
    """Configure SocketIO with optimal settings."""
    try:
        socketio.init_app(
            app,
            cors_allowed_origins="*",
            debug=False,  # Disable debug completely
            engineio_logger=False,  # Disable engineio logger completely
            ping_timeout=60,
            ping_interval=25,
            max_http_buffer_size=10 * 1024 * 1024,
            always_connect=True,
            manage_session=True,  # Let socketio manage sessions
            transports=["websocket", "polling"],
        )
    except Exception as e:
        log.error(f"Error initializing SocketIO: {e}")
        # Fall back to minimal configuration if advanced config fails
        socketio.init_app(app, cors_allowed_origins="*")


def _configure_request_logging(app):
    """Configure request logging for development."""

    @app.before_request
    def log_request_info():
        # Skip logging for static files and frequent API calls
        if (
            not request.path.startswith("/static/")
            and not request.path == "/api/status"
        ):
            log.info(f"Request: {request.method} {request.path}")
            if request.is_json and not request.path == "/api/status":
                log.debug(f"JSON Body: {request.get_json()}")

    @app.after_request
    def log_response_info(response):
        # Skip logging for static files and frequent API calls
        if (
            not request.path.startswith("/static/")
            and not request.path == "/api/status"
        ):
            log.info(
                f"Response: {response.status_code} for {request.method} {request.path}"
            )
        return response
