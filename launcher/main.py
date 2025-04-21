"""
bitHuman Visual Agent Launcher Module

This script verifies and prepares the environment for the bitHuman Visual Agent.

Example usage:
1. Run the launcher: python -m launcher
2. Then run the daemon (web service): python -m daemon

Command-line usage:
$ python -m launcher.main [--port PORT] [--verbose]
"""

import argparse
import asyncio
import json
import logging
import os
import platform
import socket
import sys
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import aiohttp

from launcher.assets_manager import AssetsManager, SettingsManager
from launcher.logging import (
    Colors,
    format_command,
    format_error,
    format_header,
    format_path,
    format_section,
    format_success,
    format_value,
    format_warning,
    log_assets,
    log_config,
    log_network,
    log_security,
    log_system,
    setup_logging,
)

#############################
# Global variables
#############################
# Thread-safe logging configuration
_logging_lock = threading.Lock()

#############################
# Utility Functions
#############################


def get_user_data_dir() -> str:
    """Get the appropriate user data directory for the current platform.

    Returns:
        Path to the user data directory
    """
    # Determine the appropriate user data directory based on the platform
    if platform.system() == "Windows":
        base_dir = os.environ.get("APPDATA", os.path.expanduser("~"))
    elif platform.system() == "Darwin":  # macOS
        base_dir = os.path.expanduser("~/Library/Application Support")
    else:  # Linux/Unix
        base_dir = os.environ.get("XDG_DATA_HOME", os.path.expanduser("~/.local/share"))

    # Create the application-specific data directory
    app_data_dir = os.path.join(base_dir, "bitHumanVisualAgent")
    return app_data_dir


async def verify_openai_api_key(api_key: str) -> Tuple[bool, str]:
    """Verify if the OpenAI API key is valid by calling the models endpoint.

    Args:
        api_key: The OpenAI API key to verify

    Returns:
        Tuple of (is_valid, message)
    """
    url = "https://api.openai.com/v1/models"
    headers = {"Authorization": f"Bearer {api_key}"}

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers, timeout=10) as response:
                if response.status == 200:
                    # API key is valid
                    data = await response.json()
                    model_count = len(data.get("data", []))
                    return (
                        True,
                        f"Valid OpenAI API key (access to {model_count} models)",
                    )
                elif response.status == 401:
                    # API key is invalid
                    return False, "Invalid API key or key has been revoked"
                elif response.status == 429:
                    # Rate limited
                    return False, "API key rate limited - please try again later"
                else:
                    # Other error
                    return False, f"API returned status code {response.status}"
    except asyncio.TimeoutError:
        return False, "Connection timed out while verifying API key"
    except Exception as e:
        return False, f"Error verifying API key: {str(e)}"


async def verify_bithuman_api_key(api_key: str) -> Tuple[bool, str, bool]:
    """Verify if the bitHuman API key is valid by calling the validation endpoint.

    Args:
        api_key: The bitHuman API key to verify

    Returns:
        Tuple of (is_valid, message, validation_success)
        is_valid: Whether the key is valid
        message: Message describing the result
        validation_success: Whether validation could be performed (true) or deferred to later (false)
    """
    url = "https://api.one.bithuman.io/v1/authentication/validate-secret"
    headers = {"Content-Type": "application/json"}
    payload = {"value": api_key}

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                url, headers=headers, json=payload, timeout=10
            ) as response:
                if response.status == 200:
                    # API returned a response
                    data = await response.json()
                    is_valid = data.get("data", {}).get("is_valid", False)

                    if is_valid:
                        return True, "Valid bitHuman API key", True
                    else:
                        return False, "Invalid bitHuman API key", True
                else:
                    # Other error
                    return False, f"API returned status code {response.status}", True
    except asyncio.TimeoutError:
        return (
            False,
            "Connection timed out while verifying API key. Will try again later.",
            False,
        )
    except aiohttp.ClientConnectorError:
        return (
            False,
            "Could not connect to the bitHuman API. Will try again later.",
            False,
        )
    except Exception as e:
        return False, f"Error verifying API key: {str(e)}. Will try again later.", False


#############################
# Verification Functions
#############################


def verify_environment() -> Tuple[bool, Optional[str]]:
    """Verify the Python environment and dependencies.

    Returns:
        Tuple of (success, error_message)
    """
    try:
        # Check Python version
        python_version = platform.python_version()
        if not python_version.startswith(
            ("3.8", "3.9", "3.10", "3.11", "3.12", "3.13")
        ):
            return (
                False,
                f"Unsupported Python version: {python_version}. Please use Python 3.8 or newer.",
            )

        # Check for required packages
        required_packages = [
            "flask",
            "flask-socketio",
            "numpy",
            "pillow",
            "requests",
            "aiohttp",
            "aiofiles",
            "tqdm",
        ]

        missing_packages = []
        try:
            import pkg_resources

            for package in required_packages:
                try:
                    pkg_resources.get_distribution(package)
                except pkg_resources.DistributionNotFound:
                    missing_packages.append(package)
        except ImportError:
            # If pkg_resources is not available, we can't check packages
            log_system(
                "pkg_resources not available, skipping package verification",
                logging.WARNING,
            )

        if missing_packages:
            return False, f"Missing required packages: {', '.join(missing_packages)}"

        # Check system architecture
        if platform.system() not in ["Windows", "Darwin", "Linux"]:
            return False, f"Unsupported operating system: {platform.system()}"

        # All checks passed
        log_system(
            f"Environment verification passed: Python {python_version} on {platform.system()}"
        )
        return True, None

    except Exception as e:
        error_message = f"Environment verification error: {str(e)}"
        log_system(error_message, logging.ERROR)
        return False, error_message


def verify_directories(user_data_dir: str) -> Tuple[bool, Optional[str]]:
    """Verify and create the required directory structure.

    Args:
        user_data_dir: Path to user data directory

    Returns:
        Tuple of (success, error_message)
    """
    try:
        # Initialize settings manager
        settings_manager = SettingsManager(user_data_dir)
        settings = settings_manager.settings

        # Get directory paths from settings
        assets_dir = settings["assets"]["assetDir"]
        models_dir = settings["assets"]["modelsDir"]
        images_dir = settings["assets"]["imagesDir"]
        voices_dir = settings["assets"]["voicesDir"]
        prompts_dir = settings["assets"]["promptsDir"]
        logs_dir = settings["logs"]["logDir"]

        # Asset base directory path
        assets_base_path = os.path.join(user_data_dir, assets_dir)

        # Required directories
        required_dirs = [
            user_data_dir,
            assets_base_path,
            os.path.join(assets_base_path, models_dir),
            os.path.join(assets_base_path, images_dir),
            os.path.join(assets_base_path, voices_dir),
            os.path.join(assets_base_path, prompts_dir),
            os.path.join(user_data_dir, logs_dir),
        ]

        created_dirs = []

        # Create directories if they don't exist
        for directory in required_dirs:
            if not os.path.exists(directory):
                log_system(f"Creating directory: {directory}")
                os.makedirs(directory, exist_ok=True)
                created_dirs.append(directory)

        # Verify write permissions by creating and removing a test file
        test_file_path = os.path.join(user_data_dir, ".write_test")
        try:
            with open(test_file_path, "w") as f:
                f.write("Test write access")
            os.remove(test_file_path)
        except (IOError, OSError) as e:
            return False, f"Cannot write to directory {user_data_dir}: {str(e)}"

        # All checks passed
        log_system(f"Directory structure verification passed: {user_data_dir}")

        result_message = "All directories exist and are writeable"
        if created_dirs:
            result_message = f"Created directories: {', '.join(created_dirs)}"

        return True, result_message

    except Exception as e:
        error_message = f"Directory verification error: {str(e)}"
        log_system(error_message, logging.ERROR)
        return False, error_message


#############################
# Launcher Main Functions
#############################


async def prepare_environment(
    user_data_dir: str, port: Optional[int] = None
) -> Dict[str, Any]:
    """Prepare the environment for application startup.

    This function:
    1. Verifies the Python environment
    2. Checks and initializes directory structure
    3. Sets up required assets
    4. Configures and checks port
    5. Validates bitHuman API key
    6. Validates OpenAI API key
    7. Final verification of settings

    Args:
        user_data_dir: Path to user data directory
        port: Optional specific port to use

    Returns:
        Dictionary with detailed verification results
    """
    results = {
        "status": "pending",
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "user_data_dir": user_data_dir,
    }

    try:
        # Initialize settings manager
        settings_manager = SettingsManager(user_data_dir)

        # Log system information
        log_system("Preparing environment for Visual Agent")

        # Step 1: Verify Python environment and dependencies
        log_system("Verifying environment...")
        env_ok, env_message = verify_environment()
        results["environment"] = {
            "status": "success" if env_ok else "error",
            "message": env_message if not env_ok else "Environment verification passed",
            "python_version": platform.python_version(),
            "system": platform.system(),
            "platform": platform.platform(),
        }

        if not env_ok:
            log_system(f"Environment verification failed: {env_message}", logging.ERROR)
            results["status"] = "error"
            results["error"] = f"Environment verification failed: {env_message}"
            return results

        # Step 2: Verify and create directory structure if needed
        log_system("Verifying directory structure...")
        dir_ok, dir_message = verify_directories(user_data_dir)
        results["directories"] = {
            "status": "success" if dir_ok else "error",
            "message": dir_message,
        }

        if not dir_ok:
            log_system(
                f"Directory structure verification failed: {dir_message}", logging.ERROR
            )
            results["status"] = "error"
            results["error"] = f"Directory structure verification failed: {dir_message}"
            return results

        # Step 3: Check and initialize assets
        log_assets("Checking required assets...")
        assets_ok, assets_results = await AssetsManager.check_and_initialize_assets(
            user_data_dir
        )
        results["assets"] = assets_results

        if not assets_ok:
            log_assets("Failed to initialize required assets", logging.ERROR)
            results["status"] = "error"
            results["error"] = "Failed to initialize required assets"
            return results

        # Step 4: Verify and configure port
        log_network("Verifying port configuration...")
        if port is not None:
            # Try to bind to the specified port
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                try:
                    s.bind(("127.0.0.1", port))
                    settings_manager.update_setting("server.port", port)
                    port_ok = True
                    port_message = f"Using specified port: {port}"
                except OSError:
                    port_ok = False
                    port_message = f"Specified port {port} is already in use"
        else:
            # Find an available port
            port_ok, port = settings_manager.find_available_port()
            port_message = (
                f"Found available port: {port}"
                if port_ok
                else "No available ports found"
            )

        results["port"] = {
            "status": "success" if port_ok else "error",
            "port": port,
            "message": port_message,
        }

        if not port_ok:
            log_network(f"Port verification failed: {port_message}", logging.ERROR)
            results["status"] = "error"
            results["error"] = f"Port verification failed: {port_message}"
            return results

        # Step 5: Verify bitHuman API key
        log_security("Validating bitHuman API key...")
        # Get API key from settings
        bithuman_api_key = settings_manager.get_setting("apiKeys.bithuman", "")

        # Always validate the API key, regardless of whether it's the default or not
        (
            bithuman_valid,
            bithuman_message,
            bithuman_validation_success,
        ) = await verify_bithuman_api_key(bithuman_api_key)

        # If the key is invalid or couldn't be validated, try fallback to default_settings.json
        if not bithuman_valid:
            log_security(
                "User's bitHuman API key is invalid or couldn't be validated, trying fallback key...",
                logging.WARNING,
            )

            # Load key directly from default_settings.json
            default_settings_path = os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                "default_settings.json",
            )
            try:
                with open(default_settings_path, "r") as f:
                    default_settings = json.load(f)
                    fallback_bithuman_key = default_settings.get("apiKeys", {}).get(
                        "bithuman", ""
                    )

                # Only try fallback if it's different from the user's key
                if fallback_bithuman_key and fallback_bithuman_key != bithuman_api_key:
                    log_security(
                        "Found fallback bitHuman API key in default_settings.json, validating...",
                        logging.INFO,
                    )
                    (
                        fallback_valid,
                        fallback_message,
                        fallback_validation_success,
                    ) = await verify_bithuman_api_key(fallback_bithuman_key)

                    if fallback_valid:
                        log_security(
                            "Fallback bitHuman API key is valid, updating user settings...",
                            logging.INFO,
                        )
                        # Update the user's settings with the valid fallback key
                        settings_manager.update_setting(
                            "apiKeys.bithuman", fallback_bithuman_key
                        )
                        # Update our validation results
                        bithuman_valid = True
                        bithuman_message = fallback_message + " (fallback key)"
                        bithuman_validation_success = True
                        bithuman_status = "success"
                    else:
                        log_security(
                            f"Fallback bitHuman API key validation failed: {fallback_message}",
                            logging.ERROR,
                        )
                        # Keep original validation results
            except Exception as e:
                log_security(
                    f"Error loading fallback bitHuman API key: {e}", logging.ERROR
                )

        # Determine status - if we couldn't validate (network issue), it's a warning instead of error
        if bithuman_valid:
            bithuman_status = "success"
            log_security(f"bitHuman API key validation successful: {bithuman_message}")
        elif not bithuman_validation_success:
            bithuman_status = "warning"
            log_security(
                f"bitHuman API key validation deferred: {bithuman_message}",
                logging.WARNING,
            )
        else:
            bithuman_status = "error"
            log_security(
                f"bitHuman API key validation failed: {bithuman_message}", logging.ERROR
            )

        results["bithuman_key"] = {
            "status": bithuman_status,
            "valid": bithuman_valid,
            "message": bithuman_message,
            "validation_success": bithuman_validation_success,
        }

        # Step 6: Verify OpenAI API key
        log_security("Validating OpenAI API key...")
        # Get API key from settings
        openai_api_key = settings_manager.get_setting("apiKeys.openai", "")

        # Always validate the API key, regardless of whether it's the default or not
        api_valid, api_message = await verify_openai_api_key(openai_api_key)

        # If the key is invalid, try fallback to default_settings.json
        if not api_valid:
            log_security(
                "User's OpenAI API key is invalid, trying fallback key...",
                logging.WARNING,
            )

            # Load key directly from default_settings.json
            default_settings_path = os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                "default_settings.json",
            )
            try:
                with open(default_settings_path, "r") as f:
                    default_settings = json.load(f)
                    fallback_openai_key = default_settings.get("apiKeys", {}).get(
                        "openai", ""
                    )

                # Only try fallback if it's different from the user's key
                if fallback_openai_key and fallback_openai_key != openai_api_key:
                    log_security(
                        "Found fallback OpenAI API key in default_settings.json, validating...",
                        logging.INFO,
                    )
                    fallback_valid, fallback_message = await verify_openai_api_key(
                        fallback_openai_key
                    )

                    if fallback_valid:
                        log_security(
                            "Fallback OpenAI API key is valid, updating user settings...",
                            logging.INFO,
                        )
                        # Update the user's settings with the valid fallback key
                        settings_manager.update_setting(
                            "apiKeys.openai", fallback_openai_key
                        )
                        # Update our validation results
                        api_valid = True
                        api_message = fallback_message + " (fallback key)"
                    else:
                        log_security(
                            f"Fallback OpenAI API key validation failed: {fallback_message}",
                            logging.ERROR,
                        )
                        # Keep original validation results
            except Exception as e:
                log_security(
                    f"Error loading fallback OpenAI API key: {e}", logging.ERROR
                )

        api_status = "success" if api_valid else "error"

        if api_valid:
            log_security(f"OpenAI API key validation successful: {api_message}")
        else:
            log_security(
                f"OpenAI API key validation failed: {api_message}", logging.ERROR
            )

        results["api_key"] = {
            "status": api_status,
            "valid": api_valid,
            "message": api_message,
        }

        # Step 7: Final verification of settings
        log_config("Verifying settings file...")
        # Load settings from disk to ensure they've been saved correctly
        current_settings = settings_manager.settings
        saved_port = settings_manager.get_setting("server.port")

        if saved_port is None or saved_port != port:
            log_config(
                f"Settings verification failed: Port mismatch. Expected {port}, found {saved_port}",
                logging.ERROR,
            )
            results["settings_verification"] = {
                "status": "error",
                "message": f"Port mismatch in settings. Expected {port}, found {saved_port}",
            }
            results["status"] = "error"
            results["error"] = "Settings were not saved correctly"
            return results

        results["settings_verification"] = {
            "status": "success",
            "message": "Settings saved correctly",
            "port": saved_port,
        }

        # All checks passed
        log_system("Environment preparation completed successfully")
        results["status"] = "success"
        return results

    except Exception as e:
        error_message = f"Environment preparation failed: {str(e)}"
        log_system(error_message, logging.ERROR)
        results["status"] = "error"
        results["error"] = error_message
        return results


async def async_launch_app(port: Optional[int] = None) -> int:
    """Main async entry point for the launcher.

    Args:
        port: Optional port to use for the server

    Returns:
        Exit code (0 for success, non-zero for error)
    """
    # Get user data directory
    user_data_dir = get_user_data_dir()

    try:
        # Prepare environment (verify, setup directories, download assets)
        results = await prepare_environment(user_data_dir, port)

        # Define colors for prettier console output
        STATUS_COLORS = {
            "success": Colors.GREEN,
            "error": Colors.RED,
            "warning": Colors.YELLOW,
            "pending": Colors.BRIGHT_BLACK,
        }

        # Print results summary with colors
        divider = "═" * 60
        print(f"\n{format_header('VISUAL AGENT ENVIRONMENT VERIFICATION')}")
        print(format_section(char="═"))

        # Status with color
        status_text = "SUCCESS" if results["status"] == "success" else "ERROR"
        status_format = "success" if results["status"] == "success" else "error"
        print(
            f"{Colors.BOLD}Status:{Colors.RESET} {format_value(status_text, status_format)}"
        )
        print(f"{Colors.BOLD}Timestamp:{Colors.RESET} {results['timestamp']}")
        print(
            f"{Colors.BOLD}User data directory:{Colors.RESET} {format_path(results['user_data_dir'])}"
        )
        print(format_section(char="-"))

        # Print environment details with color
        env = results.get("environment", {})
        env_status = env.get("status", "unknown")
        env_format = "success" if env_status == "success" else "error"
        print(
            f"{Colors.BOLD}Environment:{Colors.RESET} {format_value(env_status.upper(), env_format)}"
        )
        print(
            f"  {Colors.BRIGHT_BLACK}Python:{Colors.RESET} {env.get('python_version', 'unknown')}"
        )
        print(
            f"  {Colors.BRIGHT_BLACK}System:{Colors.RESET} {env.get('system', 'unknown')} ({env.get('platform', 'unknown')})"
        )
        print(
            f"  {Colors.BRIGHT_BLACK}Message:{Colors.RESET} {env.get('message', 'No details')}"
        )

        # Print directory details with color
        dirs = results.get("directories", {})
        dirs_status = dirs.get("status", "unknown")
        dirs_format = "success" if dirs_status == "success" else "error"
        print(
            f"{Colors.BOLD}Directories:{Colors.RESET} {format_value(dirs_status.upper(), dirs_format)}"
        )
        print(
            f"  {Colors.BRIGHT_BLACK}Message:{Colors.RESET} {dirs.get('message', 'No details')}"
        )

        # Print assets details with color
        assets = results.get("assets", {})
        assets_status = assets.get("status", "unknown")
        assets_format = "success" if assets_status == "success" else "error"
        print(
            f"{Colors.BOLD}Assets:{Colors.RESET} {format_value(assets_status.upper(), assets_format)}"
        )

        # Print initial asset status in a prettier format
        initial_status = assets.get("initial_status", {})
        if initial_status:
            print(f"  {Colors.UNDERLINE}Starting Asset Check:{Colors.RESET}")
            for key, value in initial_status.items():
                if (
                    "missing" in value.lower()
                    or "not found" in value.lower()
                    or "no valid" in value.lower()
                ):
                    # Show user-friendly message about what needs to be downloaded
                    missing_count = value.count(",") + 1 if "," in value else 1
                    print(
                        f"  • {key}: {Colors.YELLOW}🔍 Downloading {missing_count} {key} files...{Colors.RESET}"
                    )
                elif "ok" in value.lower() or "found" in value.lower():
                    print(
                        f"  • {key}: {Colors.GREEN}✅ All {key} files already available{Colors.RESET}"
                    )
                else:
                    print(f"  • {key}: {value}")

        # Print download results if any
        download_results = assets.get("download", {})
        if download_results and download_results.get("status") in [
            "success",
            "partial",
            "error",
        ]:
            print(f"  {Colors.UNDERLINE}Download Results:{Colors.RESET}")

            # Get counts for each asset type
            success_counts = {}
            failed_counts = {}

            # Display model downloads
            model_results = download_results.get("models", {})
            if model_results:
                success_models = sum(
                    1 for status in model_results.values() if status == "Success"
                )
                failed_models = sum(
                    1 for status in model_results.values() if status == "Failed"
                )
                success_counts["Models"] = success_models
                failed_counts["Models"] = failed_models

                if failed_models == 0:
                    print(
                        f"  • Models: {Colors.GREEN}✅ Downloaded {success_models} model files successfully{Colors.RESET}"
                    )
                else:
                    print(
                        f"  • Models: {Colors.YELLOW}⚠️ Downloaded {success_models} files, {failed_models} failed{Colors.RESET}"
                    )
                    # Show details only for failed downloads
                    for model, status in model_results.items():
                        if status == "Failed":
                            print(f"    - {model}: {format_value(status, 'error')}")

            # Display image downloads
            image_results = download_results.get("images", {})
            if image_results:
                success_images = sum(
                    1 for status in image_results.values() if status == "Success"
                )
                failed_images = sum(
                    1 for status in image_results.values() if status == "Failed"
                )
                success_counts["Images"] = success_images
                failed_counts["Images"] = failed_images

                if failed_images == 0:
                    print(
                        f"  • Images: {Colors.GREEN}✅ Downloaded {success_images} image files successfully{Colors.RESET}"
                    )
                else:
                    print(
                        f"  • Images: {Colors.YELLOW}⚠️ Downloaded {success_images} files, {failed_images} failed{Colors.RESET}"
                    )
                    # Show details only for failed downloads
                    for image, status in image_results.items():
                        if status == "Failed":
                            print(f"    - {image}: {format_value(status, 'error')}")

            # Display voice downloads
            voice_results = download_results.get("voices", {})
            if voice_results:
                success_voices = sum(
                    1 for status in voice_results.values() if status == "Success"
                )
                failed_voices = sum(
                    1 for status in voice_results.values() if status == "Failed"
                )
                success_counts["Voices"] = success_voices
                failed_counts["Voices"] = failed_voices

                if failed_voices == 0:
                    print(
                        f"  • Voices: {Colors.GREEN}✅ Downloaded {success_voices} voice files successfully{Colors.RESET}"
                    )
                else:
                    print(
                        f"  • Voices: {Colors.YELLOW}⚠️ Downloaded {success_voices} files, {failed_voices} failed{Colors.RESET}"
                    )
                    # Show details only for failed downloads
                    for voice, status in voice_results.items():
                        if status == "Failed":
                            print(f"    - {voice}: {format_value(status, 'error')}")

            # Display prompts downloads
            prompts_results = download_results.get("prompts", {})
            if prompts_results:
                success_prompts = sum(
                    1 for status in prompts_results.values() if status == "Success"
                )
                failed_prompts = sum(
                    1 for status in prompts_results.values() if status == "Failed"
                )
                success_counts["Prompts"] = success_prompts
                failed_counts["Prompts"] = failed_prompts

                if failed_prompts == 0:
                    print(
                        f"  • Prompts: {Colors.GREEN}✅ Downloaded {success_prompts} prompt files successfully{Colors.RESET}"
                    )
                else:
                    print(
                        f"  • Prompts: {Colors.YELLOW}⚠️ Downloaded {success_prompts} files, {failed_prompts} failed{Colors.RESET}"
                    )
                    # Show details only for failed downloads
                    for prompt, status in prompts_results.items():
                        if status == "Failed":
                            print(f"    - {prompt}: {format_value(status, 'error')}")

        # Print final verification status if available
        final_status = assets.get("final_status", {})
        if final_status:
            print(f"  {Colors.UNDERLINE}Final Asset Status:{Colors.RESET}")
            all_good = True
            missing_assets = []

            for key, value in final_status.items():
                if "missing" in value.lower() or "not found" in value.lower():
                    all_good = False
                    print(
                        f"  • {key}: {Colors.YELLOW}⚠️ Some files are still missing{Colors.RESET}"
                    )
                    missing_assets.append(key)
                elif "ok" in value.lower() or "found" in value.lower():
                    print(f"  • {key}: {Colors.GREEN}✅ All files ready{Colors.RESET}")
                else:
                    print(f"  • {key}: {value}")

            # Summary message
            if all_good:
                print(
                    f"  {Colors.GREEN}🎉 All asset files are prepared and ready to use!{Colors.RESET}"
                )
            elif assets.get("status") == "partial":
                print(
                    f"  {Colors.YELLOW}⚠️ Some files couldn't be downloaded, but the essential ones are ready{Colors.RESET}"
                )
            else:
                print(
                    f"  {Colors.RED}⚠️ Some required files are missing, which might affect functionality{Colors.RESET}"
                )
        # If no final status but download was successful, show positive message
        elif download_results and download_results.get("status") == "success":
            print(
                f"  {Colors.GREEN}🎉 All asset files are prepared and ready to use!{Colors.RESET}"
            )

        # Print port details with color
        port_info = results.get("port", {})
        port_status = port_info.get("status", "unknown")
        port_format = "success" if port_status == "success" else "error"
        print(
            f"{Colors.BOLD}Port:{Colors.RESET} {format_value(port_status.upper(), port_format)}"
        )
        print(
            f"  {Colors.BRIGHT_BLACK}Port number:{Colors.RESET} {port_info.get('port', 'unknown')}"
        )
        print(
            f"  {Colors.BRIGHT_BLACK}Message:{Colors.RESET} {port_info.get('message', 'No details')}"
        )

        # Create a colorful API Key validation section with horizontal separators
        print("")  # Add some spacing
        print(f"{Colors.CYAN}{'═' * 80}{Colors.RESET}")
        print(
            f"{Colors.BG_BLUE}{Colors.WHITE}{Colors.BOLD}  🔐  API KEY VALIDATION  🔐  {Colors.RESET}"
        )
        print(f"{Colors.CYAN}{'═' * 80}{Colors.RESET}")

        # Print bitHuman API key validation results with color (first)
        bithuman_info = results.get("bithuman_key", {})
        bithuman_status = bithuman_info.get("status", "unknown")
        validation_success = bithuman_info.get("validation_success", True)
        bithuman_message = bithuman_info.get("message", "No details")

        # Choose format and emoji based on status
        if bithuman_status == "success":
            bithuman_format = "success"
            bithuman_emoji = "✅"
            bithuman_prefix = "🔑"
        elif bithuman_status == "warning":
            bithuman_format = "warning"
            bithuman_emoji = "⏳"
            bithuman_prefix = "⚠️"
        else:
            bithuman_format = "error"
            bithuman_emoji = "❌"
            bithuman_prefix = "🔴"

        # Print bitHuman API key status with enhanced formatting
        print(
            f"{Colors.BOLD}{bithuman_prefix} bitHuman API Key:{Colors.RESET} {format_value(bithuman_status.upper(), bithuman_format)}"
        )
        print(
            f"   {Colors.BRIGHT_BLACK}Status:{Colors.RESET} {bithuman_emoji} {bithuman_message}"
        )

        if bithuman_status == "error":
            # Only show error message when validation was successful but key was invalid
            print(
                f"   {Colors.RED}🚫 API key is invalid. Please update your bitHuman key in default_settings.json{Colors.RESET}"
            )
            print(
                f"   {Colors.BRIGHT_BLACK}🔗 Get a new key:{Colors.RESET} {format_value('https://console.bithuman.io/develop', 'info')}"
            )
        elif bithuman_status == "warning":
            # For network connection issues, show a message that validation will be tried later
            print(
                f"   {Colors.YELLOW}⚠️ Will validate your key when connection is available{Colors.RESET}"
            )

        # Add a decorative separator between API key sections
        print(f"{Colors.MAGENTA}{'─' * 80}{Colors.RESET}")

        # Print OpenAI API key validation results with color (second)
        api_info = results.get("api_key", {})
        api_status = api_info.get("status", "unknown")
        api_message = api_info.get("message", "No details")
        api_format = "success" if api_status == "success" else "error"

        # Choose emoji based on status
        if api_status == "success":
            api_emoji = "✅"
            api_prefix = "🔑"
        else:
            api_emoji = "❌"
            api_prefix = "🔴"

        # Print OpenAI API key status with enhanced formatting
        print(
            f"{Colors.BOLD}{api_prefix} OpenAI API Key:{Colors.RESET} {format_value(api_status.upper(), api_format)}"
        )
        print(
            f"   {Colors.BRIGHT_BLACK}Status:{Colors.RESET} {api_emoji} {api_message}"
        )

        if api_status == "error":
            print(
                f"   {Colors.RED}🚫 API key is invalid. Please update your OpenAI key in default_asettings.json{Colors.RESET}"
            )
            print(
                f"   {Colors.YELLOW}⚠️ Agent Mode won't work without a valid OpenAI API key, but you can still use Avatar Mode{Colors.RESET}"
            )
            print(
                f"   {Colors.BRIGHT_BLACK}🔗 Get a new key:{Colors.RESET} {format_value('https://platform.openai.com/api-keys', 'info')}"
            )

        # Close the panel with a bottom separator
        print(f"{Colors.CYAN}{'═' * 80}{Colors.RESET}")
        print("")  # Add some spacing

        # Conditional final status message based on API key validity
        all_success = results["status"] == "success"
        keys_valid = api_status == "success" and (
            bithuman_status == "success" or bithuman_status == "warning"
        )

        if all_success and keys_valid:
            # All checks passed and keys are valid
            print(
                f"{format_success('All checks passed!')} The environment is ready to run the Visual Agent daemon."
            )
            print(
                f"\n{Colors.BOLD}Launch daemon with:{Colors.RESET} {format_command('python -m daemon')}"
            )
        elif all_success:
            # System checks passed but keys have issues
            print(f"{format_warning('System checks passed but API keys have issues!')}")

            if api_status != "success" and bithuman_status != "success":
                print(
                    f"{Colors.YELLOW}⚠️ The application will have limited functionality without valid API keys.{Colors.RESET}"
                )
            elif api_status != "success":
                print(
                    f"{Colors.YELLOW}⚠️ Agent Mode won't work without a valid OpenAI API key, but you can still use Avatar Mode.{Colors.RESET}"
                )
            elif bithuman_status != "success" and bithuman_status != "warning":
                print(
                    f"{Colors.YELLOW}⚠️ Some features may be limited without a valid bitHuman API key.{Colors.RESET}"
                )

            print(
                f"\n{Colors.BOLD}You can still launch the daemon with:{Colors.RESET} {format_command('python -m daemon')}"
            )
        else:
            # System checks failed
            print(
                f"{format_error('Error:')} {results.get('error', 'Unknown error occurred')}"
            )
            print(
                f"{format_warning('Please fix the issues before running the daemon.')}"
            )
        print(format_section(char="═"))

        # Write results to a JSON file
        results_file = os.path.join(user_data_dir, "launcher_results.json")
        try:
            with open(results_file, "w") as f:
                json.dump(results, f, indent=4)
            print(f"\n{format_path(f'Detailed results written to: {results_file}')}")
        except Exception as e:
            log_system(f"Error writing results file: {e}", logging.ERROR)

        # Return success or failure
        return 0 if results["status"] == "success" else 1

    except Exception as e:
        log_system(f"Launch failed: {str(e)}", logging.ERROR)
        print(f"\n{format_error(f'Launch failed: {str(e)}')}")
        return 1


def launch_app(port: Optional[int] = None, verbose: bool = False) -> int:
    """Run the launcher with the specified configuration.

    This is the primary public function for verifying the environment.
    It handles all the necessary setup steps.

    Args:
        port: Optional port to use for the server
        verbose: Whether to enable verbose logging

    Returns:
        Exit code (0 for success, non-zero for error)
    """
    try:
        # Get user data directory
        user_data_dir = get_user_data_dir()

        # Initialize settings manager
        settings_manager = SettingsManager(user_data_dir)
        settings = settings_manager.settings

        # Add user_data_dir to settings for logging
        settings["user_data_dir"] = user_data_dir

        # Set up logging with appropriate level
        setup_logging(verbose, settings)

        # Run the async main function in a new event loop
        return asyncio.run(async_launch_app(port=port))
    except KeyboardInterrupt:
        # Handle Ctrl+C gracefully
        log_system("Launch interrupted", logging.WARNING)
        print(f"\n{format_warning('Launch interrupted by user.')}")
        return 0
    except Exception as e:
        # Handle unexpected errors
        log_system(f"Launch error: {str(e)}", logging.ERROR)
        print(f"\n{format_error(f'Unexpected error: {str(e)}')}")
        return 1


#############################
# Argument Parser
#############################
parser = argparse.ArgumentParser(description="bitHuman Visual Agent Launcher")
parser.add_argument("--port", type=int, help="Specify port for the server")
parser.add_argument(
    "--verbose", "-v", action="store_true", help="Enable verbose logging"
)

#############################
# Script Entry Point
#############################

if __name__ == "__main__":
    # Parse command line arguments
    args = parser.parse_args()

    # Get user data directory
    user_data_dir = get_user_data_dir()

    # Initialize settings manager
    settings_manager = SettingsManager(user_data_dir)
    settings = settings_manager.settings

    # Add user_data_dir to settings for logging
    settings["user_data_dir"] = user_data_dir

    # Set up logging with appropriate level
    setup_logging(args.verbose, settings)

    # Print a welcome banner
    print(f"\n{format_header('bitHuman Visual Agent Launcher')}")
    print(format_section(""))
    print("Starting verification process for the Visual Agent environment...")
    print(f"{format_path(f'System: {platform.system()} {platform.release()}')}")
    print(f"{format_path(f'Python: {platform.python_version()}')}")
    print(f"{format_section('')}\n")

    # Run the launcher
    exit_code = launch_app(port=args.port, verbose=args.verbose)

    # Report final status
    if exit_code == 0:
        print(
            f"\n{format_success('Launcher completed successfully.')} You can now start the daemon with:"
        )
        print(f"  {format_command('python -m daemon')}")

    sys.exit(exit_code)
