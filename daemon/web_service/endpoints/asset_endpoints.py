"""Asset-related API endpoints for the bitHuman Visual Agent.

This module provides API endpoints for asset operations, including:
- Listing available models
- Listing available voices
- Serving static assets
"""

import traceback

from flask import Blueprint, jsonify
from loguru import logger

from daemon.web_service.utils.asset_manager import get_assets_from_directory


def register_endpoints(app, model_loader):
    """Register asset-related endpoints with the Flask application.

    Args:
        app: The Flask application
        model_loader: The model loader instance
    """
    # Create a blueprint for asset endpoints
    asset_bp = Blueprint("asset_endpoints", __name__)

    @asset_bp.route("/api/models", methods=["GET"])
    def get_available_models():
        """Get the list of available models from the system directory."""
        try:
            models_list = get_assets_from_directory("models", ".imx", "defaults.models")
            return jsonify({"models": models_list})
        except Exception as e:
            logger.error(f"Error getting available models: {e}")
            logger.error(f"Traceback: {traceback.format_exc()}")
            return jsonify({"error": str(e), "models": []}), 500

    @asset_bp.route("/api/voices", methods=["GET"])
    def get_available_voices():
        """Get the list of available voices from the system directory."""
        try:
            voices_list = get_assets_from_directory("voices", ".wav", "defaults.voices")
            return jsonify({"voices": voices_list})
        except Exception as e:
            logger.error(f"Error getting available voices: {e}")
            logger.error(f"Traceback: {traceback.format_exc()}")
            return jsonify({"error": str(e), "voices": []}), 500

    @asset_bp.route("/api/images", methods=["GET"])
    def get_available_images():
        """Get the list of available images from the system directory."""
        try:
            # Look for PNG images first
            png_images = get_assets_from_directory("images", ".png")
            # Then look for JPG images
            jpg_images = get_assets_from_directory("images", ".jpg")
            # Combine the lists
            images_list = png_images + jpg_images

            return jsonify({"images": images_list})
        except Exception as e:
            logger.error(f"Error getting available images: {e}")
            logger.error(f"Traceback: {traceback.format_exc()}")
            return jsonify({"error": str(e), "images": []}), 500

    # Register the blueprint with the app
    app.register_blueprint(asset_bp)
