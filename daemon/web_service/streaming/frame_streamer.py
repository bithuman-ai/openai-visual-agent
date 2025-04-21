"""Frame streaming module for the bitHuman Visual Agent.

This module provides classes for streaming video frames to clients via SocketIO.
"""

import base64
import time
from io import BytesIO
from typing import Any

import numpy as np
from PIL import Image

from bithuman.utils.agent import VideoFrame, VideoOutput
from daemon.utils.helpers import safe_emit
from daemon.utils.logging import LogCategory, error, ui, warning


class WebFrameStreamer(VideoOutput):
    """
    Stream frames to web clients via SocketIO.

    This class handles:
    1. Converting frames to JPEG format
    2. Base64 encoding frames for transmission
    3. Sending frames to connected clients via SocketIO
    """

    def __init__(
        self,
        window_title: str = "Visual Agent",
        quality: int = 85,
        max_fps: int = 30,
        auto_open_browser: bool = True,
    ):
        """
        Initialize the web frame streamer.

        Args:
            window_title: Title for the browser window
            quality: JPEG quality (1-100)
            max_fps: Maximum frames per second to stream
            auto_open_browser: Whether to automatically open a browser window
        """
        super().__init__()
        self.active = False
        self.window_title = window_title
        self.quality = quality
        self.max_fps = max_fps
        self.frame_count = 0
        self.auto_open_browser = auto_open_browser
        self._port = None
        self._server = None

        ui(f"Initialized web frame streamer with quality={quality}, max_fps={max_fps}")

    def start(self):
        """Start the frame streamer."""
        self.active = True
        ui("Started web frame streamer")
        # Get socketio instance on demand only when needed
        if self._server is None:
            # Import here to avoid circular import
            from daemon.web_service.server import get_socketio

            self._server = get_socketio()

        # If we need to open the browser automatically
        if self.auto_open_browser and self._port:
            try:
                import webbrowser

                url = f"http://localhost:{self._port}"
                ui(f"Opening browser to {url}")
                webbrowser.open(url)
            except Exception as e:
                warning(f"Could not open browser: {e}", LogCategory.UI)

    def stop(self):
        """Stop the frame streamer."""
        self.active = False
        ui("Stopped web frame streamer")

    async def capture_frame(
        self, frame: VideoFrame, fps: float, exp_time: float
    ) -> None:
        """Capture a video frame and send it to connected clients."""
        if not frame.has_image:
            return
        self.handle_frame(frame.rgb_image, {"fps": fps, "exp_time": exp_time})

    def buffer_empty(self) -> bool:
        """Check if the buffer is empty."""
        return True

    def handle_frame(self, frame: np.ndarray, metadata: dict[str, Any] = None) -> bool:
        """
        Process and stream a video frame to connected clients.

        Args:
            frame: The frame as a numpy array (RGB format)
            metadata: Additional metadata to include with the frame

        Returns:
            Boolean indicating success
        """
        if not self.active:
            return False

        try:
            # Get socketio instance on demand to avoid circular import
            if self._server is None:
                # Import here to avoid circular import
                from daemon.web_service.server import get_socketio

                self._server = get_socketio()

            # Check if we have a server connection
            if not self._server:
                warning(
                    "No SocketIO server available, can't send frame", LogCategory.UI
                )
                return False

            # Convert to PIL Image
            pil_img = Image.fromarray(frame)

            # Save as JPEG to buffer
            buffer = BytesIO()
            pil_img.save(buffer, format="JPEG", quality=self.quality, optimize=True)

            # Get the bytes and encode as base64
            img_bytes = buffer.getvalue()
            base64_img = base64.b64encode(img_bytes).decode("utf-8")

            # Prepare metadata to include with the frame
            emit_data = {
                "frame": base64_img,
                "fps": 0,
                "time": time.time(),
                "exp_time": 0,
            }

            # Add any custom metadata
            if metadata:
                emit_data.update(metadata)

            # Emit the frame to connected clients
            safe_emit(self._server, "frame", emit_data)

            return True

        except Exception as e:
            error(f"Error streaming frame: {e}", LogCategory.UI)
            import traceback

            error(traceback.format_exc(), LogCategory.UI)
            return False
