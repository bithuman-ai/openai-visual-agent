"""Unified logging configuration for bitHuman Visual Agent application.

This module provides a centralized, aesthetically pleasing logging system with
consistent formatting and appropriate filtering for different components.
"""

import logging
import os
import sys
import threading
import time
from enum import Enum
from typing import Optional

# Import loguru if available, otherwise fall back to standard logging
try:
    from loguru import logger

    USING_LOGURU = True
except ImportError:
    import logging as logger

    USING_LOGURU = False

# Flag to ensure we don't recursively set up logging
_is_setup_in_progress = threading.Event()

# Track recent messages to deduplicate logs (message → timestamp)
_recent_messages = {}
# Lock for thread-safe access to the recent messages
_recent_messages_lock = threading.Lock()
# Default deduplication timeout (in seconds)
_DEDUPE_TIMEOUT = 1.0


def should_log_message(message: str, level: str, category: str) -> bool:
    """Check if a message should be logged based on deduplication logic.

    Args:
        message: The message to log
        level: Log level
        category: Log category

    Returns:
        True if the message should be logged, False if it should be skipped
    """
    # Don't deduplicate ERROR or higher level messages
    if level in ["ERROR", "CRITICAL"]:
        return True

    # Create a unique key for this message
    message_key = f"{category}:{level}:{message}"
    current_time = time.time()

    with _recent_messages_lock:
        # Check if we've seen this message recently
        if message_key in _recent_messages:
            last_time = _recent_messages[message_key]
            if current_time - last_time < _DEDUPE_TIMEOUT:
                return False  # Skip if it's a duplicate within dedupe window

        # Update the last time we saw this message
        _recent_messages[message_key] = current_time

        # Clean up old messages
        for key in list(_recent_messages.keys()):
            if current_time - _recent_messages[key] > _DEDUPE_TIMEOUT:
                del _recent_messages[key]

    return True


# Log categories for better organization and filtering
class LogCategory(Enum):
    """Categories for logs to enable consistent styling and filtering."""

    SYSTEM = "SYSTEM"  # System-level events (startup, shutdown)
    SERVER = "SERVER"  # Web/API server events
    MODEL = "MODEL"  # Model loading/processing
    UI = "UI"  # User interface events
    NETWORK = "NETWORK"  # Network operations
    AUDIO = "AUDIO"  # Audio processing
    ELECTRON = "ELECTRON"  # Electron frontend
    DEBUG = "DEBUG"  # Debug information (only shown in debug mode)


# Simple format function that works reliably with loguru's colorize
def format_func(record):
    color_map = {
        "SYSTEM": "blue",
        "SERVER": "green",
        "MODEL": "magenta",
        "UI": "cyan",
        "NETWORK": "yellow",
        "AUDIO": "yellow",
        "ELECTRON": "magenta",
        "DEBUG": "white",
    }

    # Get extra data
    extra = record["extra"]
    category = extra.get("category", "")

    # If category is not in our map, use module name
    if not category or category not in color_map:
        module = record["name"].split(".")[-1].upper()
        category = module

        # Map common modules to our categories
        module_map = {
            "RUNTIME": "MODEL",
            "VIDEO_SCRIPT": "MODEL",
            "VIDEO_GRAPH": "MODEL",
            "AUDIO_PROCESSOR": "AUDIO",
            "UI_CONTROLLER": "UI",
            "APP": "SYSTEM",
        }
        if module in module_map:
            category = module_map[module]

    # Get color based on category
    color = color_map.get(category, "white")

    # Production vs development format
    try:
        from . import assets_manager

        is_production = assets_manager.get_server_mode() == "production"
    except (ImportError, AttributeError):
        # Fall back to development mode if assets_manager can't be imported
        is_production = False

    if is_production:
        time_format = "{time:HH:mm:ss}"
        module_part = ""
    else:
        time_format = "{time:YYYY-MM-DD HH:mm:ss}"
        module_part = " <cyan>{name:<25}</cyan> |"

    # Handle multi-line messages by replacing newlines with a special marker
    # that will help visually align the continuation lines
    message = record["message"]
    if "\n" in message:
        lines = message.split("\n")
        # Format the message with continuation markers for better readability
        message = lines[0]
        for line in lines[1:]:
            # Add a continuation marker to indent each line
            message += f"\n                               | {line}"
        record["message"] = message

    # Create a cleaner format string with fixed-width columns for better alignment
    # Use a fixed width for the category tag to ensure alignment
    return f"{time_format} | <{color}>[{category:<10}]</{color}> | <level>{{level:<8}}</level> |{module_part} {{message}}\n"


# Configure the logger with appropriate settings
def setup_logger(
    level: str = "INFO",
    is_production: bool = False,
    log_file: Optional[str] = None,
) -> None:
    """Set up the unified logger with appropriate configuration.

    Args:
        level: Minimum log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        is_production: If True, use more compact output format
        log_file: Optional path to write logs to file
    """
    global app_logger, _is_setup_in_progress

    # Prevent recursive setup
    if _is_setup_in_progress.is_set():
        return

    _is_setup_in_progress.set()

    try:
        # Get settings for mode and debug level, with parameters taking precedence
        from . import assets_manager

        is_production = (
            is_production or assets_manager.get_server_mode() == "production"
        )
        debug_mode = level.upper() == "DEBUG" or assets_manager.get_debug_mode()

        if USING_LOGURU:
            # Remove default loguru handler
            logger.remove()

            # Add stderr handler with appropriate level and format
            logger.add(
                sys.stderr,
                level=level,
                format=format_func,
                colorize=True,
                filter=lambda record: _category_filter(record, debug_mode),
            )

            # Add file handler if specified
            if log_file:
                # We need a custom format function for the file format to handle multi-line messages
                def file_format_func(record):
                    # Handle multi-line messages by adding continuation markers
                    message = record["message"]
                    if "\n" in message:
                        lines = message.split("\n")
                        # Format the message with continuation markers for better readability
                        message = lines[0]
                        for line in lines[1:]:
                            # Add a continuation marker to indent each line
                            message += f"\n                               | {line}"
                        record["message"] = message

                    # Return the formatted string
                    return "{time:YYYY-MM-DD HH:mm:ss} | [{extra[category]}] | {level: <8} | {name} | {message}\n"

                logger.add(
                    log_file,
                    level=level,
                    format=file_format_func,
                    rotation="10 MB",
                    retention="1 week",
                    compression="gz",
                )

            # Set up core logger
            app_logger = bitHumanLogger(logger)

        else:
            # Fallback to standard logging if loguru is not available
            logging.basicConfig(
                level=getattr(logging, level),
                format="%(asctime)s | [%(name)s] | %(levelname)-8s | %(message)s",
                handlers=[logging.StreamHandler(sys.stderr)],
            )

            if log_file:
                file_handler = logging.FileHandler(log_file)
                file_handler.setFormatter(
                    logging.Formatter(
                        "%(asctime)s | [%(name)s] | %(levelname)-8s | %(message)s"
                    )
                )
                logging.getLogger().addHandler(file_handler)

            # Create a simple logger
            app_logger = SimpleLogger()

        # Configure standard library loggers to be more restrictive
        configure_stdlib_loggers(is_production, debug_mode)

        # Set environment variable to suppress warnings
        os.environ["PYTHONWARNINGS"] = "ignore::UserWarning"

        # Log configuration complete using the logger directly
        if app_logger:
            app_logger.system(
                f"Logging configured in {'production' if is_production else 'development'} mode"
            )
    finally:
        _is_setup_in_progress.clear()


def _category_filter(record, debug_mode):
    """Filter records based on category and debug mode.

    Args:
        record: The log record
        debug_mode: Whether debug mode is enabled

    Returns:
        True if record should be shown, False otherwise
    """
    # Ensure the record has extras
    if not hasattr(record, "extra"):
        return True

    # Check if there's a category in extras
    if "category" not in record["extra"]:
        return True

    # If it's a debug category, only show in debug mode
    return record["extra"]["category"] != LogCategory.DEBUG.value or debug_mode


class bitHumanLogger:
    """bitHuman unified logger based on loguru."""

    def __init__(self, logger_instance):
        """Initialize with a logger instance.

        Args:
            logger_instance: The loguru logger instance
        """
        self._logger = logger_instance

    def _log(self, level: str, message: str, category: LogCategory, **kwargs) -> None:
        """Internal logging method with category and metadata.

        Args:
            level: Log level
            message: Log message
            category: Log category
            **kwargs: Additional metadata to include in the log
        """
        # Check if we should deduplicate this message
        if not should_log_message(message, level, category.value):
            return

        # Add category metadata for the log record
        extras = {"category": category.value}
        extras.update(kwargs)

        # Call the appropriate log level function with properly escaped message
        log_fn = getattr(self._logger, level.lower())

        # Always escape all curly braces in the message to prevent formatter exceptions
        # This ensures consistent behavior regardless of format specifiers or actual braces in text
        safe_message = message.replace("{", "{{").replace("}", "}}")

        # Send the escaped message to the logger
        log_fn(safe_message, **extras)

    # Define all the log methods
    def trace(
        self, message: str, category: LogCategory = LogCategory.DEBUG, **kwargs
    ) -> None:
        self._log("TRACE", message, category, **kwargs)

    def debug(
        self, message: str, category: LogCategory = LogCategory.DEBUG, **kwargs
    ) -> None:
        self._log("DEBUG", message, category, **kwargs)

    def info(
        self, message: str, category: LogCategory = LogCategory.SYSTEM, **kwargs
    ) -> None:
        self._log("INFO", message, category, **kwargs)

    def success(
        self, message: str, category: LogCategory = LogCategory.SYSTEM, **kwargs
    ) -> None:
        self._log("SUCCESS", message, category, **kwargs)

    def warning(
        self, message: str, category: LogCategory = LogCategory.SYSTEM, **kwargs
    ) -> None:
        self._log("WARNING", message, category, **kwargs)

    def error(
        self, message: str, category: LogCategory = LogCategory.SYSTEM, **kwargs
    ) -> None:
        self._log("ERROR", message, category, **kwargs)

    def critical(
        self, message: str, category: LogCategory = LogCategory.SYSTEM, **kwargs
    ) -> None:
        self._log("CRITICAL", message, category, **kwargs)

    # Convenience methods for different categories
    def system(self, message: str, level: str = "INFO", **kwargs) -> None:
        self._log(level, message, LogCategory.SYSTEM, **kwargs)

    def server(self, message: str, level: str = "INFO", **kwargs) -> None:
        self._log(level, message, LogCategory.SERVER, **kwargs)

    def model(self, message: str, level: str = "INFO", **kwargs) -> None:
        self._log(level, message, LogCategory.MODEL, **kwargs)

    def ui(self, message: str, level: str = "INFO", **kwargs) -> None:
        self._log(level, message, LogCategory.UI, **kwargs)

    def network(self, message: str, level: str = "INFO", **kwargs) -> None:
        self._log(level, message, LogCategory.NETWORK, **kwargs)

    def audio(self, message: str, level: str = "INFO", **kwargs) -> None:
        self._log(level, message, LogCategory.AUDIO, **kwargs)

    def electron(self, message: str, level: str = "INFO", **kwargs) -> None:
        self._log(level, message, LogCategory.ELECTRON, **kwargs)


class SimpleLogger:
    """Fallback logger using standard logging when loguru is not available."""

    def __init__(self):
        """Initialize the simple logger."""
        self._logger = logging.getLogger("bithuman")

    def _log(self, level: str, message: str, category: LogCategory, **kwargs) -> None:
        """Internal logging method.

        Args:
            level: Log level
            message: Log message
            category: Log category
            **kwargs: Additional metadata to include in the log
        """
        # Deduplicate messages
        if not should_log_message(message, level, category.value):
            return

        # Escape curly braces for consistent behavior
        message = message.replace("{", "{{").replace("}", "}}")

        # Handle multi-line messages by adding continuation markers
        if "\n" in message:
            lines = message.split("\n")
            # Format the message with continuation markers for better readability
            formatted_message = f"[{category.value}] {lines[0]}"
            for line in lines[1:]:
                # Add a continuation marker to indent each line
                formatted_message += f"\n                               | {line}"
            log_fn = getattr(self._logger, level.lower())
            log_fn(formatted_message)
        else:
            # Single line message - original handling
            log_fn = getattr(self._logger, level.lower())
            log_fn(f"[{category.value}] {message}")

    # Implement all the same methods as bitHumanLogger with simpler implementation
    def trace(
        self, message: str, category: LogCategory = LogCategory.DEBUG, **kwargs
    ) -> None:
        self._logger.debug(f"[{category.value}] {message}")

    def debug(
        self, message: str, category: LogCategory = LogCategory.DEBUG, **kwargs
    ) -> None:
        self._logger.debug(f"[{category.value}] {message}")

    def info(
        self, message: str, category: LogCategory = LogCategory.SYSTEM, **kwargs
    ) -> None:
        self._logger.info(f"[{category.value}] {message}")

    def success(
        self, message: str, category: LogCategory = LogCategory.SYSTEM, **kwargs
    ) -> None:
        self._logger.info(f"[{category.value}] SUCCESS: {message}")

    def warning(
        self, message: str, category: LogCategory = LogCategory.SYSTEM, **kwargs
    ) -> None:
        self._logger.warning(f"[{category.value}] {message}")

    def error(
        self, message: str, category: LogCategory = LogCategory.SYSTEM, **kwargs
    ) -> None:
        self._logger.error(f"[{category.value}] {message}")

    def critical(
        self, message: str, category: LogCategory = LogCategory.SYSTEM, **kwargs
    ) -> None:
        self._logger.critical(f"[{category.value}] {message}")

    # Convenience methods for different categories
    def system(self, message: str, level: str = "INFO", **kwargs) -> None:
        getattr(self._logger, level.lower())(f"[SYSTEM] {message}")

    def server(self, message: str, level: str = "INFO", **kwargs) -> None:
        getattr(self._logger, level.lower())(f"[SERVER] {message}")

    def model(self, message: str, level: str = "INFO", **kwargs) -> None:
        getattr(self._logger, level.lower())(f"[MODEL] {message}")

    def ui(self, message: str, level: str = "INFO", **kwargs) -> None:
        getattr(self._logger, level.lower())(f"[UI] {message}")

    def network(self, message: str, level: str = "INFO", **kwargs) -> None:
        getattr(self._logger, level.lower())(f"[NETWORK] {message}")

    def audio(self, message: str, level: str = "INFO", **kwargs) -> None:
        getattr(self._logger, level.lower())(f"[AUDIO] {message}")

    def electron(self, message: str, level: str = "INFO", **kwargs) -> None:
        getattr(self._logger, level.lower())(f"[ELECTRON] {message}")


# Helper functions for configuring standard library loggers
def configure_stdlib_loggers(is_production: bool, debug_mode: bool) -> None:
    """Configure standard library loggers to appropriate levels.

    Args:
        is_production: Whether production mode is enabled
        debug_mode: Whether debug mode is enabled
    """
    # Configure levels for external libraries
    if is_production:
        # Very restrictive in production
        logging.getLogger("werkzeug").setLevel(logging.ERROR)
        logging.getLogger("engineio").setLevel(logging.ERROR)
        logging.getLogger("engineio.server").setLevel(logging.ERROR)
        logging.getLogger("socketio").setLevel(logging.ERROR)
        logging.getLogger("socketio.server").setLevel(logging.ERROR)
        logging.getLogger("flask_socketio").setLevel(logging.ERROR)
        logging.getLogger("bithuman").setLevel(logging.WARNING)
    else:
        # Less restrictive in development but still focused
        logging.getLogger("werkzeug").setLevel(logging.WARNING)
        logging.getLogger("engineio").setLevel(logging.ERROR)
        logging.getLogger("engineio.server").setLevel(logging.ERROR)
        logging.getLogger("socketio").setLevel(logging.WARNING)
        logging.getLogger("socketio.server").setLevel(logging.ERROR)
        logging.getLogger("flask_socketio").setLevel(logging.WARNING)
        logging.getLogger("bithuman").setLevel(
            logging.INFO if debug_mode else logging.WARNING
        )

    # Always suppress these noisy loggers
    logging.getLogger("numba").setLevel(logging.ERROR)
    logging.getLogger("urllib3").setLevel(logging.ERROR)
    logging.getLogger("requests").setLevel(logging.ERROR)


# Default logger singleton
app_logger = None


# Direct access to the global logger instance
def get_logger(name=None):
    """Get the global logger instance.

    Args:
        name: Optional logger name (not used, included for compatibility)

    Returns:
        The global bitHumanLogger instance
    """
    # We ignore the name parameter and always return the global logger
    return app_logger


# Function aliases for direct access to the logger
def debug(message: str, category: LogCategory = LogCategory.DEBUG, **kwargs) -> None:
    if app_logger:
        app_logger.debug(message, category, **kwargs)


def info(message: str, category: LogCategory = LogCategory.SYSTEM, **kwargs) -> None:
    if app_logger:
        app_logger.info(message, category, **kwargs)


def warning(message: str, category: LogCategory = LogCategory.SYSTEM, **kwargs) -> None:
    if app_logger:
        app_logger.warning(message, category, **kwargs)


def error(message: str, category: LogCategory = LogCategory.SYSTEM, **kwargs) -> None:
    if app_logger:
        app_logger.error(message, category, **kwargs)


def critical(
    message: str, category: LogCategory = LogCategory.SYSTEM, **kwargs
) -> None:
    if app_logger:
        app_logger.critical(message, category, **kwargs)


def system(message: str, level: str = "INFO", **kwargs) -> None:
    if app_logger:
        app_logger.system(message, level, **kwargs)


def server(message: str, level: str = "INFO", **kwargs) -> None:
    if app_logger:
        app_logger.server(message, level, **kwargs)


def model(message: str, level: str = "INFO", **kwargs) -> None:
    if app_logger:
        app_logger.model(message, level, **kwargs)


def ui(message: str, level: str = "INFO", **kwargs) -> None:
    if app_logger:
        app_logger.ui(message, level, **kwargs)


def network(message: str, level: str = "INFO", **kwargs) -> None:
    if app_logger:
        app_logger.network(message, level, **kwargs)


def audio(message: str, level: str = "INFO", **kwargs) -> None:
    if app_logger:
        app_logger.audio(message, level, **kwargs)


def electron(message: str, level: str = "INFO", **kwargs) -> None:
    if app_logger:
        app_logger.electron(message, level, **kwargs)


def configure_logging(level: str = "INFO"):
    """Configure logging for the application (compatibility wrapper).

    Args:
        level: Minimum log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
    """
    # Set reasonable defaults in case imports fail due to circular imports
    is_production = False

    # Try to import, but don't fail if there's a circular import
    try:
        # Only try to import if logger isn't already configured
        if app_logger is None:
            from . import assets_manager

            is_production = assets_manager.get_server_mode() == "production"
    except (ImportError, AttributeError):
        # During initial import cycles, this might fail, so default to development mode
        pass

    # Set up the logger
    setup_logger(level=level, is_production=is_production)
    return app_logger


# Suppress werkzeug write() before start_response error in stderr
class StderrFilter(logging.Filter):
    """Filter to suppress specific Werkzeug error messages."""

    def filter(self, record):
        """Filter out the write() before start_response error."""
        if hasattr(record, "msg") and isinstance(record.msg, str):
            if "AssertionError: write() before start_response" in record.msg:
                return False
        return True


# Apply the filter to stderr
stderr_handler = logging.StreamHandler(sys.stderr)
stderr_handler.addFilter(StderrFilter())
logging.getLogger().addHandler(stderr_handler)

# Also set up a filter for werkzeug's internal logger
werkzeug_logger = logging.getLogger("werkzeug")
werkzeug_logger.addFilter(StderrFilter())
