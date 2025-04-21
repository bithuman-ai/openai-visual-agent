"""Asset management utilities for the bitHuman Visual Agent API.

This module provides functions for discovering, loading, and managing assets like
models, voices, and images used by the API server.
"""

import os
from typing import Any, Dict, List, Optional, Tuple

from loguru import logger

from daemon.utils import assets_manager


def get_assets_from_directory(
    asset_type: str, file_extension: str, default_setting_key: str = None
) -> list[dict[str, Any]]:
    """Get available assets from a directory.

    Finds all assets of a specific type in the corresponding assets directory.

    Args:
        asset_type: Type of asset (models, voices, images)
        file_extension: File extension to filter by
        default_setting_key: Setting key for default assets if none found

    Returns:
        List of asset objects with metadata
    """
    try:
        # Get user data directory using settings utility
        user_data_dir = assets_manager.get_user_data_dir()
        assets_list = []

        if user_data_dir:
            assets_dir = os.path.join(user_data_dir, "assets", asset_type)
            if os.path.exists(assets_dir):
                # Find all files with the given extension in the directory
                files = [
                    f for f in os.listdir(assets_dir) if f.endswith(file_extension)
                ]

                # For models, return objects with ID, name, and file path
                if asset_type == "models":
                    for file in files:
                        asset_id = file.replace(file_extension, "")
                        # Format the display name
                        display_name = asset_id.replace("_", " ").title()
                        assets_list.append(
                            {
                                "id": asset_id,
                                "name": display_name,
                                "file": os.path.join(assets_dir, file),
                            }
                        )
                # For voices, return ID and file path
                elif asset_type == "voices":
                    for file in files:
                        asset_id = file.replace(file_extension, "")
                        # Using consistent object format for voices
                        assets_list.append(
                            {
                                "id": asset_id,
                                "name": asset_id.replace("_", " ").title(),
                                "file": os.path.join(assets_dir, file),
                            }
                        )
                # For images, return full objects
                elif asset_type == "images":
                    for file in files:
                        asset_id = file.replace(file_extension, "")
                        assets_list.append(
                            {
                                "id": asset_id,
                                "file": os.path.join(assets_dir, file),
                                "format": file_extension.replace(".", "").upper(),
                            }
                        )

        # If no assets found and we have a settings key, use defaults from settings
        if not assets_list and default_setting_key:
            defaults = assets_manager.get_setting(default_setting_key, [])

            # Process default assets based on type
            if asset_type == "models":
                for file in defaults:
                    asset_id = os.path.basename(file).replace(file_extension, "")
                    # Format the display name
                    display_name = asset_id.replace("_", " ").title()
                    assets_list.append(
                        {"id": asset_id, "name": display_name, "file": file}
                    )
            elif asset_type == "voices":
                for file in defaults:
                    asset_id = os.path.basename(file).replace(file_extension, "")
                    # Using consistent object format for voices
                    assets_list.append(
                        {
                            "id": asset_id,
                            "name": asset_id.replace("_", " ").title(),
                            "file": file,
                        }
                    )

        return assets_list
    except Exception as e:
        logger.error(f"Error getting available {asset_type}: {e}")
        return []


def get_model_by_id(model_id: str) -> Optional[dict[str, Any]]:
    """Get a model by ID.

    Looks up a model by its ID and returns information about it.

    Args:
        model_id: ID of the model to look up

    Returns:
        Dictionary with model metadata or None if not found
    """
    # First try to find with .imx extension
    models = get_assets_from_directory("models", ".imx", "defaults.models")

    # Look for a matching ID
    for model in models:
        if model["id"] == model_id:
            return model

    # Try without requiring the exact ID match (for backward compatibility)
    model_id_lower = model_id.lower()
    for model in models:
        if model["id"].lower() == model_id_lower:
            return model

    return None


def get_voice_by_id(voice_id: str) -> Optional[dict[str, Any]]:
    """Get a voice by ID.

    Looks up a voice by its ID and returns information about it.

    Args:
        voice_id: ID of the voice to look up

    Returns:
        Dictionary with voice metadata or None if not found
    """
    voices = get_assets_from_directory("voices", ".wav", "defaults.voices")

    # Look for matching ID
    for voice in voices:
        if voice["id"] == voice_id:
            return voice

    # Try case-insensitive match
    voice_id_lower = voice_id.lower()
    for voice in voices:
        if voice["id"].lower() == voice_id_lower:
            return voice

    return None


def find_asset_file(asset_type: str, asset_id: str) -> Optional[str]:
    """Find the full path to an asset file.

    Finds the full path to an asset file based on its type and ID.

    Args:
        asset_type: Type of asset (models, voices)
        asset_id: ID of the asset to look up

    Returns:
        Full path to the asset file or None if not found
    """
    if asset_type == "models":
        model = get_model_by_id(asset_id)
        return model["file"] if model else None
    elif asset_type == "voices":
        voice = get_voice_by_id(asset_id)
        return voice["file"] if voice else None

    return None
