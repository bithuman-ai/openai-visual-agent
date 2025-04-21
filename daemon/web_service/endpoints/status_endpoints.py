"""Status-related API endpoints for the bitHuman Visual Agent.

This module provides API endpoints for status information, including:
- Current model status
- Server status
- Mute control
"""

import traceback

from flask import Blueprint, jsonify, request
from loguru import logger

from daemon.utils import assets_manager


def register_endpoints(app, model_loader):
    """Register status-related endpoints with the Flask application.

    Args:
        app: The Flask application
        model_loader: The model loader instance
    """
    # Create a blueprint for status endpoints
    status_bp = Blueprint("status_endpoints", __name__)

    @status_bp.route("/api/status", methods=["GET"])
    def get_status():
        """Get the status of the Visual Agent server."""
        try:
            status = model_loader.get_status()
            return jsonify(status), 200

        except Exception as e:
            logger.error(f"Error in status check: {e}")
            logger.error(f"Traceback: {traceback.format_exc()}")
            return jsonify({"error": str(e)}), 500

    @status_bp.route("/health", methods=["GET"])
    def health_check():
        """Simple health check endpoint for monitoring."""
        import time

        return jsonify({"status": "ok", "uptime": time.time()})

    @status_bp.route("/api/constants", methods=["GET"])
    def get_constants():
        """Get constants and defaults for the client."""
        settings = assets_manager.load_settings()
        return jsonify(
            {
                "default_model_path": settings.get("assets", {}).get(
                    "defaultModel", ""
                ),
                "default_image_path": settings.get("assets", {}).get(
                    "defaultImage", ""
                ),
                "default_voice": settings.get("assets", {}).get("defaultVoice", ""),
            }
        )

    @status_bp.route("/api/toggle-mute", methods=["POST"])
    def toggle_mute():
        """Toggle the mute state of the Visual Agent."""
        try:
            if not model_loader:
                logger.error("No model loader available")
                return jsonify(
                    {"error": "Visual Agent not initialized", "muted": False}
                ), 500

            # Call the model_loader's toggle_mute method
            is_muted = model_loader.toggle_mute()
            logger.info(f"API requested toggle mute to {is_muted}")

            return jsonify({"success": True, "muted": is_muted}), 200

        except Exception as e:
            logger.error(f"Error toggling mute: {e}")
            logger.error(f"Traceback: {traceback.format_exc()}")
            return jsonify({"error": str(e), "muted": False}), 500

    @status_bp.route("/api/direct-toggle-mute", methods=["POST"])
    def direct_toggle_mute():
        """Direct endpoint to toggle mute (alternate to main server endpoint)."""
        try:
            if not model_loader:
                logger.error("No model loader available in direct endpoint")
                return jsonify(
                    {"error": "Model loader not available", "muted": False}
                ), 500

            # Call the model_loader's toggle_mute method
            is_muted = model_loader.toggle_mute()
            logger.info(f"Direct API toggle mute: {is_muted}")

            return jsonify({"success": True, "muted": is_muted}), 200

        except Exception as e:
            logger.error(f"Error in direct toggle mute: {e}")
            import traceback

            logger.error(traceback.format_exc())
            return jsonify({"error": str(e), "muted": False}), 500

    @status_bp.route("/api/set-mute-state", methods=["PUT"])
    def set_mute_state():
        """Set the mute state to a specific value."""
        try:
            if not model_loader:
                logger.error("No model loader available")
                return jsonify(
                    {"error": "Visual Agent not initialized", "muted": False}
                ), 500

            # Get requested mute state from request
            data = request.get_json()
            if not data or "muted" not in data:
                logger.error("No mute state provided in request")
                return jsonify({"error": "Missing muted parameter"}), 400

            requested_state = data["muted"]
            current_state = model_loader.is_muted

            logger.info(
                f"API requested set mute state to {requested_state}, current state is {current_state}"
            )

            # Only toggle if the requested state is different from current state
            if requested_state != current_state:
                logger.info(
                    f"Toggling mute state from {current_state} to {requested_state}"
                )
                model_loader.toggle_mute()
            else:
                logger.info(f"No change needed, mute state already {current_state}")

            return jsonify({"success": True, "muted": requested_state}), 200

        except Exception as e:
            logger.error(f"Error setting mute state: {e}")
            logger.error(f"Traceback: {traceback.format_exc()}")
            return jsonify({"error": str(e), "muted": False}), 500

    @status_bp.route("/api/toggle-mode", methods=["POST"])
    def toggle_mode():
        """Toggle between agent and avatar modes."""
        try:
            if model_loader:
                # Get current status to determine current mode
                status = model_loader.get_status()
                current_mode = status.get("current_mode", "agent")

                # Toggle to the opposite mode
                new_mode = "avatar" if current_mode == "agent" else "agent"
                success = model_loader.set_mode(new_mode)

                logger.info(f"Mode toggled to: {new_mode}, success: {success}")
                return jsonify({"success": True, "mode": new_mode}), 200
            else:
                logger.error("No model loader available in toggle mode endpoint")
                return jsonify(
                    {"error": "Model loader not available", "mode": "agent"}
                ), 500
        except Exception as e:
            logger.error(f"Error in toggle mode: {e}")
            import traceback

            logger.error(traceback.format_exc())
            return jsonify({"error": str(e), "mode": "agent"}), 500

    @status_bp.route("/api/play-sound", methods=["POST"])
    def play_sound():
        """Play a sound file through the avatar."""
        try:
            if not model_loader:
                logger.error("No model loader available in play sound endpoint")
                return jsonify({"error": "Model loader not available"}), 500

            # Get file path from request
            data = request.get_json()
            if not data or "file_path" not in data:
                logger.error("No file path provided in play sound request")
                return jsonify({"error": "Missing file_path parameter"}), 400

            file_path = data["file_path"]
            logger.info(f"Received request to play sound file: {file_path}")

            # Call the model_loader's play_sound_file method
            success = model_loader.play_sound_file(file_path)

            if success:
                logger.info(f"Successfully playing sound file: {file_path}")
                return jsonify(
                    {
                        "success": True,
                        "message": "Playing sound file",
                        "file_path": file_path,
                    }
                ), 200
            else:
                logger.error(f"Failed to play sound file: {file_path}")
                return jsonify(
                    {"success": False, "error": "Failed to play sound file"}
                ), 500

        except Exception as e:
            logger.error(f"Error playing sound file: {e}")
            import traceback

            logger.error(traceback.format_exc())
            return jsonify({"error": str(e)}), 500

    # Register the blueprint with the app
    app.register_blueprint(status_bp)
