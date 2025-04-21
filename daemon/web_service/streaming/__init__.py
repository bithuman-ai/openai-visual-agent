"""Streaming modules for the bitHuman Visual Agent.

This package contains the modules responsible for streaming video frames and
handling real-time communication with clients via SocketIO.
"""

from .frame_streamer import WebFrameStreamer

__all__ = ["WebFrameStreamer"]
