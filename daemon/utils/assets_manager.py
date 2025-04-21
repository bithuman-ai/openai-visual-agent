"""Asset management and settings utilities for the bitHuman Visual Agent Application."""

import asyncio
import json
import os
import platform
import subprocess
import sys
import time
from typing import Any, Callable, Dict, Optional

import aiofiles
import aiohttp

# Remove this import as we're incorporating the settings_utils functions
# from daemon.utils import settings_utils
from daemon.utils.logging import error, info, warning

#############################
# Settings Utilities
#############################


def get_user_data_dir() -> str:
    """Get the platform-specific user data directory.

    Returns:
        Path to the user data directory
    """
    home = os.path.expanduser("~")
    app_name = "bitHumanVisualAgent"

    if platform.system() == "Darwin":  # macOS
        return os.path.join(home, "Library", "Application Support", app_name)
    elif platform.system() == "Windows":  # Windows
        return os.path.join(
            os.environ.get("APPDATA", os.path.join(home, "AppData", "Roaming")),
            app_name,
        )
    else:  # Linux and others
        return os.path.join(home, ".local", "share", app_name)


def get_settings_path() -> str:
    """Get the path to the settings.json file.

    Returns:
        Path to settings.json
    """
    return os.path.join(get_user_data_dir(), "settings.json")


def load_settings() -> Dict[str, Any]:
    """Load settings from settings.json.

    Returns:
        Dictionary of settings or empty dict if file cannot be loaded
    """
    settings_path = get_settings_path()

    try:
        if os.path.exists(settings_path):
            with open(settings_path) as f:
                return json.load(f)
        else:
            info(f"Warning: Settings file not found at {settings_path}")
    except Exception as e:
        error(f"Error loading settings: {e}")

    return {}


def get_setting(path: str, default: Any = None) -> Any:
    """Get a setting value using a dot notation path.

    Args:
        path: Path to the setting (e.g., "server.port")
        default: Default value if setting is not found

    Returns:
        Setting value or default
    """
    settings = load_settings()

    # Split the path into parts
    parts = path.split(".")

    # Navigate through the settings dictionary
    current = settings
    for part in parts:
        if isinstance(current, dict) and part in current:
            current = current[part]
        else:
            return default

    return current


# Convenient accessor functions
def get_api_key(key_name: str) -> str:
    """Get an API key from settings.

    Args:
        key_name: The name of the API key (e.g., "openai", "bithuman")

    Returns:
        The API key or empty string if not found
    """
    return get_setting(f"apiKeys.{key_name}", "")


def get_server_port() -> int:
    """Get the server port from settings.

    Returns:
        The server port (default: 5001)
    """
    return get_setting("server.port", 5001)


def get_server_mode() -> str:
    """Get the server mode from settings.

    Returns:
        The server mode ('development' or 'production')
    """
    return get_setting("server.mode", "production")


def get_debug_mode() -> bool:
    """Get the debug mode setting.

    Returns:
        True if debug mode is enabled, False otherwise
    """
    return get_setting("server.debug", False)


def get_asset_path(asset_type: str) -> str:
    """Get an asset path from settings.

    Args:
        asset_type: The type of asset (e.g., "modelsDir", "imagesDir")

    Returns:
        The asset path or empty string if not found
    """
    asset_dir = get_setting("assets.assetDir", "assets")
    asset_subdir = get_setting(f"assets.{asset_type}", "")
    if asset_subdir:
        return os.path.join(get_user_data_dir(), asset_dir, asset_subdir)
    return ""


def get_default_model_path() -> str:
    """Get the default model path.

    Returns:
        The default model path
    """
    models = get_setting("defaults.models", ["albert_einstein.imx"])
    if models and len(models) > 0:
        return models[0]
    return "albert_einstein.imx"


#############################
# Asset Management
#############################


class AssetsManager:
    """Manages asset downloads and initialization."""

    def __init__(self, user_data_dir: str):
        """Initialize the AssetsManager.

        Args:
            user_data_dir: The user data directory path
        """
        self.user_data_dir = user_data_dir
        self.assets_dir = os.path.join(user_data_dir, "assets")
        self.models_dir = os.path.join(self.assets_dir, "models")
        self.images_dir = os.path.join(self.assets_dir, "images")
        self.voices_dir = os.path.join(self.assets_dir, "voices")
        self.config_dir = os.path.join(self.assets_dir, "config")

        # Create directories
        os.makedirs(self.assets_dir, exist_ok=True)
        os.makedirs(self.models_dir, exist_ok=True)
        os.makedirs(self.images_dir, exist_ok=True)
        os.makedirs(self.voices_dir, exist_ok=True)
        os.makedirs(self.config_dir, exist_ok=True)

        # Load settings
        settings = load_settings()

        # Get constants from settings
        self._default_models = settings.get("defaults", {}).get("models", [])
        self._default_voices = settings.get("defaults", {}).get("voices", [])
        self._config_files = settings.get("defaults", {}).get("prompts", [])
        self._repo_base_url = settings.get("repo", {}).get("baseUrl", "")
        self._model_base_url = settings.get("repo", {}).get("modelBaseUrl", "")
        self._voice_base_url = settings.get("repo", {}).get("voiceBaseUrl", "")
        self._config_base_url = settings.get("repo", {}).get("configBaseUrl", "")

        # Import model loader only when needed to avoid circular imports
        self._model_loader = None

    async def _download_file(
        self,
        url: str,
        destination: str,
        file_desc: str,
        callback: Optional[Callable[[str, float], None]] = None,
        chunk_size: int = 1048576,
        max_retries: int = 3,
    ) -> bool:
        """Download a file with simple progress tracking.

        Args:
            url: The URL to download from
            destination: The destination file path
            file_desc: Description of the file being downloaded
            callback: Optional callback for progress updates
            chunk_size: Size of chunks to download (default: 1MB)
            max_retries: Maximum number of retry attempts

        Returns:
            True if download was successful, False otherwise
        """
        # First try to use external download tools for better performance
        external_result = self._try_external_download(
            url, destination, file_desc, callback
        )
        if external_result:
            return True

        # If external download fails or isn't available, fall back to internal method
        info(f"Using internal downloader for {url}")
        if callback:
            callback(f"Downloading {file_desc}...", 0)

        # Fall back to internal download method with retry logic
        retries = 0
        while retries <= max_retries:
            try:
                # Calculate optimal chunk size based on file size (if available)
                adaptive_chunk_size = chunk_size

                # Configure aiohttp with optimized settings for large files
                timeout = aiohttp.ClientTimeout(
                    total=7200, connect=60, sock_connect=60, sock_read=120
                )

                # Use a more optimized connector with larger limits for large files
                conn = aiohttp.TCPConnector(
                    limit=5,
                    force_close=False,  # Keep connections alive
                    enable_cleanup_closed=True,
                    ttl_dns_cache=300,  # Cache DNS results
                    ssl=False,  # Disable SSL for better performance if http
                )

                session_kwargs = {
                    "timeout": timeout,
                    "connector": conn,
                    "raise_for_status": False,
                }

                if url.startswith("https"):
                    # Re-enable SSL for https URLs
                    conn = aiohttp.TCPConnector(
                        limit=5,
                        force_close=False,
                        enable_cleanup_closed=True,
                        ttl_dns_cache=300,
                    )
                    session_kwargs["connector"] = conn

                async with aiohttp.ClientSession(**session_kwargs) as session:
                    # Set headers for better download performance
                    headers = {
                        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
                        "Accept-Encoding": "gzip, deflate",
                        "Connection": "keep-alive",
                    }

                    # Check if file exists and is partially downloaded
                    file_size = 0
                    if os.path.exists(destination):
                        file_size = os.path.getsize(destination)
                        if file_size > 0:
                            headers["Range"] = f"bytes={file_size}-"
                            info(f"Resuming download of {url} from byte {file_size}")

                    try:
                        # First make a HEAD request to get file info without downloading
                        async with session.head(
                            url, headers=headers, allow_redirects=True
                        ) as head_response:
                            if head_response.status == 200:
                                # Get content length from headers
                                content_length = head_response.headers.get(
                                    "content-length"
                                )
                                if content_length:
                                    total_size = int(content_length)

                                    # Adjust chunk size based on file size
                                    if total_size > 1024 * 1024 * 1024:  # > 1GB
                                        adaptive_chunk_size = (
                                            4 * 1024 * 1024
                                        )  # 4MB chunks for very large files
                                    elif total_size > 100 * 1024 * 1024:  # > 100MB
                                        adaptive_chunk_size = (
                                            2 * 1024 * 1024
                                        )  # 2MB chunks for large files

                                    info(
                                        f"File size: {total_size} bytes, using chunk size: {adaptive_chunk_size} bytes"
                                    )
                    except Exception as e:
                        warning(f"Failed to get file info with HEAD request: {e}")

                    # Now make the actual GET request
                    async with session.get(
                        url, headers=headers, allow_redirects=True
                    ) as response:
                        if (
                            response.status == 416
                        ):  # Range not satisfiable - file is complete
                            info(f"File already downloaded: {destination}")
                            return True

                        if response.status not in [
                            200,
                            206,
                        ]:  # 200 OK or 206 Partial Content
                            if retries < max_retries:
                                wait_time = 2**retries  # Exponential backoff
                                warning(
                                    f"Download failed with status {response.status}, retrying in {wait_time}s (attempt {retries + 1}/{max_retries})"
                                )
                                await asyncio.sleep(wait_time)
                                retries += 1
                                continue
                            error(f"Failed to download {url}: HTTP {response.status}")
                            return False

                        # Get file size for progress tracking
                        total_size = int(response.headers.get("content-length", 0))
                        if response.status == 206:  # Partial content
                            content_range = response.headers.get("content-range", "")
                            if content_range:
                                try:
                                    total_size = int(content_range.split("/")[-1])
                                except ValueError:
                                    pass  # Ignore if we can't parse the total size

                        # Create directory if it doesn't exist
                        os.makedirs(os.path.dirname(destination), exist_ok=True)

                        # Download and write file with progress tracking
                        mode = "ab" if file_size > 0 else "wb"  # Append if resuming

                        start_time = time.time()
                        last_update_time = start_time
                        update_interval = 1.0  # Update progress every 1 second

                        async with aiofiles.open(destination, mode) as f:
                            downloaded = file_size
                            bytes_since_last_update = 0

                            async for chunk in response.content.iter_chunked(
                                adaptive_chunk_size
                            ):
                                await f.write(chunk)

                                # Update downloaded count
                                chunk_size = len(chunk)
                                downloaded += chunk_size
                                bytes_since_last_update += chunk_size

                                # Update progress at fixed intervals to avoid excessive updates
                                current_time = time.time()
                                if current_time - last_update_time >= update_interval:
                                    # Calculate speed
                                    duration = current_time - last_update_time
                                    speed = (
                                        bytes_since_last_update / duration
                                        if duration > 0
                                        else 0
                                    )

                                    # Calculate ETA
                                    eta_str = "unknown"
                                    if total_size and speed > 0:
                                        remaining_bytes = total_size - downloaded
                                        eta_seconds = remaining_bytes / speed
                                        eta_str = self._format_time(eta_seconds)

                                    # Calculate percentage
                                    percentage = (
                                        (downloaded / total_size * 100)
                                        if total_size
                                        else 0
                                    )

                                    # Update progress using callback
                                    progress_message = f"Downloading {file_desc}: {percentage:.1f}% (ETA: {eta_str})"
                                    callback(progress_message, percentage / 100)

                                    # Reset counters
                                    last_update_time = current_time
                                    bytes_since_last_update = 0

                info(f"Downloaded {url} to {destination}")
                return True

            except asyncio.TimeoutError:
                if retries < max_retries:
                    wait_time = 2**retries  # Exponential backoff
                    warning(
                        f"Download timed out, retrying in {wait_time}s (attempt {retries + 1}/{max_retries})"
                    )
                    await asyncio.sleep(wait_time)
                    retries += 1
                else:
                    error(f"Download timed out after {max_retries} retries: {url}")
                    return False
            except Exception as e:
                if retries < max_retries:
                    wait_time = 2**retries  # Exponential backoff
                    warning(
                        f"Error downloading {url}: {e}, retrying in {wait_time}s (attempt {retries + 1}/{max_retries})"
                    )
                    await asyncio.sleep(wait_time)
                    retries += 1
                else:
                    error(f"Error downloading {url} after {max_retries} retries: {e}")
                    return False

    def _format_speed(self, speed: float) -> str:
        """Format speed in bytes/second to a human-readable string.

        Args:
            speed: Speed in bytes per second

        Returns:
            Formatted speed string (e.g., '1.2 MB')
        """
        if speed < 1024:
            return f"{speed:.1f} B"
        elif speed < 1024 * 1024:
            return f"{speed / 1024:.1f} KB"
        elif speed < 1024 * 1024 * 1024:
            return f"{speed / (1024 * 1024):.1f} MB"
        else:
            return f"{speed / (1024 * 1024 * 1024):.1f} GB"

    def _format_time(self, seconds: float) -> str:
        """Format time in seconds to a human-readable string.

        Args:
            seconds: Time in seconds

        Returns:
            Formatted time string (e.g., '1h 2m 3s')
        """
        if seconds < 60:
            # Fix for the double 's' bug - ensure we format seconds correctly
            return f"{int(seconds)}s"
        elif seconds < 3600:
            m = int(seconds / 60)
            s = int(seconds % 60)
            # Only add seconds if there are any
            if s > 0:
                return f"{m}m {s}s"
            else:
                return f"{m}m"
        else:
            h = int(seconds / 3600)
            m = int((seconds % 3600) / 60)
            s = int(seconds % 60)
            # Only include non-zero components
            if m == 0 and s == 0:
                return f"{h}h"
            elif s == 0:
                return f"{h}h {m}m"
            else:
                return f"{h}h {m}m {s}s"

    def _try_external_download(
        self,
        url: str,
        destination: str,
        file_desc: str,
        callback: Optional[Callable[[str, float], None]] = None,
    ) -> bool:
        """Attempt to use external download tools for better performance.

        Args:
            url: The URL to download from
            destination: The destination file path
            file_desc: Description of the file being downloaded
            callback: Optional callback for progress updates

        Returns:
            True if download was successful, False otherwise
        """
        try:
            # Create directory if it doesn't exist
            os.makedirs(os.path.dirname(destination), exist_ok=True)

            # Try aria2c first (best performance)
            if self._command_exists("aria2c"):
                info(f"Using aria2c to download {url}")
                if callback:
                    callback(f"Downloading {file_desc} with aria2c...", 0)

                cmd = [
                    "aria2c",
                    url,
                    "--dir",
                    os.path.dirname(destination),
                    "--out",
                    os.path.basename(destination),
                    "--file-allocation=none",
                    "--continue=true",
                    "--max-connection-per-server=16",
                    "--split=16",
                    "--max-tries=5",
                    "--retry-wait=5",
                    "--connect-timeout=60",
                    "--timeout=60",
                    "--auto-file-renaming=false",
                    "--allow-overwrite=true",
                    "--console-log-level=notice",
                    "--summary-interval=1",
                    "--download-result=full",
                    "--show-console-readout=true",
                    "--human-readable=true",
                ]

                process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    universal_newlines=True,
                    bufsize=1,
                )

                completed_percentage = 0
                download_speed = "0"

                # Process output in real time to show progress
                for line in iter(process.stdout.readline, ""):
                    # Parse progress information
                    if "[#" in line:  # Progress bar line
                        try:
                            # Parse percentage
                            perc_match = (
                                line.split("(")[1].split("%")[0].strip()
                                if "(" in line and "%" in line
                                else None
                            )
                            if perc_match:
                                completed_percentage = float(perc_match)

                            # Parse download speed
                            if "DL:" in line:
                                speed_part = line.split("DL:")[1].strip().split(" ")[0]
                                download_speed = speed_part

                            # Update callback with percentage
                            if callback:
                                progress_message = f"Downloading {file_desc}: {completed_percentage:.1f}% (Speed: {download_speed}/s)"
                                callback(progress_message, completed_percentage / 100)
                        except Exception:
                            # Just continue if we can't parse a line
                            pass

                process.wait()
                if process.returncode == 0:
                    if callback:
                        callback(f"Download complete: {file_desc}", 1.0)
                    info(f"Downloaded {url} to {destination} using aria2c")
                    return True

                warning(
                    f"aria2c download failed with code {process.returncode}, falling back to internal method"
                )
                return False

            # Try curl as an alternative
            elif self._command_exists("curl"):
                info(f"Using curl to download {url}")
                if callback:
                    callback(f"Downloading {file_desc} with curl...", 0)

                cmd = [
                    "curl",
                    url,
                    "--output",
                    destination,
                    "--continue-at",
                    "-",  # Resume download
                    "--location",  # Follow redirects
                    "--connect-timeout",
                    "60",
                    "--retry",
                    "5",
                    "--retry-delay",
                    "5",
                    "--progress",  # Show progress
                ]

                process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    universal_newlines=True,
                    bufsize=1,
                )

                # Process output in real time to show progress
                for line in iter(process.stdout.readline, ""):
                    if "%" in line and callback:
                        try:
                            # Parse percentage
                            percentage = float(line.strip().split()[1].replace("%", ""))
                            progress_message = (
                                f"Downloading {file_desc}: {percentage:.1f}%"
                            )
                            callback(progress_message, percentage / 100)
                        except Exception:
                            # Just continue if we can't parse a line
                            callback(f"Downloading {file_desc}...", 0.5)

                process.wait()
                if process.returncode == 0:
                    if callback:
                        callback(f"Download complete: {file_desc}", 1.0)
                    info(f"Downloaded {url} to {destination} using curl")
                    return True

                warning("curl download failed, falling back to internal method")
                return False

            # Try wget as a last resort
            elif self._command_exists("wget"):
                info(f"Using wget to download {url}")
                if callback:
                    callback(f"Downloading {file_desc} with wget...", 0)

                cmd = [
                    "wget",
                    url,
                    "-O",
                    destination,
                    "-c",  # Continue partial downloads
                    "--tries=5",
                    "--timeout=60",
                    "--progress=bar:force:noscroll",  # Show progress bar
                ]

                process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    universal_newlines=True,
                    bufsize=1,
                )

                # Process output in real time to show progress
                for line in iter(process.stdout.readline, ""):
                    if "%" in line and callback:
                        try:
                            # Parse percentage
                            percentage = float(
                                line.split("%")[0].strip().split(" ")[-1]
                            )
                            progress_message = (
                                f"Downloading {file_desc}: {percentage:.1f}%"
                            )
                            callback(progress_message, percentage / 100)
                        except Exception:
                            # Just continue if we can't parse a line
                            pass

                process.wait()
                if process.returncode == 0:
                    if callback:
                        callback(f"Download complete: {file_desc}", 1.0)
                    info(f"Downloaded {url} to {destination} using wget")
                    return True

                warning("wget download failed, falling back to internal method")
                return False

        except Exception as e:
            warning(
                f"External download tool failed: {e}, falling back to internal method"
            )

        return False

    def _command_exists(self, command: str) -> bool:
        """Check if a command exists on the system.

        Args:
            command: Command name to check

        Returns:
            True if command exists, False otherwise
        """
        try:
            # Use 'where' on Windows and 'which' on Unix
            cmd = "where" if os.name == "nt" else "which"
            subprocess.check_output([cmd, command], stderr=subprocess.STDOUT)
            return True
        except (subprocess.SubprocessError, FileNotFoundError):
            return False

    async def _generate_cover_photo(
        self, model_path: str, callback: Optional[Callable[[str, float], None]] = None
    ) -> Optional[str]:
        """Generate a cover photo for a model.

        Args:
            model_path: Path to the model file
            callback: Optional callback for progress updates

        Returns:
            Path to the cover photo or None if failed
        """
        try:
            # Import the model loader module if not already
            if self._model_loader is None:
                # Use lazy import to avoid circular dependency
                from daemon.core.model_loader import ModelLoader

                self._model_loader = ModelLoader()

            # Generate cover photo
            info(f"Generating cover photo for {model_path}")
            model_name = os.path.basename(model_path)
            model_name_without_ext = os.path.splitext(model_name)[0]

            if callback:
                callback(f"Generating thumbnail for {model_name_without_ext}...", 0.5)

            # Get cover photo
            temp_cover_path = await self._model_loader.get_cover_photo_from_model(
                model_path
            )
            if not temp_cover_path or not os.path.exists(temp_cover_path):
                error(f"Failed to generate cover photo for {model_path}")
                return None

            # Move to permanent location
            permanent_path = os.path.join(
                self.images_dir, f"{model_name_without_ext}.jpg"
            )
            import shutil

            shutil.copy2(temp_cover_path, permanent_path)
            info(f"Saved cover photo to {permanent_path}")

            if callback:
                callback(f"Generated thumbnail for {model_name_without_ext}", 1.0)

            # Clean up temporary file
            try:
                os.unlink(temp_cover_path)
            except Exception:
                pass

            return permanent_path
        except Exception as e:
            error(f"Error generating cover photo: {e}")
            return None

    async def is_asset_setup_required(self) -> bool:
        """Check if asset setup is required.

        Returns:
            True if setup is required, False otherwise
        """
        # Check for models
        for model in self._default_models:
            model_path = os.path.join(self.models_dir, model)
            if not os.path.exists(model_path):
                info(f"Missing model: {model}")
                return True

        # Check for config files
        for config_file in self._config_files:
            config_path = os.path.join(self.config_dir, config_file)
            if not os.path.exists(config_path):
                info(f"Missing config file: {config_file}")
                return True

        # Check for voices
        for voice in self._default_voices:
            voice_path = os.path.join(self.voices_dir, voice)
            if not os.path.exists(voice_path):
                info(f"Missing voice: {voice}")
                return True

        # Check for cover photos
        for model in self._default_models:
            model_name = os.path.splitext(model)[0]
            image_path = os.path.join(self.images_dir, f"{model_name}.jpg")
            if not os.path.exists(image_path):
                info(f"Missing cover photo: {image_path}")
                return True

        info("All assets are present, no setup required")
        return False

    async def setup_assets(
        self, callback: Optional[Callable[[str, float], None]] = None
    ) -> bool:
        """Set up all assets (download models, generate cover photos, etc.).

        Args:
            callback: Optional callback for progress updates

        Returns:
            True if setup was successful, False otherwise
        """
        try:
            # Assign different weights to different asset types based on typical size
            model_weight = 30.0  # Models are large files
            voice_weight = 2.0  # Voice samples are medium
            config_weight = 0.5  # Config files are small
            cover_weight = 3.0  # Cover photo generation takes some time

            # Calculate total weighted items
            total_weight = (
                len(self._default_models) * model_weight  # Models
                + len(self._default_voices) * voice_weight  # Voices
                + len(self._config_files) * config_weight  # Config files
                + len(self._default_models) * cover_weight  # Cover photos
            )

            # Track weighted progress
            weight_completed = 0.0

            # Create progress tracking function
            def update_overall_progress(message: str, task_progress: float):
                nonlocal callback, weight_completed, total_weight
                if callback:
                    # Format message with clear separation
                    formatted_message = f"PROGRESS: {message}"
                    callback(
                        formatted_message, min(1.0, weight_completed / total_weight)
                    )

            # Step 1: Download models in parallel (largest files, most progress weight)
            if callback:
                callback(
                    "Preparing to download models...", weight_completed / total_weight
                )

            # Create model download tasks
            model_tasks = []
            model_count = 0

            for model in self._default_models:
                model_count += 1
                model_path = os.path.join(self.models_dir, model)
                model_url = f"{self._model_base_url}/{model}"

                if not os.path.exists(model_path):
                    model_desc = f"model {model}"
                    model_tasks.append((model_url, model_path, model_desc, model))
                else:
                    info(f"Model already exists: {model_path}")
                    # Update progress for skipped models
                    weight_completed += model_weight
                    update_overall_progress(
                        "Skipping existing model", weight_completed / total_weight
                    )

            # Download models in parallel with a concurrency limit
            if model_tasks:
                # Create semaphore to limit concurrent downloads (adjust based on connection)
                semaphore = asyncio.Semaphore(3)  # Allow 3 concurrent downloads

                async def download_with_semaphore(url, path, desc, model_name):
                    async with semaphore:

                        def model_progress(message, progress):
                            if callback:
                                # Format message with clear separation
                                formatted_message = f"PROGRESS: {message}"
                                callback(
                                    formatted_message,
                                    (weight_completed + progress * model_weight)
                                    / total_weight,
                                )

                        return await self._download_file(
                            url, path, desc, model_progress
                        ), model_name

                # Start all downloads concurrently
                download_results = await asyncio.gather(
                    *[
                        download_with_semaphore(url, path, desc, model)
                        for url, path, desc, model in model_tasks
                    ],
                    return_exceptions=True,
                )

                # Process results
                for result in download_results:
                    if isinstance(result, Exception):
                        error(f"Error in parallel download: {result}")
                        return False

                    success, model_name = result
                    if not success:
                        error(f"Failed to download model: {model_name}")
                        return False

                    # Update progress
                    weight_completed += model_weight
                    update_overall_progress(
                        f"Downloaded model: {model_name}",
                        weight_completed / total_weight,
                    )

            # Step 2: Download config files (small files, less progress)
            if callback:
                callback(
                    "Downloading configuration files...",
                    weight_completed / total_weight,
                )

            # Download smaller files in parallel too
            config_tasks = []
            config_count = 0

            for config_file in self._config_files:
                config_count += 1
                config_path = os.path.join(self.config_dir, config_file)
                config_url = f"{self._config_base_url}/{config_file}"

                if not os.path.exists(config_path):
                    config_desc = f"config {config_file}"
                    config_tasks.append(
                        (config_url, config_path, config_desc, config_file)
                    )
                else:
                    info(f"Config file already exists: {config_path}")
                    weight_completed += config_weight
                    update_overall_progress(
                        "Skipping existing config file", weight_completed / total_weight
                    )

            # Download configs in parallel (can use higher concurrency as they're small)
            if config_tasks:
                semaphore = asyncio.Semaphore(
                    10
                )  # Allow more concurrent downloads for small files

                async def download_with_semaphore(url, path, desc, file_name):
                    async with semaphore:

                        def config_progress(message, progress):
                            if callback:
                                # Format message with clear separation
                                formatted_message = f"PROGRESS: {message}"
                                callback(
                                    formatted_message,
                                    (weight_completed + progress * config_weight)
                                    / total_weight,
                                )

                        return await self._download_file(
                            url, path, desc, config_progress
                        ), file_name

                config_results = await asyncio.gather(
                    *[
                        download_with_semaphore(url, path, desc, file)
                        for url, path, desc, file in config_tasks
                    ],
                    return_exceptions=True,
                )

                for result in config_results:
                    if isinstance(result, Exception):
                        error(f"Error in parallel config download: {result}")
                        return False

                    success, file_name = result
                    if not success:
                        error(f"Failed to download config file: {file_name}")
                        return False

                    weight_completed += config_weight
                    update_overall_progress(
                        f"Downloaded config: {file_name}",
                        weight_completed / total_weight,
                    )

            # Step 3: Download voices in parallel (medium-sized files)
            if callback:
                callback(
                    "Downloading voice samples...", weight_completed / total_weight
                )

            voice_tasks = []
            voice_count = 0

            for voice in self._default_voices:
                voice_count += 1
                voice_path = os.path.join(self.voices_dir, voice)
                voice_url = f"{self._voice_base_url}/{voice}"

                if not os.path.exists(voice_path):
                    voice_desc = f"voice {voice}"
                    voice_tasks.append((voice_url, voice_path, voice_desc, voice))
                else:
                    info(f"Voice already exists: {voice_path}")
                    weight_completed += voice_weight
                    update_overall_progress(
                        "Skipping existing voice", weight_completed / total_weight
                    )

            # Download voices in parallel
            if voice_tasks:
                semaphore = asyncio.Semaphore(5)  # Moderate concurrency for voice files

                async def download_with_semaphore(url, path, desc, voice_name):
                    async with semaphore:

                        def voice_progress(message, progress):
                            if callback:
                                # Format message with clear separation
                                formatted_message = f"PROGRESS: {message}"
                                callback(
                                    formatted_message,
                                    (weight_completed + progress * voice_weight)
                                    / total_weight,
                                )

                        return await self._download_file(
                            url, path, desc, voice_progress
                        ), voice_name

                voice_results = await asyncio.gather(
                    *[
                        download_with_semaphore(url, path, desc, voice)
                        for url, path, desc, voice in voice_tasks
                    ],
                    return_exceptions=True,
                )

                for result in voice_results:
                    if isinstance(result, Exception):
                        error(f"Error in parallel voice download: {result}")
                        return False

                    success, voice_name = result
                    if not success:
                        error(f"Failed to download voice: {voice_name}")
                        return False

                    weight_completed += voice_weight
                    update_overall_progress(
                        f"Downloaded voice: {voice_name}",
                        weight_completed / total_weight,
                    )

            # Step 4: Generate cover photos (takes some processing time)
            # Note: This is CPU-bound work, so we limit concurrency
            if callback:
                callback("Generating cover photos...", weight_completed / total_weight)

            cover_count = 0
            for model in self._default_models:
                cover_count += 1
                model_path = os.path.join(self.models_dir, model)
                model_name = os.path.splitext(model)[0]
                image_path = os.path.join(self.images_dir, f"{model_name}.jpg")

                if not os.path.exists(image_path):

                    def cover_progress(message, progress):
                        if callback:
                            # Format message with clear separation
                            formatted_message = f"PROGRESS: {message}"
                            callback(
                                formatted_message,
                                (weight_completed + progress * cover_weight)
                                / total_weight,
                            )

                    cover_path = await self._generate_cover_photo(
                        model_path, cover_progress
                    )

                    if not cover_path:
                        error(f"Failed to generate cover photo for model: {model}")
                        return False
                else:
                    info(f"Cover photo already exists: {image_path}")

                weight_completed += cover_weight
                update_overall_progress(
                    f"Generated thumbnail for {model_name}",
                    weight_completed / total_weight,
                )

            # Complete the overall progress
            if callback:
                callback("PROGRESS: Setup complete", 1.0)

            info("Asset setup completed successfully")
            return True

        except Exception as e:
            error(f"Error during asset setup: {e}")
            if callback:
                callback(f"ERROR: {e}", 0)
            return False

    def _parse_human_size(self, size_str: str) -> int:
        """Parse a human-readable size string to bytes.

        Args:
            size_str: Size string like '1.2GiB'

        Returns:
            Size in bytes as integer
        """
        try:
            # Remove commas used as thousand separators
            size_str = size_str.replace(",", "")

            # Check for units
            if (
                size_str.endswith("K")
                or size_str.endswith("KiB")
                or size_str.endswith("KB")
            ):
                return int(
                    float(size_str.rstrip("KiB").rstrip("KB").rstrip("K")) * 1024
                )
            elif (
                size_str.endswith("M")
                or size_str.endswith("MiB")
                or size_str.endswith("MB")
            ):
                return int(
                    float(size_str.rstrip("MiB").rstrip("MB").rstrip("M")) * 1024 * 1024
                )
            elif (
                size_str.endswith("G")
                or size_str.endswith("GiB")
                or size_str.endswith("GB")
            ):
                return int(
                    float(size_str.rstrip("GiB").rstrip("GB").rstrip("G"))
                    * 1024
                    * 1024
                    * 1024
                )
            else:
                return int(float(size_str))
        except Exception:
            return 0


async def init_model_loader() -> tuple[bool, str]:
    """Initialize the model loader with the default model.

    Returns:
        Tuple of (success, error_message)
    """
    # Make imports here to avoid circular dependencies
    from daemon.main import get_model_loader

    # Get existing model loader or create a new one
    get_model_loader()
