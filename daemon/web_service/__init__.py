"""Web Service module for the bitHuman Visual Agent Application.

This module provides the REST API and WebSocket interfaces for the Visual Agent,
organized into logical components:

- server: Core Flask/SocketIO server implementation
- endpoints: API endpoint modules for different functional areas
- streaming: Components for streaming frames to clients
- utils: Utility functions for the web service
- templates: HTML templates for web interfaces

The main entry point is the create_app() function in the server module,
which initializes the Flask application and SocketIO server.
"""

from .server import create_app, get_socketio, init_socketio
from .streaming import WebFrameStreamer

__all__ = [
    "create_app",
    "get_socketio",
    "init_socketio",
    "WebFrameStreamer",
]
