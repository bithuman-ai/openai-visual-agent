"""
Asset management utilities for the launcher module.

This module handles verification and downloading of required assets.
"""

import asyncio
import json
import logging
import os
from typing import Any, Dict, Optional, Tuple

import aiofiles
import aiohttp

from launcher.logging import (
    format_error,
    format_header,
    format_section,
    format_success,
    log_assets,
    log_config,
    log_network,
)

#############################
# Settings Management
#############################


class SettingsManager:
    """Manages application settings."""

    def __init__(self, user_data_dir: str):
        """Initialize the settings manager.

        Args:
            user_data_dir: Path to the user data directory
        """
        self.user_data_dir = user_data_dir
        self._settings = None
        self._default_settings = None

    @property
    def settings(self) -> Dict[str, Any]:
        """Get the current settings, loading them if needed.

        Returns:
            The current settings dictionary
        """
        if self._settings is None:
            self._settings = self.load_settings()
        return self._settings

    @property
    def default_settings(self) -> Dict[str, Any]:
        """Get the default settings, loading them if needed.

        Returns:
            The default settings dictionary
        """
        if self._default_settings is None:
            self._default_settings = self._load_default_settings()
        return self._default_settings

    def _load_default_settings(self) -> Dict[str, Any]:
        """Load the default settings from the settings.json file.

        Returns:
            Dictionary containing the default settings
        """
        default_settings_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "default_settings.json",
        )
        try:
            with open(default_settings_path, "r") as f:
                return json.load(f)
        except Exception as e:
            log_config(f"Error loading default settings: {e}", logging.ERROR)
            return {}

    def get_settings_path(self) -> str:
        """Get the path to the settings file.

        Returns:
            Path to the settings file
        """
        settings_filename = self.default_settings.get("app", {}).get(
            "settingsFile", "settings.json"
        )
        return os.path.join(self.user_data_dir, settings_filename)

    def load_settings(self) -> Dict[str, Any]:
        """Load settings from the settings file or create with defaults if it doesn't exist.

        Returns:
            Dictionary containing the settings
        """
        settings_path = self.get_settings_path()
        log_config(f"Checking for settings file at: {settings_path}")

        # If settings file doesn't exist, create it with defaults
        if not os.path.exists(settings_path):
            return self.create_settings()

        # Load existing settings
        try:
            with open(settings_path, "r") as f:
                settings = json.load(f)
            log_config("Settings file loaded successfully.")
            return settings
        except Exception as e:
            log_config(f"Error loading settings file: {e}", logging.ERROR)
            # If loading fails, return the default settings
            return self.default_settings

    def create_settings(self) -> Dict[str, Any]:
        """Create settings file with default values.

        Returns:
            Dictionary containing the default settings
        """
        settings_path = self.get_settings_path()
        log_config("Settings file not found. Creating with defaults.", logging.INFO)

        # Make sure the directory exists
        os.makedirs(os.path.dirname(settings_path), exist_ok=True)

        try:
            # Save default settings
            with open(settings_path, "w") as f:
                json.dump(self.default_settings, f, indent=2)
            log_config("Default settings created successfully.")
        except Exception as e:
            log_config(f"Error creating settings file: {e}", logging.ERROR)

        return self.default_settings

    def save_settings(self, settings: Dict[str, Any]) -> bool:
        """Save settings to the settings file.

        Args:
            settings: Dictionary containing the settings

        Returns:
            True if successful, False otherwise
        """
        settings_path = self.get_settings_path()
        try:
            # Ensure directory exists
            os.makedirs(os.path.dirname(settings_path), exist_ok=True)

            # Create a temporary file first to ensure atomic write
            temp_file = settings_path + ".tmp"
            with open(temp_file, "w") as f:
                json.dump(settings, f, indent=4)

            # Verify the temporary file was written correctly
            with open(temp_file, "r") as f:
                written_settings = json.load(f)
                if written_settings != settings:
                    log_config(
                        "Settings verification failed after write", logging.ERROR
                    )
                    os.remove(temp_file)
                    return False

            # Rename temporary file to actual settings file (atomic operation)
            os.replace(temp_file, settings_path)

            # Update the cached settings
            self._settings = settings

            # Log important settings for debugging
            if "server" in settings and "port" in settings["server"]:
                log_config(f"Saved settings with port: {settings['server']['port']}")

            return True
        except Exception as e:
            log_config(f"Error saving settings file: {e}", logging.ERROR)
            # Try to clean up temporary file if it exists
            try:
                if os.path.exists(temp_file):
                    os.remove(temp_file)
            except:
                pass
            return False

    def update_setting(self, key_path: str, value: Any) -> bool:
        """Update a specific setting value.

        Args:
            key_path: Dot-separated path to the setting (e.g., "server.port")
            value: New value for the setting

        Returns:
            True if successful, False otherwise
        """
        try:
            # Get current settings
            settings = self.settings.copy()

            # Parse the key path
            keys = key_path.split(".")

            # Navigate to the correct nested dictionary
            current = settings
            for key in keys[:-1]:
                if key not in current:
                    current[key] = {}
                current = current[key]

            # Update the value
            current[keys[-1]] = value

            # Save the updated settings
            return self.save_settings(settings)
        except Exception as e:
            log_config(f"Error updating setting {key_path}: {e}", logging.ERROR)
            return False

    def get_setting(self, key_path: str, default: Any = None) -> Any:
        """Get a specific setting value.

        Args:
            key_path: Dot-separated path to the setting (e.g., "server.port")
            default: Default value to return if setting is not found

        Returns:
            The setting value or default if not found
        """
        try:
            # Get current settings
            settings = self.settings

            # Parse the key path
            keys = key_path.split(".")

            # Navigate to the correct nested dictionary
            current = settings
            for key in keys:
                if key not in current:
                    return default
                current = current[key]

            return current
        except Exception as e:
            log_config(f"Error getting setting {key_path}: {e}", logging.ERROR)
            return default

    def find_available_port(
        self, start_port: Optional[int] = None, max_port: Optional[int] = None
    ) -> Tuple[bool, Optional[int]]:
        """Find an available port to use for the server.

        Args:
            start_port: The port to start scanning from (or uses settings)
            max_port: The maximum port to check (or uses settings)

        Returns:
            Tuple of (success, port)
        """
        import socket

        # Get port range from settings
        if start_port is None:
            start_port = self.get_setting("server.minPort", 5001)
        if max_port is None:
            max_port = self.get_setting("server.maxPort", 5010)

        # Check if there's already a configured port in settings
        current_port = self.get_setting("server.port")
        if current_port is not None:
            # Try to verify if the port is still available
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                try:
                    s.bind(("127.0.0.1", current_port))
                    log_network(f"Using previously configured port: {current_port}")
                    return True, current_port
                except OSError:
                    log_network(
                        f"Previously configured port {current_port} is now in use, searching for a new port",
                        logging.WARNING,
                    )

        # Try each port in range
        for port in range(start_port, max_port + 1):
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                try:
                    s.bind(("127.0.0.1", port))
                    # Update settings.json with the new port immediately
                    if self.update_setting("server.port", port):
                        log_network(
                            f"Found available port {port} and saved to settings.json"
                        )
                    else:
                        log_network(
                            f"Found available port {port} but failed to save to settings.json",
                            logging.WARNING,
                        )
                    return True, port
                except OSError:
                    continue  # Port is in use, try next one

        # If we get here, no ports were available
        log_network(
            f"No available ports found between {start_port} and {max_port}",
            logging.ERROR,
        )
        return False, None


#############################
# Asset Management
#############################


class AssetsManager:
    """Manages assets for the Visual Agent application."""

    def __init__(self, user_data_dir: str):
        """Initialize the assets manager.

        Args:
            user_data_dir: Path to the user data directory
        """
        self.user_data_dir = user_data_dir

        # Initialize settings manager
        self.settings_manager = SettingsManager(user_data_dir)
        self.settings = self.settings_manager.settings

        # Get base asset directory
        self.assets_base_dir = os.path.join(
            self.user_data_dir, self.settings["assets"]["assetDir"]
        )

        # Define required asset directories
        self.asset_dirs = {
            "models": os.path.join(
                self.assets_base_dir, self.settings["assets"]["modelsDir"]
            ),
            "images": os.path.join(
                self.assets_base_dir, self.settings["assets"]["imagesDir"]
            ),
            "voices": os.path.join(
                self.assets_base_dir, self.settings["assets"]["voicesDir"]
            ),
            "prompts": os.path.join(
                self.assets_base_dir, self.settings["assets"]["promptsDir"]
            ),
        }

        # Base URLs for downloading assets
        self.base_urls = {
            "models": self.settings["repo"]["modelBaseUrl"],
            "images": self.settings["repo"]["imageBaseUrl"],
            "voices": self.settings["repo"]["voiceBaseUrl"],
            "prompts": self.settings["repo"]["promptBaseUrl"],
        }

        # Assets to check and download
        self.required_assets = {
            "models": self.settings["defaults"]["models"],
            "images": self.settings["defaults"]["images"],
            "voices": self.settings["defaults"]["voices"],
            "prompts": self.settings["defaults"]["prompts"],
        }

        # Map between display names and keys in required_assets/asset_dirs/base_urls
        self.asset_mappings = {
            "models": {
                "required_key": "models",
                "dir_key": "models",
                "url_key": "models",
                "results_key": "models",
            },
            "images": {
                "required_key": "images",
                "dir_key": "images",
                "url_key": "images",
                "results_key": "images",
            },
            "voices": {
                "required_key": "voices",
                "dir_key": "voices",
                "url_key": "voices",
                "results_key": "voices",
            },
            "prompts": {
                "required_key": "prompts",
                "dir_key": "prompts",
                "url_key": "prompts",
                "results_key": "prompts",
            },
        }

    async def is_asset_setup_required(self) -> Tuple[bool, Dict[str, str]]:
        """Check if asset setup is required.

        Returns:
            Tuple of (setup_required, asset_status_report)
        """
        try:
            asset_status = {}
            setup_required = False

            # Check if essential directories exist
            for dir_name, dir_path in self.asset_dirs.items():
                if not os.path.exists(dir_path):
                    asset_status[dir_name] = f"Directory missing: {dir_name}"
                    setup_required = True
                else:
                    asset_status[dir_name] = f"Directory OK: {dir_name}"

            # Check each type of asset
            for asset_type, mapping in self.asset_mappings.items():
                required_key = mapping["required_key"]
                dir_key = mapping["dir_key"]

                if required_key not in self.required_assets:
                    continue

                missing_assets = []
                # Handle the case for dir_key that might not be in self.asset_dirs
                dir_path = self.asset_dirs.get(dir_key)
                if not dir_path:
                    asset_status[asset_type] = (
                        f"Asset directory not configured: {dir_key}"
                    )
                    setup_required = True
                    continue

                # Check each required asset of this type
                for asset_file in self.required_assets[required_key]:
                    asset_path = os.path.join(dir_path, asset_file)
                    if not os.path.exists(asset_path):
                        missing_assets.append(asset_file)
                        setup_required = True

                # Record status for this asset type
                if missing_assets:
                    asset_status[asset_type] = (
                        f"Missing {asset_type}: {', '.join(missing_assets)}"
                    )
                else:
                    asset_status[asset_type] = (
                        f"{len(self.required_assets[required_key])} {asset_type} found"
                    )

            return setup_required, asset_status

        except Exception as e:
            log_assets(f"Error checking assets: {str(e)}", logging.ERROR)
            # If there's an error, assume setup is required
            return True, {"error": f"Error checking assets: {str(e)}"}

    async def download_file(self, url: str, dest_path: str, desc: str) -> bool:
        """Download a file with progress reporting and automatic retries.
        Uses optimized settings for maximum download speed.

        Args:
            url: URL to download from
            dest_path: Destination file path
            desc: Description for the progress bar

        Returns:
            True if successful, False otherwise
        """
        from tqdm import tqdm

        # Get settings from configuration
        connect_timeout = self.settings_manager.get_setting("repo.connectTimeout", 10)
        download_timeout = self.settings_manager.get_setting(
            "repo.downloadTimeout", 300
        )
        use_multipart = self.settings_manager.get_setting(
            "repo.useMultipartDownload", True
        )
        chunk_size = self.settings_manager.get_setting(
            "repo.chunkSize", 262144
        )  # Default 256KB
        max_connections_per_file = self.settings_manager.get_setting(
            "repo.maxConnectionsPerFile", 3
        )
        large_file_threshold = self.settings_manager.get_setting(
            "repo.largeFileThreshold", 10 * 1024 * 1024
        )  # Default 10MB

        # Constants for retry mechanism
        MAX_RETRIES = 3
        RETRY_DELAY = 2  # seconds between retries
        TIMEOUT_CONNECT = connect_timeout
        TIMEOUT_READ = download_timeout

        try:
            # Create parent directory if it doesn't exist
            os.makedirs(os.path.dirname(dest_path), exist_ok=True)

            # Log the download
            log_assets(f"Downloading {desc} from {url}")

            # Create a progress bar for this download
            progress_bar = tqdm(
                desc=f"{desc}", unit="B", unit_scale=True, unit_divisor=1024, leave=True
            )

            # TCP connection reuse and keepalive settings
            tcp_connector = aiohttp.TCPConnector(
                limit=20,  # Increased to allow more parallel connections
                ssl=False,  # Disable SSL verification for speed if needed
                keepalive_timeout=60,
                enable_cleanup_closed=True,
                force_close=False,
            )

            # Configure timeout
            timeout = aiohttp.ClientTimeout(
                total=None,  # No overall timeout
                connect=TIMEOUT_CONNECT,
                sock_connect=TIMEOUT_CONNECT,
                sock_read=TIMEOUT_READ,
            )

            # Set up headers to optimize connection
            headers = {
                "User-Agent": "bitHumanVisualAgent/1.0",
                "Connection": "keep-alive",
                "Accept-Encoding": "gzip, deflate",
                "Accept-Ranges": "bytes",  # Important for resumable downloads
            }

            # Use aiohttp for async HTTP requests with retry logic
            retry_count = 0
            total_size = 0
            temp_file = dest_path + ".tmp"

            while retry_count <= MAX_RETRIES:
                try:
                    async with aiohttp.ClientSession(
                        connector=tcp_connector,
                        timeout=timeout,
                        headers=headers,
                        raise_for_status=True,
                        auto_decompress=True,
                    ) as session:
                        # First try to get the file size and check if server supports range requests
                        supports_range = False
                        try:
                            async with session.head(
                                url, timeout=TIMEOUT_CONNECT
                            ) as response:
                                if response.status == 200:
                                    total_size = int(
                                        response.headers.get("Content-Length", 0)
                                    )
                                    progress_bar.total = total_size

                                    # Check if server supports range requests
                                    if (
                                        "accept-ranges" in response.headers
                                        and response.headers["accept-ranges"] == "bytes"
                                    ):
                                        supports_range = True
                                        log_assets(
                                            f"Server supports range requests for {desc}"
                                        )
                        except Exception as e:
                            log_assets(
                                f"Could not determine file size for {desc} (continuing): {str(e)}"
                            )
                            # Continue anyway, not a fatal error

                        # Determine if we should use multi-part download
                        should_use_multipart = (
                            use_multipart
                            and supports_range
                            and total_size > large_file_threshold
                        )

                        # If this is a resumable download and we have a partial file
                        resume_pos = 0
                        if os.path.exists(temp_file) and retry_count > 0:
                            resume_pos = os.path.getsize(temp_file)
                            if resume_pos > 0 and total_size > resume_pos:
                                log_assets(f"Resuming download from byte {resume_pos}")
                                progress_bar.update(
                                    resume_pos
                                )  # Update progress bar for resumed bytes

                        # For multi-part download of large files
                        if should_use_multipart and resume_pos == 0:
                            # Calculate how to split the download
                            parts = min(
                                max_connections_per_file,
                                max(1, total_size // (5 * 1024 * 1024)),
                            )  # At least 5MB per part
                            part_size = total_size // parts

                            # Prepare part files
                            part_files = [f"{temp_file}.part{i}" for i in range(parts)]

                            # Function to download a specific part
                            async def download_part(part_index, start_byte, end_byte):
                                part_file = part_files[part_index]
                                part_headers = headers.copy()
                                part_headers["Range"] = f"bytes={start_byte}-{end_byte}"

                                async with session.get(
                                    url, headers=part_headers
                                ) as response:
                                    async with aiofiles.open(part_file, "wb") as f:
                                        downloaded = 0
                                        async for (
                                            chunk
                                        ) in response.content.iter_chunked(chunk_size):
                                            if not chunk:
                                                continue
                                            await f.write(chunk)
                                            downloaded += len(chunk)
                                            progress_bar.update(len(chunk))
                                return True

                            # Create download tasks for each part
                            part_tasks = []
                            for i in range(parts):
                                start = i * part_size
                                end = (
                                    (i + 1) * part_size - 1
                                    if i < parts - 1
                                    else total_size - 1
                                )
                                part_tasks.append(download_part(i, start, end))

                            # Run all part downloads concurrently
                            log_assets(
                                f"Using multi-part download with {parts} connections for {desc}"
                            )
                            results = await asyncio.gather(
                                *part_tasks, return_exceptions=True
                            )

                            # Check for errors
                            for i, result in enumerate(results):
                                if isinstance(result, Exception):
                                    raise Exception(
                                        f"Part {i} download failed: {str(result)}"
                                    )

                            # Combine the parts
                            async with aiofiles.open(temp_file, "wb") as outfile:
                                for part_file in part_files:
                                    if os.path.exists(part_file):
                                        async with aiofiles.open(
                                            part_file, "rb"
                                        ) as infile:
                                            await outfile.write(await infile.read())
                                        # Clean up part file
                                        os.remove(part_file)

                            # Verify the combined file size
                            actual_size = os.path.getsize(temp_file)
                            if actual_size != total_size:
                                raise Exception(
                                    f"File size verification failed: expected {total_size}, got {actual_size}"
                                )

                            # Rename temporary file to final file
                            os.replace(temp_file, dest_path)
                            progress_bar.close()
                            log_assets(
                                f"Successfully downloaded {desc} using multi-part download"
                            )
                            return True

                        # Regular single-connection download
                        else:
                            # Prepare for resumable download if possible
                            download_headers = headers.copy()
                            if resume_pos > 0 and supports_range:
                                download_headers["Range"] = f"bytes={resume_pos}-"

                            # Download the file
                            async with session.get(
                                url, headers=download_headers
                            ) as response:
                                # If we didn't get the content length before, try from GET
                                if total_size == 0:
                                    total_size = int(
                                        response.headers.get("Content-Length", 0)
                                    )
                                    if total_size > 0:
                                        progress_bar.total = total_size

                                # Check if we're resuming or starting fresh
                                if (
                                    resume_pos == 0 or response.status != 206
                                ):  # Not a partial content response
                                    # Open file for writing (overwrite)
                                    file_mode = "wb"
                                else:
                                    # Open file for appending
                                    file_mode = "ab"

                                # Open the file for writing
                                async with aiofiles.open(temp_file, file_mode) as f:
                                    downloaded = resume_pos

                                    # Download and write chunks
                                    async for chunk in response.content.iter_chunked(
                                        chunk_size
                                    ):
                                        if not chunk:  # Skip empty chunks
                                            continue
                                        await f.write(chunk)
                                        downloaded += len(chunk)
                                        progress_bar.update(len(chunk))

                                # Verify the download size if we know the total size
                                if total_size > 0 and downloaded != total_size:
                                    raise Exception(
                                        f"Download size mismatch: expected {total_size}, got {downloaded}"
                                    )

                                # Complete the progress bar
                                progress_bar.close()

                                # Verify file integrity
                                if total_size > 0:
                                    actual_size = os.path.getsize(temp_file)
                                    if (
                                        actual_size != total_size
                                        and actual_size != downloaded
                                    ):
                                        raise Exception(
                                            f"File size verification failed: expected {total_size}, got {actual_size}"
                                        )

                                # Rename temporary file to final file
                                os.replace(temp_file, dest_path)

                                log_assets(f"Successfully downloaded {desc}")
                                return True

                except (
                    aiohttp.ClientConnectorError,
                    aiohttp.ClientResponseError,
                    asyncio.TimeoutError,
                ) as e:
                    # For connection errors, try retry
                    retry_count += 1
                    error_type = type(e).__name__

                    if hasattr(progress_bar, "close") and not progress_bar.closed:
                        progress_bar.close()

                    # Create new progress bar for retry
                    if retry_count <= MAX_RETRIES:
                        progress_bar = tqdm(
                            desc=f"{desc} (retry {retry_count}/{MAX_RETRIES})",
                            unit="B",
                            unit_scale=True,
                            unit_divisor=1024,
                            leave=True,
                        )

                        log_assets(
                            f"{error_type} for {desc}, retrying ({retry_count}/{MAX_RETRIES}): {str(e)}"
                        )
                        await asyncio.sleep(
                            RETRY_DELAY * retry_count
                        )  # Exponential backoff
                    else:
                        raise Exception(
                            f"{error_type} after {MAX_RETRIES} retries: {str(e)}"
                        )

                except Exception as e:
                    # Other errors
                    if hasattr(progress_bar, "close") and not progress_bar.closed:
                        progress_bar.close()

                    if retry_count < MAX_RETRIES:
                        retry_count += 1

                        # Create new progress bar for retry
                        progress_bar = tqdm(
                            desc=f"{desc} (retry {retry_count}/{MAX_RETRIES})",
                            unit="B",
                            unit_scale=True,
                            unit_divisor=1024,
                            leave=True,
                        )

                        log_assets(
                            f"Error downloading {desc}, retrying ({retry_count}/{MAX_RETRIES}): {str(e)}"
                        )
                        await asyncio.sleep(RETRY_DELAY * retry_count)
                    else:
                        raise Exception(
                            f"Download failed after {MAX_RETRIES} retries: {str(e)}"
                        )

        except Exception as e:
            log_assets(f"Error downloading {desc}: {str(e)}", logging.ERROR)
            if (
                "progress_bar" in locals()
                and hasattr(progress_bar, "close")
                and not progress_bar.closed
            ):
                progress_bar.close()

            # Clean up any temporary files
            if os.path.exists(temp_file):
                try:
                    # Don't remove temp file for retry capability, just log it
                    log_assets(
                        f"Temporary file remains for potential resume: {temp_file}"
                    )
                except:
                    pass

            # Clean up any part files if they exist
            if "part_files" in locals():
                for part_file in part_files:
                    if os.path.exists(part_file):
                        try:
                            os.remove(part_file)
                        except:
                            pass

            return False

    async def download_required_assets(self) -> Dict[str, str]:
        """Download required assets sequentially.

        Files are downloaded one at a time for cleaner progress reporting.
        Each individual file download still uses multi-part optimization for speed.

        Returns:
            Dictionary with status of each downloaded asset
        """
        # Initialize results dictionary based on asset mappings
        results = {
            mapping["results_key"]: {} for mapping in self.asset_mappings.values()
        }

        # First check what we need to download
        setup_required, asset_status = await self.is_asset_setup_required()

        if not setup_required:
            log_assets("All required assets already exist, no download needed.")
            results["status"] = "success"
            return results

        # Create all required directories if they don't exist
        for dir_name, dir_path in self.asset_dirs.items():
            if not os.path.exists(dir_path):
                log_assets(f"Creating directory: {dir_path}")
                os.makedirs(dir_path, exist_ok=True)

        print(f"\n{format_header('DOWNLOADING REQUIRED ASSETS')}")
        print(format_section(char="═"))

        # Prepare list of assets to download
        assets_to_download = []

        # Gather all assets that need downloading
        for asset_type, mapping in self.asset_mappings.items():
            required_key = mapping["required_key"]
            dir_key = mapping["dir_key"]
            url_key = mapping["url_key"]
            results_key = mapping["results_key"]

            if required_key not in self.required_assets:
                continue

            for asset_file in self.required_assets[required_key]:
                asset_path = os.path.join(self.asset_dirs[dir_key], asset_file)
                if not os.path.exists(asset_path):
                    asset_url = f"{self.base_urls[url_key]}/{asset_file}"
                    # Track asset metadata
                    assets_to_download.append(
                        {
                            "asset_type": asset_type,
                            "asset_file": asset_file,
                            "asset_url": asset_url,
                            "asset_path": asset_path,
                            "results_key": results_key,
                            "desc": f"{asset_type.title()}: {asset_file}",
                        }
                    )
                else:
                    results[mapping["results_key"]][asset_file] = "Already exists"

        download_count = len(assets_to_download)
        if download_count == 0:
            log_assets("No new assets needed to be downloaded.")
            print(f"{format_success('No new assets needed to be downloaded')}")
            results["status"] = "success"
            return results

        # Sort assets by type for better organization
        assets_to_download.sort(key=lambda x: (x["asset_type"], x["asset_file"]))

        log_assets(f"Downloading {download_count} assets sequentially...")

        # Process each download one at a time (sequentially)
        failed_count = 0
        completed_count = 0

        for asset_info in assets_to_download:
            try:
                log_assets(
                    f"Starting download of {asset_info['desc']} ({completed_count + 1}/{download_count})"
                )

                # Download the file (this will use multi-part download internally for large files)
                success = await self.download_file(
                    asset_info["asset_url"],
                    asset_info["asset_path"],
                    asset_info["desc"],
                )

                # Update results
                results[asset_info["results_key"]][asset_info["asset_file"]] = (
                    "Success" if success else "Failed"
                )

                # Update counters
                completed_count += 1
                if not success:
                    failed_count += 1
                    log_assets(
                        f"Failed to download {asset_info['desc']}", logging.ERROR
                    )
                else:
                    log_assets(f"Successfully downloaded {asset_info['desc']}")

                # Provide progress feedback
                log_assets(
                    f"Progress: {completed_count}/{download_count} assets processed, {failed_count} failed"
                )

            except Exception as e:
                # This should rarely happen as exceptions are caught in download_file
                log_assets(
                    f"Unexpected error downloading {asset_info['desc']}: {str(e)}",
                    logging.ERROR,
                )
                results[asset_info["results_key"]][asset_info["asset_file"]] = "Failed"
                failed_count += 1
                completed_count += 1

        # Log summary
        print(format_section(char="-"))
        overall_success = failed_count == 0
        if overall_success and download_count > 0:
            log_assets(f"All {download_count} assets downloaded successfully.")
            print(
                f"{format_success(f'Downloaded {download_count} assets successfully')}"
            )
            results["status"] = "success"
        elif failed_count == download_count:
            log_assets(
                f"Failed to download all {download_count} assets.", logging.ERROR
            )
            print(f"{format_error(f'Failed to download all {download_count} assets')}")
            results["status"] = "error"
        else:
            log_assets(
                f"Downloaded {download_count - failed_count} assets, {failed_count} failed."
            )
            print(
                f"{format_error(f'Failed to download {failed_count} out of {download_count} assets')}"
            )
            results["status"] = "partial" if download_count > failed_count else "error"
        print(format_section(char="═"))

        return results

    async def initialize_assets(self) -> Tuple[bool, Dict[str, Any]]:
        """Initialize assets for the application.

        Returns:
            Tuple of (success, result_details)
        """
        results = {}
        try:
            # Ensure directories exist
            for dir_path in self.asset_dirs.values():
                os.makedirs(dir_path, exist_ok=True)

            # Download required assets
            download_results = await self.download_required_assets()
            results["download"] = download_results

            if download_results.get("status") not in ["success", "partial"]:
                return False, results

            # Verify assets after download
            setup_required, asset_status = await self.is_asset_setup_required()
            results["verification"] = asset_status

            if setup_required:
                # Some assets might still be missing, but we'll continue if at least partial success
                if download_results.get("status") == "partial":
                    log_assets(
                        "Some assets are still missing, but continuing with partial success",
                        logging.WARNING,
                    )
                    results["status"] = "partial"
                    return True, results
                else:
                    log_assets(
                        "Asset initialization failed: verification failed after download",
                        logging.ERROR,
                    )
                    results["status"] = "error"
                    results["error"] = "Verification failed after download"
                    return False, results

            results["status"] = "success"
            return True, results

        except Exception as e:
            log_assets(f"Error initializing assets: {str(e)}", logging.ERROR)
            results["status"] = "error"
            results["error"] = str(e)
            return False, results

    @staticmethod
    async def check_and_initialize_assets(
        user_data_dir: str,
    ) -> Tuple[bool, Dict[str, Any]]:
        """Check if required assets exist and download if needed.

        Args:
            user_data_dir: Path to user data directory

        Returns:
            Tuple of (success, result_details)
        """
        results = {}
        try:
            # Create assets manager
            assets_manager = AssetsManager(user_data_dir)

            # Check if setup is required
            log_assets("Checking for required assets...")
            (
                setup_required,
                asset_status,
            ) = await assets_manager.is_asset_setup_required()
            results["initial_status"] = asset_status

            # Log detailed asset status
            log_assets(
                f"Asset verification complete. {len(asset_status)} categories checked."
            )
            for category, status in asset_status.items():
                if "missing" in status.lower() or "error" in status.lower():
                    log_assets(f"  - {category}: {status}", logging.WARNING)
                else:
                    log_assets(f"  - {category}: {status}")

            if setup_required:
                log_assets("Some assets are missing. Starting download process...")
                # Initialize assets
                success, init_results = await assets_manager.initialize_assets()
                results.update(init_results)

                if not success and init_results.get("status") != "partial":
                    log_assets("Failed to initialize assets", logging.ERROR)
                    results["status"] = "error"
                    return False, results

                # Perform final verification
                log_assets("Performing final asset verification...")
                (
                    final_required,
                    final_status,
                ) = await assets_manager.is_asset_setup_required()
                results["final_status"] = final_status

                if final_required:
                    log_assets(
                        "Some assets are still missing after download", logging.WARNING
                    )
                    results["status"] = "partial"
                    # Continue with partial success to allow the app to run with limited functionality
                    return True, results
                else:
                    log_assets(
                        "Asset initialization completed successfully. All required assets available."
                    )
                    results["status"] = "success"
            else:
                log_assets("All required assets already exist. No downloads needed.")
                results["status"] = "success"

            return True, results

        except Exception as e:
            log_assets(f"Error checking assets: {str(e)}", logging.ERROR)
            results["status"] = "error"
            results["error"] = str(e)
            return False, results
