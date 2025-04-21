"""
Logging utilities for the launcher module.

This module provides colorful, categorized logging functionality.
"""

import logging
import sys
import threading
from enum import Enum, auto


# ANSI color codes for pretty terminal output
class Colors:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    UNDERLINE = "\033[4m"

    # Foreground colors
    BLACK = "\033[30m"
    RED = "\033[31m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    BLUE = "\033[34m"
    MAGENTA = "\033[35m"
    CYAN = "\033[36m"
    WHITE = "\033[37m"

    # Background colors
    BG_BLACK = "\033[40m"
    BG_RED = "\033[41m"
    BG_GREEN = "\033[42m"
    BG_YELLOW = "\033[43m"
    BG_BLUE = "\033[44m"
    BG_MAGENTA = "\033[45m"
    BG_CYAN = "\033[46m"
    BG_WHITE = "\033[47m"

    # Bright variants
    BRIGHT_BLACK = "\033[90m"
    BRIGHT_RED = "\033[91m"
    BRIGHT_GREEN = "\033[92m"
    BRIGHT_YELLOW = "\033[93m"
    BRIGHT_BLUE = "\033[94m"
    BRIGHT_MAGENTA = "\033[95m"
    BRIGHT_CYAN = "\033[96m"
    BRIGHT_WHITE = "\033[97m"


class LogCategory(Enum):
    """Log categories for better organization and coloring"""

    SYSTEM = auto()
    ASSETS = auto()
    NETWORK = auto()
    CONFIG = auto()
    SECURITY = auto()
    DEBUG = auto()


class ColorfulFormatter(logging.Formatter):
    """A custom formatter that adds colors and categories to logs"""

    CATEGORY_COLORS = {
        LogCategory.SYSTEM: Colors.CYAN,
        LogCategory.ASSETS: Colors.MAGENTA,
        LogCategory.NETWORK: Colors.YELLOW,
        LogCategory.CONFIG: Colors.GREEN,
        LogCategory.SECURITY: Colors.RED,
        LogCategory.DEBUG: Colors.BRIGHT_BLACK,
    }

    LEVEL_COLORS = {
        logging.DEBUG: Colors.BRIGHT_BLACK,
        logging.INFO: Colors.WHITE,
        logging.WARNING: Colors.YELLOW,
        logging.ERROR: Colors.RED,
        logging.CRITICAL: Colors.BG_RED + Colors.WHITE,
    }

    def __init__(self, use_colors=True):
        super().__init__(
            fmt="%(asctime)s | %(levelname)-8s | %(message)s", datefmt="%H:%M:%S"
        )
        self.use_colors = use_colors

    def format(self, record):
        # Store the original message
        original_msg = record.msg
        levelname = record.levelname

        # Check if category is in extra
        category = None
        if hasattr(record, "category"):
            category = record.category

        # Apply colors if enabled
        if self.use_colors:
            # Color for the level
            level_color = self.LEVEL_COLORS.get(record.levelno, Colors.WHITE)

            # Format the level name with color
            record.levelname = f"{level_color}{levelname}{Colors.RESET}"

            # Add category with color if provided
            if category:
                category_color = self.CATEGORY_COLORS.get(category, Colors.WHITE)
                category_name = category.name.ljust(8)
                record.msg = (
                    f"{category_color}[{category_name}]{Colors.RESET} {record.msg}"
                )
        elif category:
            # No colors, but still add the category
            category_name = category.name.ljust(8)
            record.msg = f"[{category_name}] {record.msg}"

        # Format the record
        result = super().format(record)

        # Restore the original message
        record.msg = original_msg
        record.levelname = levelname

        return result


# Create a custom logger
logger = logging.getLogger("launcher")
logger.setLevel(logging.INFO)

# Create a console handler and set its formatter
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setFormatter(ColorfulFormatter(use_colors=True))
logger.addHandler(console_handler)

# Remove the default handlers that basicConfig might have added
for handler in logging.root.handlers[:]:
    logging.root.removeHandler(handler)

# Thread-safe logging configuration
_logging_lock = threading.Lock()


# Helper functions for easier category-based logging
def log_system(message, level=logging.INFO):
    logger._log(level, message, (), extra={"category": LogCategory.SYSTEM})


def log_assets(message, level=logging.INFO):
    logger._log(level, message, (), extra={"category": LogCategory.ASSETS})


def log_network(message, level=logging.INFO):
    logger._log(level, message, (), extra={"category": LogCategory.NETWORK})


def log_config(message, level=logging.INFO):
    logger._log(level, message, (), extra={"category": LogCategory.CONFIG})


def log_security(message, level=logging.INFO):
    logger._log(level, message, (), extra={"category": LogCategory.SECURITY})


def log_debug(message):
    logger._log(logging.DEBUG, message, (), extra={"category": LogCategory.DEBUG})


# Utility functions for colorful text formatting
def format_header(text, width=60):
    """Format a header with background color and padding."""
    padding = (width - len(text)) // 2
    return f"{Colors.BG_BLUE}{Colors.WHITE}{Colors.BOLD} {' ' * padding}{text}{' ' * padding} {Colors.RESET}"


def format_section(text="", char="─", width=60):
    """Format a section divider with color."""
    return f"{Colors.CYAN}{char * width}{Colors.RESET}"


def format_success(text):
    """Format a success message."""
    return f"{Colors.GREEN}✅ {text}{Colors.RESET}"


def format_error(text):
    """Format an error message."""
    return f"{Colors.RED}❌ {text}{Colors.RESET}"


def format_warning(text):
    """Format a warning message."""
    return f"{Colors.YELLOW}⚠️ {text}{Colors.RESET}"


def format_info(text):
    """Format an info message."""
    return f"{Colors.BLUE}ℹ️ {text}{Colors.RESET}"


def format_command(text):
    """Format a command."""
    return f"{Colors.YELLOW}$ {text}{Colors.RESET}"


def format_path(text):
    """Format a file path."""
    return f"{Colors.BRIGHT_BLACK}📁 {text}{Colors.RESET}"


def format_value(text, status="normal"):
    """Format a value based on its status."""
    if status == "success":
        return f"{Colors.GREEN}{text}{Colors.RESET}"
    elif status == "error":
        return f"{Colors.RED}{text}{Colors.RESET}"
    elif status == "warning":
        return f"{Colors.YELLOW}{text}{Colors.RESET}"
    else:
        return f"{Colors.WHITE}{text}{Colors.RESET}"


# Initialize the logger
def setup_logging(verbose=False, settings=None):
    """Setup logging with appropriate level based on verbose flag and settings.

    Args:
        verbose: Whether to enable debug logging
        settings: Optional settings dictionary with logging configuration
    """
    # Default to INFO level
    log_level = logging.INFO

    # Override with settings if available
    if settings:
        if verbose:
            # Verbose flag takes precedence
            log_level = logging.DEBUG
        else:
            # Get log level from settings
            level_str = settings.get("logs", {}).get("logLevel", "INFO")
            # Convert string level to logging constant
            if level_str == "DEBUG":
                log_level = logging.DEBUG
            elif level_str == "INFO":
                log_level = logging.INFO
            elif level_str == "WARNING":
                log_level = logging.WARNING
            elif level_str == "ERROR":
                log_level = logging.ERROR
            elif level_str == "CRITICAL":
                log_level = logging.CRITICAL

        # Configure file logging if enabled in settings
        if settings.get("logs", {}).get("logToFile", False):
            import os
            from logging.handlers import RotatingFileHandler

            # Get log directory and create if it doesn't exist
            log_dir = os.path.join(
                settings.get("user_data_dir", ""),
                settings.get("logs", {}).get("logDir", "logs"),
            )
            os.makedirs(log_dir, exist_ok=True)

            # Configure rotating file handler
            log_file = os.path.join(log_dir, "launcher.log")
            max_bytes = settings.get("logs", {}).get("maxLogSizeMB", 10) * 1024 * 1024
            backup_count = settings.get("logs", {}).get("backupCount", 5)

            file_handler = RotatingFileHandler(
                log_file, maxBytes=max_bytes, backupCount=backup_count
            )
            file_handler.setFormatter(ColorfulFormatter(use_colors=False))
            logger.addHandler(file_handler)
    elif verbose:
        # If no settings but verbose flag is set
        log_level = logging.DEBUG

    # Set the log level
    logger.setLevel(log_level)

    # Log the configuration
    if log_level == logging.DEBUG:
        log_debug("Verbose logging enabled")
