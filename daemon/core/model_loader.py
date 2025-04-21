"""Model loader for the bitHuman Visual Agent Application."""

import asyncio
import os
import tempfile
import threading
import time
from typing import Any, Literal, Optional

import cv2
import soundfile
from livekit import rtc
from livekit.agents import utils, vad
from livekit.agents.voice.avatar import QueueAudioOutput
from livekit.plugins import silero
from loguru import logger

from bithuman.utils.agent import LocalAvatarRunner
from daemon.core.avatar import EchoAgent, EchoAgentSession, EchoLocalAudioIO
from daemon.core.model_runtime import RuntimeManager
from daemon.core.voice_agent import VoiceAgent
from daemon.utils import assets_manager
from daemon.utils.helpers import safe_emit
from daemon.utils.logging import LogCategory, debug, error, model as log_model, warning
from daemon.web_service import WebFrameStreamer


class ModelLoader:
    """Handles loading and reloading of models."""

    def __init__(self):
        """Initialize the ModelLoader."""
        self.runtime_manager = RuntimeManager()
        self.current_visual_agent_runner: Optional[LocalAvatarRunner] = None
        self.current_video_player = (
            None  # VideoFrameHandler (import avoided for circular dependency)
        )
        self.current_local_audio: Optional[EchoLocalAudioIO] = None
        self.current_agent_session: Optional[EchoAgentSession] = None
        self.vad: Optional[vad.VAD] = None

        self.reload_event = asyncio.Event()
        self.new_model_path: Optional[str] = None
        self.reload_requested: bool = False
        # Add thread lock for synchronizing access to reload state
        self.reload_lock = threading.RLock()
        # Add timestamp for tracking when reload was requested
        self.reload_requested_time = 0
        # Store reference to Flask app when set
        self.flask_app = None
        # Store reference to SocketIO
        self.socketio = None

        self.is_muted = False
        self.current_mode: Literal["agent", "avatar"] = "agent"  # Default mode is agent
        self.current_sound_file = None  # Path to currently playing sound file
        self._active = True

    def _get_vad(self) -> vad.VAD:
        if self.vad is None:
            self.vad = silero.VAD.load(
                min_speech_duration=0.05,
                min_silence_duration=2,
                activation_threshold=0.1,
                sample_rate=8000,
            )
        return self.vad

    def set_mode(
        self, mode: Literal["agent", "avatar"], force_update: bool = False
    ) -> bool:
        """Set the current operating mode for the model.

        Args:
            mode: Operating mode, either "agent" or "avatar"

        Returns:
            bool: True if successful, False otherwise
        """
        if mode not in ["agent", "avatar"]:
            logger.error(f"Invalid mode: {mode}. Must be 'agent' or 'avatar'")
            return False

        # Update model state
        if self.current_mode == mode and not force_update:
            return True

        self.current_mode = mode

        # Log the change

        logger.info(f"Mode set to: {mode}")

        if not self.current_agent_session or not self.current_visual_agent_runner:
            return False

        if self.current_mode == "agent":
            instructions, voice = self._get_agent_instructions_and_voice()
            agent = VoiceAgent(instructions=instructions, voice=voice)
        else:
            agent = EchoAgent(vad=self._get_vad())

        # update agent
        loop = self.current_agent_session._loop
        if self.current_agent_session._activity:

            def interrupt_and_update_agent():
                self.current_agent_session.interrupt()
                self.current_agent_session.update_agent(agent)
                self.current_agent_session.output.audio.clear_buffer()

            loop.call_soon_threadsafe(interrupt_and_update_agent)
        else:
            self.current_agent_session._agent = agent

        # update idle timeout parameter for runtime
        self.current_visual_agent_runner._bithuman_runtime.set_idle_timeout(
            0.001 if self.current_mode == "agent" else 0.5
        )

        # update audio output
        self.current_local_audio.set_audio_output_enabled(self.current_mode == "agent")

        return True

    def play_sound_file(self, file_path: str) -> bool:
        """Play a sound file through the avatar.

        Args:
            file_path: Path to the sound file to play

        Returns:
            bool: True if successful, False otherwise
        """
        if not file_path or not os.path.exists(file_path):
            logger.error(f"Invalid sound file path: {file_path}")
            return False

        if not self.current_agent_session:
            logger.error("No agent session found")
            return False

        # Store the sound file path
        self.current_sound_file = file_path

        # Log the action
        logger.info(f"Playing sound file: {file_path}")
        audio, sr = soundfile.read(file_path, dtype="int16", always_2d=True)
        audio = audio.T  # (channels, samples)
        audio_frame = rtc.AudioFrame(
            data=audio.tobytes(),
            sample_rate=sr,
            num_channels=audio.shape[0],
            samples_per_channel=audio.shape[1],
        )

        async def audio_generator():
            yield audio_frame

        def interrupt_and_say():
            self.current_agent_session.interrupt()
            self.current_agent_session.say(text="", audio=audio_generator())

        loop = self.current_agent_session._loop
        loop.call_soon_threadsafe(interrupt_and_say)

        return True

    def toggle_mute(self) -> bool:
        self.is_muted = not self.is_muted
        logger.info(f"Mute state toggled to {self.is_muted}")

        # mute the microphone
        if self.current_local_audio:
            # self.current_local_audio._update_microphone(enable=False)
            self.current_local_audio._agent.input.set_audio_enabled(
                enable=not self.is_muted
            )

        # mute the bithuman runtime
        if self.current_visual_agent_runner:
            self.current_visual_agent_runner._bithuman_runtime.set_muted(self.is_muted)

        return self.is_muted

    def set_flask_app(self, app, socketio):
        """Set the Flask app and SocketIO references.

        Args:
            app: The Flask application
            socketio: The SocketIO instance
        """
        self.flask_app = app
        self.socketio = socketio
        log_model("Flask app and SocketIO references set in ModelLoader")

    def _emit_socketio_event(self, event_name, data):
        """Safely emit a SocketIO event with proper app context.

        Args:
            event_name: Name of the event to emit
            data: Data to send with the event
        """
        if not self.flask_app or not self.socketio:
            warning(
                "Cannot emit SocketIO event - no Flask app or SocketIO instance",
                LogCategory.MODEL,
            )
            return

        try:
            # Create an app context to avoid the "Working outside of application context" error
            with self.flask_app.app_context():
                # Use safe_emit to handle Werkzeug errors
                safe_emit(self.socketio, event_name, data)
                log_model(f"Emitted {event_name} event with data: {data}")
        except Exception as e:
            warning(
                f"Error emitting SocketIO event {event_name}: {e}", LogCategory.MODEL
            )

    def _load_user_settings(self) -> dict[str, Any]:
        """Load user settings from settings.json in the user data directory.

        Returns:
            Dictionary containing user settings or empty dict if file not found
        """
        try:
            # Use settings_utils to get the user settings
            return assets_manager.load_settings()
        except Exception as e:
            error(f"Error loading user settings: {e}", LogCategory.MODEL)
            return {}

    def _get_agent_instructions_and_voice(self) -> tuple[str, str]:
        """Get agent instructions and voice from user settings or defaults.

        Returns:
            Tuple of (instructions, voice)
        """
        settings = self._load_user_settings()

        # Get instructions from settings.prompt or use default
        default_instructions = assets_manager.get_setting(
            "agent.defaultInstructions",
            "Your name is Alice. You are an expert in dinosaurs. You educate people about dinosaurs, their ecosystem, and their extinction.",
        )
        instructions = settings.get("prompt", "") or default_instructions

        # Get voice from settings.voice or use default
        default_voice = assets_manager.get_setting("defaults.voice", "alloy")
        voice = settings.get("voice", "") or default_voice

        log_model(f"Using agent instructions: {instructions[:50]}... (truncated)")
        log_model(f"Using voice: {voice}")

        return instructions, voice

    async def _load_model(
        self,
        model_path: str,
        api_secret: Optional[str] = None,
        is_initial_load: bool = False,
        notify_ui: bool = False,
    ) -> tuple[bool, Optional[str], Optional[Any]]:
        """Internal helper method to load/reload a model.

        Args:
            model_path: Path to the model file
            api_secret: Optional API secret
            is_initial_load: Whether this is the initial load (vs. a reload)
            notify_ui: Whether to send UI notifications

        Returns:
            Tuple of (success, error_message, runtime)
        """
        try:
            action = "Initializing" if is_initial_load else "Reloading"
            log_model(f"{action} model: {model_path}")

            # Resolve default model if none provided
            if not model_path:
                # Use settings utils to get the user data directory and default model
                user_data_dir = assets_manager.get_user_data_dir()

                # Use the default model from settings
                default_model = assets_manager.get_default_model_path()
                model_path = os.path.join(
                    user_data_dir,
                    assets_manager.get_asset_path("modelsDir"),
                    default_model,
                )
                debug(f"Using default model: {model_path}", LogCategory.MODEL)
                if not os.path.exists(model_path):
                    return (
                        False,
                        "Default model not found",
                        None,
                    )

            # Get API secret from settings if not provided
            if not api_secret:
                api_secret = assets_manager.get_api_key("bithuman")

            # Notify clients if requested
            if notify_ui:
                self._emit_socketio_event(
                    "reload-started", {"model": os.path.basename(model_path)}
                )

            # Stop current components if they exist and this is a reload
            if not is_initial_load:
                # Stop current visual agent runner if it exists
                if self.current_visual_agent_runner:
                    log_model("Stopping current visual agent runner...")
                    await self.current_visual_agent_runner.aclose()
                    log_model("Current visual agent runner stopped")

                # Clean up OpenAI connection if it exists
                if self.current_local_audio and hasattr(
                    self.current_local_audio, "_agent"
                ):
                    log_model("Cleaning up OpenAI connection...")
                    try:
                        await self.current_local_audio._agent.aclose()
                    except Exception as e:
                        warning(
                            f"Error cleaning up OpenAI connection: {e}",
                            LogCategory.MODEL,
                        )

            # Create runtime with the model
            log_model(f"Creating runtime with model: {model_path}")

            # Check if the file exists
            if not os.path.exists(model_path):
                raise FileNotFoundError(
                    f"Visual Agent model file not found at: {model_path}"
                )

            runtime = await self.runtime_manager.create_runtime(model_path, api_secret)
            first_frame = runtime.get_first_frame()
            visual_agent_options = self.runtime_manager.create_visual_agent_options(
                first_frame
            )
            log_model(
                f"Runtime created with dimensions: {visual_agent_options.video_width}x{visual_agent_options.video_height}"
            )

            # Create WebVideoPlayer during initial load only
            if is_initial_load:
                log_model("Creating frame streamer")
                self.current_video_player = WebFrameStreamer(
                    window_title=assets_manager.get_setting(
                        "ui.windowTitle", "bitHuman Visual Agent"
                    ),
                    quality=assets_manager.get_setting("ui.quality", 85),
                    max_fps=assets_manager.get_setting("ui.fpsLimit", 30),
                    auto_open_browser=assets_manager.get_setting(
                        "ui.autoOpenBrowser", False
                    ),
                )
                self.current_video_player.start()
                log_model("Frame streamer created and started")

            # Set up audio components
            log_model("Setting up audio components")
            interim_audio_buffer = QueueAudioOutput(
                sample_rate=visual_agent_options.audio_sample_rate
            )
            self.current_agent_session = EchoAgentSession()
            self.current_agent_session.output.audio = interim_audio_buffer
            buffer_size = assets_manager.get_setting("audio.bufferSize", 3)
            self.current_local_audio = EchoLocalAudioIO(
                session=self.current_agent_session,
                agent_audio_output=interim_audio_buffer,
                buffer_size=buffer_size,
            )
            await self.current_local_audio.start()
            log_model("Audio components initialized")

            # Create visual agent runner
            log_model("Creating visual agent runner")
            self.current_visual_agent_runner = LocalAvatarRunner(
                bithuman_runtime=runtime,
                audio_input=interim_audio_buffer,
                audio_output=self.current_local_audio,
                video_output=self.current_video_player,
                options=visual_agent_options,
                runtime_kwargs={"idle_timeout": None},
            )

            # Use retry logic for OpenAI connection if reloading
            max_retries = 3 if not is_initial_load else 1
            retry_delay = 1.0  # seconds

            for attempt in range(max_retries):
                try:
                    # Start the visual agent runner
                    await self.current_visual_agent_runner.start()
                    runtime.set_idle_timeout(
                        0.001 if self.current_mode == "agent" else 0.5
                    )

                    # Make sure HTTP context is properly initialized before starting the agent
                    try:
                        utils.http_context._new_session_ctx()
                    except Exception:
                        # If already initialized, this will raise an exception - we can ignore it
                        pass

                    # Get instructions and voice from user settings or defaults
                    instructions, voice = self._get_agent_instructions_and_voice()
                    if not is_initial_load:
                        log_model(
                            f"Using refreshed agent instructions: {instructions[:50]}... (truncated)"
                        )
                        log_model(f"Using refreshed voice: {voice}")

                    # Start the agent session
                    self.set_mode(mode=self.current_mode, force_update=True)
                    await self.current_agent_session.start(
                        agent=self.current_agent_session.current_agent
                    )
                    log_model("Visual agent runner started successfully")

                    # Notify clients that reload is complete if requested
                    if notify_ui:
                        self._emit_socketio_event(
                            "reload-complete",
                            {"model": os.path.basename(model_path), "success": True},
                        )

                    return True, None, runtime
                except Exception as e:
                    if "OpenAI S2S connection" in str(e) and attempt < max_retries - 1:
                        warning(
                            f"OpenAI connection attempt {attempt + 1} failed, retrying in {retry_delay} seconds...",
                            LogCategory.MODEL,
                        )
                        await asyncio.sleep(retry_delay)
                        continue

                    # Notify clients of failure if requested
                    if notify_ui:
                        self._emit_socketio_event(
                            "reload-complete",
                            {
                                "model": os.path.basename(model_path),
                                "success": False,
                                "error": str(e),
                            },
                        )

                    return False, str(e), None

            # This should never be reached due to the return inside the loop
            return False, "Unexpected error - reached end of loading function", None

        except Exception as e:
            import traceback

            traceback.print_exc()
            error_msg = f"Error {action.lower()} model: {e}"
            error(error_msg, LogCategory.MODEL)

            # Notify UI of failure if requested
            if notify_ui:
                self._emit_socketio_event(
                    "reload-complete",
                    {
                        "model": os.path.basename(model_path),
                        "success": False,
                        "error": str(e),
                    },
                )

            return False, str(e), None

    async def initialize_model(
        self, model_path: str, api_secret: Optional[str] = None
    ) -> tuple[bool, Optional[str]]:
        """Initialize the visual agent model.

        Args:
            model_path: Path to the model file
            api_secret: Optional API secret

        Returns:
            Tuple of (success, error_message)
        """
        success, error_msg, _ = await self._load_model(
            model_path=model_path,
            api_secret=api_secret,
            is_initial_load=True,
            notify_ui=False,
        )
        return success, error_msg

    async def reload_model(self, model_path: Optional[str] = None) -> bool:
        """Reload the model with the specified path or the current model if no path provided.

        Args:
            model_path: Optional path to a new model to load

        Returns:
            True if reload was successful, False otherwise
        """
        # Use provided model_path or current model
        model_to_load = model_path or self.new_model_path
        if not model_to_load:
            error("No model path provided for reload", LogCategory.MODEL)
            return False

        # Get API secret from settings
        api_secret = assets_manager.get_api_key("bithuman")

        # Load the model
        success, _, _ = await self._load_model(
            model_path=model_to_load,
            api_secret=api_secret,
            is_initial_load=False,
            notify_ui=True,
        )

        # Reset reload flags
        with self.reload_lock:
            self.reload_requested = False
            self.new_model_path = None
            self.reload_requested_time = 0

        return success

    async def handle_reload_events(self, stop_event: asyncio.Event) -> None:
        """Monitor and handle model reload events.

        Args:
            stop_event: Event to signal when to stop monitoring
        """
        log_model("Starting reload event handler")

        while not stop_event.is_set():
            try:
                # Check for reload event
                if self.reload_event.is_set():
                    self.reload_event.clear()
                    current_new_model_path = None

                    with self.reload_lock:
                        if self.new_model_path:
                            # Store the path locally before we might reset it
                            current_new_model_path = self.new_model_path

                    if current_new_model_path:
                        log_model(
                            f"Processing reload request for model: {current_new_model_path}"
                        )
                        try:
                            success = await self.reload_model(current_new_model_path)
                            if success:
                                log_model("Model reload completed successfully")
                            else:
                                warning("Model reload failed", LogCategory.MODEL)
                        except Exception as e:
                            error(f"Error during model reload: {e}", LogCategory.MODEL)

                            # Notify UI
                            self._emit_socketio_event(
                                "reload-error",
                                {"message": f"Error reloading model: {str(e)}"},
                            )

                # Check for polling-based reload request if using background polling mode
                with self.reload_lock:
                    if self.reload_requested and not self.reload_event.is_set():
                        # Get elapsed time since request
                        elapsed = time.time() - self.reload_requested_time

                        # Only proceed with reload if we've waited at least 0.5 seconds
                        # This helps debounce multiple rapid reload requests
                        if elapsed >= 0.5:
                            log_model(
                                f"Detected pending reload request for {self.new_model_path}"
                            )
                            self.reload_event.set()  # Trigger reload on next iteration

                # Small delay to prevent busy waiting
                await asyncio.sleep(0.1)

            except asyncio.CancelledError:
                # Gracefully exit if the task is cancelled
                log_model("Reload event handler cancelled")
                break
            except Exception as e:
                error(f"Error in reload event handler: {e}", LogCategory.MODEL)

                # Add a delay after an error to prevent rapid error loops
                await asyncio.sleep(1.0)

    def get_status(self) -> dict[str, Any]:
        """Get the current status of the model loader.

        Returns:
            Dictionary containing current status
        """
        try:
            with self.reload_lock:  # Use lock to ensure consistent state
                is_reloading = self.reload_requested or self.reload_event.is_set()

                # Check if we have a valid model loaded
                model_ready = (
                    self.runtime_manager.current_runtime is not None
                    and self.current_visual_agent_runner is not None
                )

                # Get current model path
                model_path = self.runtime_manager.current_model_path or "unknown"
                if model_path and os.path.exists(model_path):
                    model_name = os.path.basename(model_path)
                else:
                    model_name = "unknown"

                # Get mute state if available
                return {
                    "is_ready": model_ready and not is_reloading,
                    "is_reloading": is_reloading,
                    "is_muted": self.is_muted,
                    "current_mode": self.current_mode,
                    "current_sound_file": self.current_sound_file,
                    "model_path": model_path,
                    "model_name": model_name,
                    "reload_requested": self.reload_requested,
                    "reload_time": self.reload_requested_time,
                }

        except Exception as e:
            error(f"Error getting status: {e}", LogCategory.MODEL)
            return {
                "is_ready": False,
                "is_reloading": False,
                "is_muted": False,
                "current_mode": self.current_mode,
                "current_sound_file": self.current_sound_file,
                "model_path": model_path,
                "model_name": model_name,
                "error": str(e),
            }

    def request_reload(self, model_path: str, force_reload: bool = False) -> bool:
        """Request a model reload.

        Args:
            model_path: Path to the model to load
            force_reload: Whether to force reload even if model is already loaded

        Returns:
            True if request was accepted, False otherwise
        """
        try:
            with self.reload_lock:
                # Check if model is already loaded and we're not forcing a reload
                if (
                    not force_reload
                    and self.runtime_manager.current_model_path == model_path
                ):
                    # Only update the current model path if it's different
                    log_model(
                        f"Current model: {self.runtime_manager.current_model_path}"
                    )

                    if self.reload_requested:
                        warning(
                            "Reload already in progress, ignoring duplicate request",
                            LogCategory.MODEL,
                        )
                        return False

                    log_model("Model already loaded, not reloading")
                    return True

                # Set new model path
                log_model(f"Setting new model path: {model_path}")
                self.new_model_path = model_path
                self.reload_requested = True
                self.reload_requested_time = time.time()

                # Signal reload
                self.reload_event.set()

                return True

        except Exception as e:
            error(f"Error requesting reload: {e}", LogCategory.MODEL)
            return False

    async def cleanup(self) -> None:
        """Clean up resources."""
        try:
            # Stop the current visual agent runner
            if self.current_visual_agent_runner:
                self.current_visual_agent_runner.stop()
                await self.current_visual_agent_runner.aclose()

            # Clean up audio resources
            if self.current_local_audio:
                await self.current_local_audio.aclose()

            # Clean up OpenAI connection if it exists
            if self.current_local_audio and hasattr(self.current_local_audio, "_agent"):
                try:
                    await self.current_local_audio._agent.aclose()
                except Exception as e:
                    warning(
                        f"Error cleaning up OpenAI connection: {e}", LogCategory.MODEL
                    )

            if self.current_agent_session:
                await self.current_agent_session.aclose()
                self.current_agent_session = None

            # Reset instance variables
            self.current_visual_agent_runner = None
            self.current_local_audio = None
            self.new_model_path = None
            self.reload_requested = False
            self._active = False
        except Exception as e:
            error(f"Error during cleanup: {e}", LogCategory.MODEL)

    async def get_cover_photo_from_model(self, model_path: str) -> Optional[str]:
        """Get the first frame of the model and save it as a cover photo in a temporary directory.

        Args:
            model_path: Path to the model file

        Returns:
            Path to the temporary cover photo or None if failed
        """
        try:
            log_model(f"Getting cover photo for model: {model_path}")

            # Get API secret for model loading
            api_secret = assets_manager.get_api_key("bithuman")
            log_model(f"Using API secret: {api_secret[:5]}... (truncated)")

            # Create runtime with the model
            log_model(f"Creating runtime with model: {model_path}")
            runtime = await self.runtime_manager.create_runtime(
                model_path, api_secret=api_secret
            )
            log_model("Runtime created successfully")

            # Get the first frame
            log_model("Getting first frame from model")
            first_frame = runtime.get_first_frame()
            if first_frame is None:
                error("Failed to get first frame from model", LogCategory.MODEL)
                return None
            log_model("Successfully retrieved first frame from model")

            # Get dimensions from the frame
            visual_agent_options = self.runtime_manager.create_visual_agent_options(
                first_frame
            )
            log_model(
                f"Cover photo dimensions: {visual_agent_options.video_width}x{visual_agent_options.video_height}"
            )

            # Generate output filename from the model name
            model_name = os.path.basename(model_path)
            model_name_without_ext = os.path.splitext(model_name)[0]

            # Create a temporary file with the right extension
            temp_file = tempfile.NamedTemporaryFile(
                suffix=f"_{model_name_without_ext}.jpg", delete=False
            )
            temp_file.close()
            cover_photo_path = temp_file.name

            # Save the image to the temporary file
            log_model(f"Saving cover photo to: {cover_photo_path}")
            cv2.imwrite(cover_photo_path, first_frame)
            log_model(f"Cover photo saved to temporary location: {cover_photo_path}")

            return cover_photo_path
        except Exception as e:
            error(f"Error getting cover photo: {e}", LogCategory.MODEL)
            # Print full stack trace to help with debugging
            import traceback

            error(f"Stack trace: {traceback.format_exc()}", LogCategory.MODEL)
            return None
