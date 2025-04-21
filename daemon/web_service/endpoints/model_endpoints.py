"""Model-related API endpoints for the bitHuman Visual Agent.

This module provides API endpoints for model operations, including:
- Model reloading
- Cover photo generation
"""

import asyncio
import os
import threading
import traceback
from typing import Any

from flask import Blueprint, jsonify, request
from loguru import logger


def register_endpoints(app, model_loader):
    """Register model-related endpoints with the Flask application.

    Args:
        app: The Flask application
        model_loader: The model loader instance
    """
    # Create a blueprint for model endpoints
    model_bp = Blueprint("model_endpoints", __name__)

    @model_bp.route("/api/reload", methods=["POST"])
    def reload_model_endpoint():
        """API endpoint to reload the Visual Agent model."""
        try:
            # Get the model path from the request
            data = request.get_json()
            if not data:
                logger.warning("Reload request missing data")
                return jsonify({"error": "No data provided"}), 400

            logger.info(f"Received reload request with data: {data}")

            if "model_path" not in data:
                logger.warning("Reload request missing model_path")
                return jsonify({"error": "model_path is required"}), 400

            model_path = data["model_path"]
            logger.info(f"Requested model path: {model_path}")

            if not os.path.exists(model_path):
                logger.error(f"Model file not found at: {model_path}")
                return jsonify({"error": f"Model file not found at: {model_path}"}), 404

            # Check for existing reload in progress
            current_status = model_loader.get_status()
            if current_status.get("is_reloading", False):
                logger.warning(
                    "Model reload already in progress, rejecting new request"
                )
                return jsonify(
                    {
                        "error": "Model reload already in progress",
                        "status": current_status,
                    }
                ), 429  # Too Many Requests

            # Determine if settings changed
            settings_changed = check_if_settings_changed(model_loader, data)

            # Store model path before starting background thread
            stored_model_path = model_path
            current_model = model_loader.runtime_manager.current_model_path or "unknown"

            # Use a thread-safe lock to avoid race conditions
            reload_lock = threading.Lock()

            # Start the reload in a background thread
            with reload_lock:
                reload_thread = threading.Thread(
                    target=reload_model_in_background,
                    args=(
                        model_loader,
                        stored_model_path,
                        settings_changed,
                        reload_lock,
                    ),
                )
                reload_thread.daemon = True
                reload_thread.start()

            # Send response to client
            response = {
                "message": "Reload request accepted and processing in background",
                "current_model": current_model,
                "requested_model": stored_model_path,
                "settings_changed": settings_changed,
            }
            logger.info(f"Sending response: {response}")

            return jsonify(response), 202  # Accepted

        except Exception as e:
            logger.error(f"Error in reload request: {e}")
            logger.error(f"Traceback: {traceback.format_exc()}")
            return jsonify({"error": str(e)}), 500

    @model_bp.route("/api/get_cover_photo_from_model", methods=["POST"])
    def get_cover_photo_from_model():
        """Generate a cover photo from a model file.

        Request body should contain:
        {
            "model_path": "path/to/model.imx"
        }

        Returns:
            JSON with success status and path to the generated cover photo
        """
        try:
            # Get the model path from the request
            data = request.get_json()
            if not data:
                logger.warning("Cover photo request missing data")
                return jsonify({"error": "No data provided"}), 400

            logger.info(f"Received cover photo request with data: {data}")

            if "model_path" not in data:
                logger.warning("Cover photo request missing model_path")
                return jsonify({"error": "model_path is required"}), 400

            model_path = data["model_path"]
            logger.info(f"Requested model path: {model_path}")

            # Check if the file exists
            if not os.path.exists(model_path):
                logger.error(f"Model file not found at: {model_path}")
                return jsonify({"error": f"Model file not found at: {model_path}"}), 404

            # Get cover photo from the model
            try:
                cover_photo_path = asyncio.run(
                    model_loader.get_cover_photo_from_model(model_path)
                )
                logger.info(f"Cover photo generation result: {cover_photo_path}")
            except Exception as e:
                logger.error(f"Error generating cover photo: {e}")
                logger.error(f"Stack trace: {traceback.format_exc()}")
                return jsonify(
                    {
                        "success": False,
                        "error": f"Error generating cover photo: {str(e)}",
                    }
                ), 500

            if not cover_photo_path or not os.path.exists(cover_photo_path):
                logger.error(f"Failed to generate cover photo for model: {model_path}")
                return jsonify(
                    {"success": False, "error": "Failed to generate cover photo"}
                ), 500

            logger.info(f"Generated cover photo at: {cover_photo_path}")

            # Return success with the path to the cover photo
            return jsonify({"success": True, "cover_photo_path": cover_photo_path})

        except Exception as e:
            logger.error(f"Error generating cover photo: {e}")
            logger.error(f"Traceback: {traceback.format_exc()}")
            return jsonify({"error": str(e)}), 500

    # Register the blueprint with the app
    app.register_blueprint(model_bp)


def check_if_settings_changed(model_loader, data: dict[str, Any]) -> bool:
    """Check if settings have changed to determine if reload is needed.

    Args:
        model_loader: The model loader instance
        data: Request data containing model_path, prompt, voice, etc.

    Returns:
        Boolean indicating if settings have changed
    """
    # Get model path and optional settings
    model_path = data.get("model_path")
    requested_prompt = data.get("prompt")
    requested_voice = data.get("voice")
    force_reload = data.get("force_reload", False)

    # Force reload if requested
    if force_reload:
        logger.info(
            "Force reload requested, reloading model regardless of settings changes"
        )
        return True

    # Check if model already loaded
    if model_loader.runtime_manager.current_model_path != model_path:
        # Different model, always reload
        return True

    # Same model, check if settings changed
    logger.info(f"Model already loaded: {model_path}, checking if settings changed")

    # Get current instructions and voice from the model loader
    current_instructions, current_voice = (
        model_loader._get_agent_instructions_and_voice()
    )

    # Compare prompt and voice settings
    if requested_prompt is not None and requested_prompt != current_instructions:
        logger.info("Prompt has changed, forcing model reload")
        return True

    if requested_voice is not None and requested_voice != current_voice:
        logger.info("Voice has changed, forcing model reload")
        return True

    logger.info("No settings changed, no need to reload model")
    return False


def reload_model_in_background(model_loader, model_path, force_reload, reload_lock):
    """Reload the model in a background thread.

    Args:
        model_loader: The model loader instance
        model_path: Path to the model file
        force_reload: Whether to force reload even if model is already loaded
        reload_lock: Thread lock for synchronization
    """
    # Use the lock to ensure thread safety
    with reload_lock:
        try:
            logger.info(
                f"Triggering reload in background thread for model: {model_path}"
            )
            reload_success = model_loader.request_reload(
                model_path, force_reload=force_reload
            )
            if not reload_success:
                logger.error(f"Failed to request model reload for: {model_path}")
                # Notify UI that reload failed
                try:
                    model_loader._emit_socketio_event(
                        "reload-error",
                        {"message": f"Failed to start reload for model: {model_path}"},
                    )
                except Exception as e:
                    logger.error(f"Error notifying UI of reload failure: {e}")
        except Exception as e:
            logger.error(f"Error in background reload thread: {e}")
            logger.error(f"Traceback: {traceback.format_exc()}")
            # Notify UI of the error
            try:
                model_loader._emit_socketio_event(
                    "reload-error", {"message": f"Error in reload: {str(e)}"}
                )
            except Exception as socket_err:
                logger.error(f"Error notifying UI of reload error: {socket_err}")
