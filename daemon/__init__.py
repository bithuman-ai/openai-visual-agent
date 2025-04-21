"""bitHuman Visual Agent daemon package.

This package provides the runtime environment for Visual Agent capabilities.
"""

import os
import sys

# Make sure daemon directory is in path
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

# Import the main functionality
from daemon.main import run_daemon

# Import logging utilities
from daemon.utils.logging import (
    LogCategory,
    configure_logging,
    debug,
    error,
    info,
    model,
    server,
    system,
    ui,
    warning,
)

# Export all interfaces
__all__ = [
    "run_daemon",
    "LogCategory",
    "configure_logging",
    "info",
    "debug",
    "warning",
    "error",
    "system",
    "model",
    "ui",
    "server",
]

# Set the package version
__version__ = "0.1.0"

# Package metadata
__author__ = "bitHuman"
__email__ = "info@bithuman.ai"
__license__ = "Proprietary"
