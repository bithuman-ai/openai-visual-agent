"""Voice agent and audio input/output handling for the bitHuman Visual Agent Application."""

from livekit.agents import utils
from livekit.agents.voice import Agent
from livekit.plugins import openai

from daemon.utils import assets_manager


class VoiceAgent(Agent):
    """Agent implementation using voice models."""

    def __init__(self, instructions: str, voice: str) -> None:
        """Initialize the agent with required instructions and voice.

        Args:
            instructions: Custom instructions for the agent
            voice: Voice model to use (e.g., 'alloy', 'nova', etc.)
        """
        # Get OpenAI API key from settings
        api_key = assets_manager.get_api_key("openai")

        # Ensure HTTP context is initialized
        try:
            utils.http_context._new_session_ctx()
        except Exception:
            # If already initialized, this might raise an exception, which we can ignore
            pass

        super().__init__(
            instructions=instructions,
            llm=openai.realtime.RealtimeModel(
                voice=voice,
                api_key=api_key,
                model="gpt-4o-mini-realtime-preview-2024-12-17",
            ),
        )
