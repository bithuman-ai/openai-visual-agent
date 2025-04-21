"""Model runtime management for the bitHuman Visual Agent Application."""

import os
from typing import Optional

import numpy as np
from livekit.agents.voice.avatar import AvatarOptions
from loguru import logger

from bithuman import AsyncBithuman
from daemon.utils import assets_manager


class RuntimeManager:
    """Manages the bitHuman runtime."""

    def __init__(self):
        """Initialize the RuntimeManager."""
        self.current_runtime: Optional[AsyncBithuman] = None
        self.current_model_path: Optional[str] = None

    async def create_runtime(
        self, model_path: str, api_secret: Optional[str] = None
    ) -> AsyncBithuman:
        """Initialize the runtime with a specific model.

        Creates a new AsyncBithuman instance with the provided model path and
        optional API secret.

        Args:
            model_path: Path to the model file
            api_secret: BitHuman API secret for authentication (from settings.json)

        Returns:
            Initialized AsyncBithuman runtime
        """
        # Get values from environment variables if not provided as arguments
        visual_agent_model = model_path

        # Use the API secret from settings if not explicitly provided
        bithuman_api_secret = api_secret or assets_manager.get_api_key("bithuman")

        if not visual_agent_model:
            raise ValueError("Visual Agent model path must be provided")
        if not os.path.exists(visual_agent_model):
            raise ValueError(
                f"Visual Agent model file not found at: {visual_agent_model}"
            )
        if not bithuman_api_secret:
            raise ValueError("BitHuman API secret must be provided via settings.json")

        try:
            logger.info(
                f"Initializing bitHuman runtime with model: {visual_agent_model}"
            )
            logger.info(f"API secret present: {bool(bithuman_api_secret)}")

            runtime = await AsyncBithuman.create(
                model_path=visual_agent_model, api_secret=bithuman_api_secret
            )
            logger.info("bitHuman runtime initialized successfully")
            self.current_runtime = runtime
            self.current_model_path = visual_agent_model
            return runtime
        except Exception as e:
            error_msg = f"Failed to initialize bitHuman runtime: {e}"
            logger.error(error_msg)

            # Get detailed exception information
            import traceback

            logger.error(f"Stack trace: {traceback.format_exc()}")

            # Check if API key related error
            if (
                "api_key" in str(e).lower()
                or "api key" in str(e).lower()
                or "auth" in str(e).lower()
            ):
                logger.error(
                    "This appears to be an API key related error. Check that your BitHuman API key is correctly set in settings.json"
                )

            # Check for network related errors
            if (
                "timeout" in str(e).lower()
                or "connect" in str(e).lower()
                or "network" in str(e).lower()
            ):
                logger.error(
                    "This appears to be a network related error. Check your internet connection."
                )

            raise RuntimeError(error_msg)

    def create_visual_agent_options(
        self, first_frame: np.ndarray | None
    ) -> AvatarOptions:
        """Create visual agent options based on the first frame.

        Args:
            first_frame: The first frame from the bitHuman runtime

        Returns:
            AvatarOptions for the visual agent runner
        """
        if first_frame is None:
            raise ValueError("Failed to get the first frame")

        if not isinstance(first_frame, np.ndarray):
            raise TypeError(
                f"Expected numpy array for first frame, got {type(first_frame)}"
            )

        if len(first_frame.shape) != 3:
            raise ValueError(
                f"Expected 3D array for first frame, got shape {first_frame.shape}"
            )

        if first_frame.shape[2] != 3:
            raise ValueError(
                f"Expected RGB image (3 channels), got {first_frame.shape[2]} channels"
            )

        output_width, output_height = first_frame.shape[1], first_frame.shape[0]

        if output_width <= 0 or output_height <= 0:
            raise ValueError(
                f"Invalid frame dimensions: {output_width}x{output_height}"
            )

        return AvatarOptions(
            video_width=output_width,
            video_height=output_height,
            video_fps=25,
            audio_sample_rate=16000,
            audio_channels=1,
        )
