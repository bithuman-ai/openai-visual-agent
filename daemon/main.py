"""Main entry point for the bitHuman Visual Agent daemon.

This module serves as the runtime component for the Visual Agent application. It coordinates:
1. Daemon server runtime management
2. Model management and operation
3. Web service and socket communication
4. Application lifecycle management
5. Graceful shutdown procedures

IMPORTANT: This daemon assumes that the launcher has already verified the environment,
downloaded the necessary assets, and prepared everything for the daemon to run.

Usage:
    To run the daemon standalone (after running the launcher):
        $ python -m daemon [--port PORT] [--model MODEL_PATH]

    Or import and call programmatically:
        from daemon import run_daemon
        run_daemon(model_path="/path/to/model.imx", port=5001)
"""

#############################
# Standard library imports
#############################
import argparse
import asyncio
import http.client
import json
import os
import signal
import socket
import sys
import threading
import time
import traceback
from typing import Optional, Tuple

from livekit.agents import utils

from daemon.core.model_loader import ModelLoader
from daemon.utils import assets_manager
from daemon.utils.logging import (
    LogCategory,
    configure_logging,
    error,
    model,
    server as log_server,
    system,
    ui,
    warning,
)
from daemon.web_service import create_app, init_socketio


#############################
# Error Handling Setup
#############################
# Add stderr filtering to completely suppress common Werkzeug errors in logs
class SuppressWerkzeugErrorFilter:
    """Filter to suppress common Werkzeug errors from displaying in logs."""

    def __init__(self, original_stderr):
        """Initialize the filter with the original stderr object."""
        self.original_stderr = original_stderr

    def write(self, message):
        """Filter and write messages to the original stderr."""
        if "AssertionError: write() before start_response" not in message:
            self.original_stderr.write(message)

    def flush(self):
        """Flush the original stderr buffer."""
        self.original_stderr.flush()

    def __getattr__(self, attr):
        """Delegate all other attributes to the original stderr."""
        return getattr(self.original_stderr, attr)


# Apply the filter to sys.stderr
sys.stderr = SuppressWerkzeugErrorFilter(sys.stderr)


#############################
# Global variables
#############################
# Global event shared across modules to coordinate shutdown
shutdown_event = threading.Event()

# Global model loader instance accessible by web services and other components
model_loader = None

# Thread-safe logging configuration to prevent duplicate initialization
_logging_configured = False
_logging_lock = threading.Lock()

# Setup user data directory and initialize settings
user_data_dir = assets_manager.get_user_data_dir()
settings = assets_manager.load_settings()

# Ensure logging is configured properly (since we removed auto-initialization)
with _logging_lock:
    if not _logging_configured:
        configure_logging()
        _logging_configured = True

# Flag to indicate if shutdown is in progress
shutting_down = False

#############################
# Utility Functions
#############################


def check_launcher_results() -> Tuple[bool, str]:
    """Check launcher_results.json to ensure API keys were properly validated.

    Returns:
        Tuple[bool, str]: (success, error_message)
    """
    try:
        results_path = os.path.join(user_data_dir, "launcher_results.json")
        if not os.path.exists(results_path):
            return (
                False,
                "launcher_results.json not found. Please run the launcher first.",
            )

        with open(results_path, "r") as f:
            results = json.load(f)

        # Check bithuman_key status
        if "bithuman_key" not in results:
            return False, "bithuman_key data not found in launcher results."

        if results["bithuman_key"].get("status") != "success":
            return (
                False,
                f"bitHuman API key verification failed: {results['bithuman_key'].get('message', 'Unknown error')}",
            )

        return True, ""
    except Exception as e:
        return False, f"Error checking launcher results: {str(e)}"


def get_model_loader() -> ModelLoader:
    """Get the global model loader instance.

    This function provides access to the shared model_loader instance
    to avoid passing it explicitly between components. It's used by
    other modules like api_server.py to access model operations.

    Returns:
        The global ModelLoader instance, or None if not initialized
    """
    global model_loader
    return model_loader


def get_server_port(specified_port: Optional[int] = None) -> int:
    """Get server port from settings or use specified port.

    Args:
        specified_port: Optional port specified by user

    Returns:
        Port number to use for the server

    Raises:
        RuntimeError: If no port can be determined
    """
    # First priority: specified port
    if specified_port is not None:
        return specified_port

    # Second priority: port from settings
    port = assets_manager.get_setting("server.port")
    if port is not None:
        return port

    # Third priority: default port range
    start_port = assets_manager.get_setting("server.minPort", 5001)
    max_port = assets_manager.get_setting("server.maxPort", 5010)

    # Try to find an available port
    for port in range(start_port, max_port + 1):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("127.0.0.1", port))
                # We can't update settings anymore since set_setting was removed
                return port
            except OSError:
                continue  # Port is in use, try next one

    # If we get here, no ports were available
    raise RuntimeError(f"No available ports found between {start_port} and {max_port}")


def wait_for_server_ready(port: int, timeout: int = 30) -> bool:
    """Wait until the server is ready to accept connections.

    Args:
        port: The port to check
        timeout: Maximum time to wait in seconds

    Returns:
        True if the server is ready, False if timed out
    """
    start_time = time.time()
    # Poll until timeout
    while time.time() - start_time < timeout:
        try:
            # Try both health endpoint and status endpoint
            conn = http.client.HTTPConnection(f"127.0.0.1:{port}", timeout=1)

            # First try /health endpoint (less likely to conflict)
            try:
                conn.request("GET", "/health")
                response = conn.getresponse()
                if response.status == 200:
                    log_server("Server health check successful")
                    return True
            except Exception:
                pass  # Fall back to API status

            # Fall back to the standard API status endpoint
            try:
                conn = http.client.HTTPConnection(f"127.0.0.1:{port}", timeout=1)
                conn.request("GET", "/api/status")
                response = conn.getresponse()
                if response.status == 200:
                    data = json.loads(response.read().decode("utf-8"))
                    log_server(
                        f"Server API status check successful: {data.get('is_ready', False)}"
                    )
                    return True
            except Exception:
                pass
        except Exception:
            pass

        # Wait before next attempt
        time.sleep(1)
        system(f"Waiting for server to be ready... ({int(time.time() - start_time)}s)")

    # Timeout reached
    return False


def resolve_model_path(model_path: Optional[str] = None) -> str:
    """Resolve the path to the model file based on settings or argument.

    Args:
        model_path: Optional explicit model path to use

    Returns:
        Path to the model file

    Raises:
        FileNotFoundError: If the model file cannot be found
    """
    # First priority: explicit model path argument
    if model_path is not None:
        if os.path.exists(model_path):
            model(f"Using provided model path: {model_path}")
            return model_path
        else:
            warning(f"Provided model path not found: {model_path}", LogCategory.MODEL)
            # Continue to other options

    # Get settings
    settings = assets_manager.load_settings()

    # Second priority: model from settings
    if settings.get("model"):
        settings_model = settings["model"]

        # Resolve the full path to the model
        model_file_path = os.path.join(
            user_data_dir, "assets", "models", settings_model
        )

        # Add .imx extension if needed
        if not os.path.exists(model_file_path) and not settings_model.endswith(".imx"):
            model_file_path = os.path.join(
                user_data_dir, "assets", "models", f"{settings_model}.imx"
            )

        if os.path.exists(model_file_path):
            model_path = model_file_path
            model(f"Using model from settings.json: {settings_model}")
            return model_path

    # Third priority: default model
    default_model = assets_manager.get_setting(
        "assets.defaultModel", "albert_einstein.imx"
    )
    model_path = os.path.join(user_data_dir, "assets", "models", default_model)

    if settings.get("model"):
        warning(
            f"Model '{settings.get('model')}' not found, using default: {default_model}",
            LogCategory.MODEL,
        )
    else:
        model(f"Using default model: {default_model}")

    if os.path.exists(model_path):
        return model_path

    # If we get here, no valid model was found
    raise FileNotFoundError(f"No valid model file found. Checked: {model_path}")


#############################
# Signal Handling
#############################


def signal_handler(signum, frame):
    """Handle termination signals (SIGINT, SIGTERM).

    Ensures graceful shutdown of all processes when the application
    receives a termination signal.

    Args:
        signum: Signal number
        frame: Current stack frame
    """
    global shutting_down
    # Prevent multiple shutdown attempts
    if shutting_down:
        return

    system("\nShutting down...")
    shutting_down = True
    shutdown_event.set()

    # Force exit after a timeout if clean shutdown is taking too long
    def force_exit_after_timeout():
        """Force exit if clean shutdown takes too long."""
        time.sleep(10)  # Give clean shutdown 10 seconds
        system("Forcing exit...")
        os._exit(0)

    # Start a thread to force exit if clean shutdown takes too long
    force_exit_thread = threading.Thread(target=force_exit_after_timeout)
    force_exit_thread.daemon = True
    force_exit_thread.start()


#############################
# Server Management
#############################


class ApplicationManager:
    """Manages the lifecycle of the Visual Agent application.

    This class encapsulates the application state and operations, providing
    a structured approach to component initialization, runtime management,
    and graceful shutdown. It separates the application into distinct phases:

    1. Setup phase: Initialize components and load model
    2. Runtime phase: Handle events and maintain application state
    3. Cleanup phase: Release resources and perform graceful shutdown

    The ApplicationManager is the core orchestrator of the daemon process,
    responsible for coordinating all the components, including the Flask server,
    SocketIO communications, model loading, and UI state management.
    """

    def __init__(self, model_path: Optional[str] = None, port: Optional[int] = None):
        """Initialize the application manager.

        Args:
            model_path: Path to the Visual Agent model file (.imx)
            port: Port to use for the web server
        """
        # Store configuration
        self.model_path = model_path
        self.port = port if port is not None else get_server_port()
        self.api_secret = assets_manager.get_api_key("bithuman")

        # Runtime state
        self.stop_event = threading.Event()
        self.server_threads = []
        self.socketio_instance = None
        self.flask_app = None

    async def setup(self) -> Tuple[bool, Optional[str]]:
        """Set up the application components.

        Returns:
            Tuple of (success, error_message)
        """
        global model_loader, _logging_configured, _logging_lock

        try:
            system("Setting up application components")

            # Configure logging only once (thread-safe)
            with _logging_lock:
                if not _logging_configured:
                    configure_logging()
                    _logging_configured = True

            # Initialize HTTP context for API communication
            system("Initializing HTTP context")
            utils.http_context._new_session_ctx()

            # Create and initialize the model loader
            system("Creating model loader")
            model_loader = ModelLoader()
            system(f"Model loader initialized: {model_loader}")

            # Create web application
            system("Creating Flask application")
            self.flask_app, self.socketio_instance = create_app(model_loader)

            # Set Flask app and SocketIO in the model loader
            model_loader.set_flask_app(self.flask_app, self.socketio_instance)

            # Configure web server endpoints
            self._configure_web_server()

            # Start web server thread
            system(f"Starting web server on port {self.port}")
            self._start_web_server()

            # Allow time for the server to start up
            time.sleep(1)

            # Initialize the model
            system(f"Initializing model: {self.model_path}")
            success, error_msg = await model_loader.initialize_model(
                self.model_path, api_secret=self.api_secret
            )

            if not success:
                return False, error_msg

            # Configure video player with server information
            if (
                hasattr(model_loader, "current_video_player")
                and model_loader.current_video_player
            ):
                ui("Configuring frame streamer...")
                video_player = model_loader.current_video_player
                # Update auto_open_browser property
                video_player.auto_open_browser = False
                # Set port and server
                video_player._port = self.port
                video_player._server = self.socketio_instance
                ui(f"Frame streamer configured to use port {self.port}")

                # Initialize socketio for video player
                init_socketio(self.socketio_instance)

            # Start UI state manager
            self._start_ui_state_manager()

            # Start status monitor
            self._start_status_monitor()

            return True, None

        except Exception as e:
            error_msg = f"Setup failed: {str(e)}"
            error(error_msg, LogCategory.SYSTEM)
            traceback.print_exc()
            return False, error_msg

    def _configure_web_server(self):
        """Configure web server endpoints and event handlers."""
        socketio = self.socketio_instance
        app = self.flask_app

        # Define a utility function to handle Werkzeug errors in socket emissions
        def safe_emit(socket_instance, event, data, **kwargs):
            """Safely emit SocketIO events, suppressing common Werkzeug errors."""
            try:
                socket_instance.emit(event, data, **kwargs)
            except AssertionError as e:
                # Handle the specific error we know is benign
                if "write() before start_response" in str(e):
                    log_server(f"Suppressed Werkzeug error: {e}")
                else:
                    # Re-raise other assertion errors
                    raise
            except Exception as e:
                error(f"Error in socket emission: {e}", LogCategory.SERVER)

        # ===== SocketIO Event Handlers =====
        # Add SocketIO event handlers for client connections
        @socketio.on("connect")
        def handle_connect():
            """Handle new client connections to the SocketIO server."""
            log_server("Client connected to socketio")
            # Get the request from the socket context
            from flask import request as flask_request

            # Send welcome message to verify connection
            safe_emit(
                socketio, "server_message", {"message": "Welcome from the server!"}
            )

            # Send current status to the newly connected client
            try:
                status = model_loader.get_status()
                client_id = flask_request.sid if hasattr(flask_request, "sid") else None
                if client_id:
                    # Send to specific client if we have its ID
                    safe_emit(socketio, "status-update", status, to=client_id)
                    # Also send loading state
                    is_loading = status.get("is_reloading", False) or not status.get(
                        "is_ready", False
                    )
                    safe_emit(socketio, "loading-state", is_loading, to=client_id)
                else:
                    # Broadcast to all clients if no client ID available
                    safe_emit(socketio, "status-update", status)
                    safe_emit(socketio, "loading-state", is_loading)
            except Exception as e:
                error(
                    f"Error sending initial status to client: {e}", LogCategory.SERVER
                )

        @socketio.on("disconnect")
        def handle_disconnect():
            """Handle client disconnection from the SocketIO server."""
            log_server("Client disconnected from socketio")
            # Clean up resources for disconnected client
            try:
                # Get the request from the socket context
                from flask import request as flask_request

                # Clean up session to prevent issues with Werkzeug
                if hasattr(flask_request, "sid"):
                    log_server(f"Cleaning up session for client {flask_request.sid}")
            except Exception as e:
                error(f"Error cleaning up client session: {e}", LogCategory.SERVER)

        @socketio.on("log_message")
        def handle_log_message(message):
            """Handle log messages from clients for debugging."""
            log_server(f"Client message: {message}")
            # Echo back to confirm receipt
            socketio.emit("log_receipt", {"received": message})

        # Add custom endpoints
        try:
            # Check existing routes to avoid adding duplicates
            existing_routes = [str(rule.rule) for rule in app.url_map.iter_rules()]

            if "/health" not in existing_routes:

                @app.route("/health")
                def health_check():
                    """Health check endpoint for monitoring."""
                    return {"status": "ok", "uptime": time.time()}

            if "/api/constants" not in existing_routes:

                @app.route("/api/constants")
                def get_constants():
                    """Provide constants and config values to clients."""
                    settings = assets_manager.load_settings()
                    return {
                        "default_model_path": settings.get("assets", {}).get(
                            "defaultModel", ""
                        ),
                        "default_image_path": settings.get("assets", {}).get(
                            "defaultImage", ""
                        ),
                    }
        except Exception as e:
            warning(f"Error checking routes: {e}", LogCategory.SERVER)

    def _start_web_server(self):
        """Start the Flask/SocketIO web server in a separate thread."""

        def run_flask_server():
            log_server(f"Starting Flask server on port {self.port}...")
            try:
                # Configure SocketIO with optimal settings
                self.socketio_instance.init_app(
                    self.flask_app,
                    cors_allowed_origins="*",  # Allow all origins for development
                    async_mode="threading",  # Use threading mode for reliability
                    ping_timeout=60,  # Longer timeout for stable connections
                    ping_interval=25,  # More frequent pings for faster disconnection detection
                    max_http_buffer_size=100
                    * 1024
                    * 1024,  # Allow large buffer for video frames
                    logger=False,  # Disable default logger
                    engineio_logger=False,  # Disable engineio logger
                )

                # Start the server
                self.socketio_instance.run(
                    self.flask_app,
                    host="127.0.0.1",
                    port=self.port,
                    debug=False,
                    use_reloader=False,
                    allow_unsafe_werkzeug=True,
                )
            except Exception as e:
                error(f"Error in Flask server: {e}", LogCategory.SERVER)
                traceback.print_exc()

        # Create and start the Flask server thread
        flask_thread = threading.Thread(target=run_flask_server)
        flask_thread.daemon = True
        flask_thread.start()
        self.server_threads.append(flask_thread)

    def _start_ui_state_manager(self):
        """Start a thread to manage and update UI loading states."""

        def manage_loading_state():
            try:
                # Wait a bit to ensure the app is ready
                time.sleep(2)

                # Set initial loading state to true
                ui("Setting initial loading state to true...")
                try:
                    # Use the model loader's safe emit method
                    model_loader._emit_socketio_event("loading-state", True)
                except Exception as e:
                    error(f"Error emitting initial loading state: {e}", LogCategory.UI)

                # Monitor loading state and update UI
                is_loading_cleared = False
                while not self.stop_event.is_set() and not shutdown_event.is_set():
                    try:
                        # Get current model status
                        status = model_loader.get_status()
                        is_ready = status.get("is_ready", False)
                        is_reloading = status.get("is_reloading", False)

                        # Model is ready and not currently reloading
                        if is_ready and not is_reloading and not is_loading_cleared:
                            ui("Model is ready, setting loading state to false")
                            try:
                                # Use model loader's safe emit method
                                model_loader._emit_socketio_event(
                                    "loading-state", False
                                )
                                is_loading_cleared = True
                            except Exception as e:
                                error(
                                    f"Error emitting ready state: {e}", LogCategory.UI
                                )
                        # Model was ready but is now reloading
                        elif is_reloading and is_loading_cleared:
                            ui("Model is reloading, setting loading state to true")
                            try:
                                # Use model loader's safe emit method
                                model_loader._emit_socketio_event("loading-state", True)
                                is_loading_cleared = False
                            except Exception as e:
                                error(
                                    f"Error emitting reloading state: {e}",
                                    LogCategory.UI,
                                )
                    except Exception as e:
                        error(f"Error checking model status: {e}", LogCategory.MODEL)
                    # Check status periodically
                    time.sleep(0.5)
            except Exception as e:
                error(f"Error in loading state manager: {e}", LogCategory.UI)

        # Create and start the thread
        loading_thread = threading.Thread(target=manage_loading_state)
        loading_thread.daemon = True
        loading_thread.start()
        self.server_threads.append(loading_thread)

    def _start_status_monitor(self):
        """Start a thread for periodic status logging."""

        def print_status():
            while not self.stop_event.is_set() and not shutdown_event.is_set():
                system("Server is running...", level="DEBUG")
                time.sleep(30)  # Print status every 30 seconds

        # Create and start the thread
        status_thread = threading.Thread(target=print_status)
        status_thread.daemon = True
        status_thread.start()
        self.server_threads.append(status_thread)

    async def start_reload_handler(self):
        """Start the model reload event handler."""
        system("Starting reload event handler")
        # Create a task to handle reload events in the background
        asyncio_stop_event = asyncio.Event()

        # Create a thread to monitor the stop events
        def monitor_stop_events():
            while not self.stop_event.is_set() and not shutdown_event.is_set():
                time.sleep(0.5)

            # Set the asyncio event when stop is requested
            loop = asyncio.new_event_loop()
            loop.run_until_complete(asyncio_stop_event.set())
            loop.close()

        # Start the monitor thread
        monitor_thread = threading.Thread(target=monitor_stop_events)
        monitor_thread.daemon = True
        monitor_thread.start()
        self.server_threads.append(monitor_thread)

        # Start the reload handler
        return await model_loader.handle_reload_events(asyncio_stop_event)

    async def run(self):
        """Run the application main loop."""
        system("Starting main application loop")
        try:
            # Wait for the server to be ready
            if not wait_for_server_ready(self.port):
                error(
                    "Server failed to start within the timeout period",
                    LogCategory.SERVER,
                )
                self.stop_event.set()
                return False

            # Print server info for external clients to connect
            log_server(f"Server is ready on port {self.port}")
            system(f"Daemon server running at: http://127.0.0.1:{self.port}")
            system("Press Ctrl+C to stop the server")

            # Start the reload handler
            await self.start_reload_handler()

            # Keep running until shutdown is requested
            while not self.stop_event.is_set() and not shutdown_event.is_set():
                await asyncio.sleep(0.5)

            return True

        except asyncio.CancelledError:
            system("Received cancellation signal")
            return True
        except Exception as e:
            error(f"Error during application run: {e}", LogCategory.SYSTEM)
            traceback.print_exc()
            return False

    async def cleanup(self):
        """Clean up resources before application exit."""
        system("Cleaning up resources")

        try:
            # Clean up model loader resources
            if model_loader:
                system("Cleaning up model loader")
                await model_loader.cleanup()

            system("Cleanup completed")
        except Exception as e:
            error(f"Error during cleanup: {e}", LogCategory.SYSTEM)
            traceback.print_exc()


#############################
# Main Application Functions
#############################


async def async_main(model_path: Optional[str] = None, port: Optional[int] = None):
    """Main async entry point for the daemon.

    Args:
        model_path: Path to the model file
        port: Port to use for the server

    Returns:
        Exit code (0 for success, non-zero for error)
    """
    try:
        # Check launcher results first
        success, error_msg = check_launcher_results()
        if not success:
            error(error_msg, LogCategory.SYSTEM)
            return 1

        # Resolve model path
        resolved_model_path = resolve_model_path(model_path)

        # Print basic information
        system(f"Starting daemon with model: {resolved_model_path}")

        # Create and initialize the application manager
        app_manager = ApplicationManager(model_path=resolved_model_path, port=port)

        # Setup the application
        success, error_msg = await app_manager.setup()
        if not success:
            error(f"Setup failed: {error_msg}", LogCategory.SYSTEM)
            return 1

        # Run the application
        if not await app_manager.run():
            return 1

        return 0

    except FileNotFoundError as e:
        error(str(e), LogCategory.MODEL)
        return 1
    except KeyboardInterrupt:
        system("Received keyboard interrupt")
        return 0
    except Exception as e:
        error(f"Unexpected error: {e}", LogCategory.SYSTEM)
        traceback.print_exc()
        return 1
    finally:
        # Ensure cleanup happens if app_manager was created
        if "app_manager" in locals():
            await app_manager.cleanup()


def run_daemon(
    model_path: Optional[str] = None, port: Optional[int] = None, verbose: bool = False
) -> int:
    """Run the daemon with the specified configuration.

    This is the primary public function for starting the daemon.
    It handles running the server after the launcher has prepared the environment.

    Args:
        model_path: Optional path to the Visual Agent model
        port: Optional port to use for the server
        verbose: Enable verbose logging

    Returns:
        Exit code (0 for success, non-zero for error)
    """
    # Register signal handlers for clean shutdown
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Configure logging
    global _logging_configured, _logging_lock
    log_level = "DEBUG" if verbose else "INFO"
    with _logging_lock:
        if not _logging_configured:
            configure_logging(level=log_level)
            _logging_configured = True
            system(f"Daemon logging configured with level: {log_level}")

    try:
        # Run the async main function in a new event loop
        return asyncio.run(async_main(model_path=model_path, port=port))
    except KeyboardInterrupt:
        # Handle CTRL+C at the top level
        return 0
    except Exception as e:
        # Log any unhandled exceptions and exit
        error(f"Fatal error: {e}", LogCategory.SYSTEM)
        traceback.print_exc()
        return 1


#############################
# Script Entry Point
#############################

if __name__ == "__main__":
    try:
        # Parse command line arguments
        parser = argparse.ArgumentParser(description="bitHuman Visual Agent Daemon")
        parser.add_argument("--port", type=int, help="Specify port for the server")
        parser.add_argument("--model", help="Path to the model file")
        parser.add_argument(
            "--verbose", "-v", action="store_true", help="Enable verbose logging"
        )
        args = parser.parse_args()

        # Run the daemon with parsed arguments
        exit_code = run_daemon(
            model_path=args.model, port=args.port, verbose=args.verbose
        )
        sys.exit(exit_code)
    except Exception as e:
        print(f"Fatal error starting daemon: {str(e)}")
        traceback.print_exc()
        sys.exit(1)
