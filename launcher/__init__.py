"""bitHuman Visual Agent Launcher Package.

This package handles the environment verification and initialization for the bitHuman Visual Agent application.
"""

from launcher.assets_manager import AssetsManager, SettingsManager
from launcher.logging import (
    Colors,
    LogCategory,
    format_command,
    format_error,
    format_header,
    format_info,
    format_path,
    format_section,
    format_success,
    format_value,
    format_warning,
    log_assets,
    log_config,
    log_debug,
    log_network,
    log_security,
    log_system,
    setup_logging,
)
from launcher.main import launch_app

__all__ = [
    # Main functionality
    "launch_app",
    # Logging utilities
    "setup_logging",
    "log_system",
    "log_assets",
    "log_network",
    "log_config",
    "log_security",
    "log_debug",
    "format_header",
    "format_section",
    "format_success",
    "format_error",
    "format_warning",
    "format_info",
    "format_command",
    "format_path",
    "format_value",
    "Colors",
    "LogCategory",
    # Asset management utilities
    "AssetsManager",
    "SettingsManager",
]
