import asyncio

import numpy as np
from livekit import rtc
from livekit.agents import NOT_GIVEN, NotGivenOr, stt, utils, vad
from livekit.agents.voice import Agent, AgentSession
from livekit.agents.voice.events import UserState
from loguru import logger

from bithuman import AudioChunk
from bithuman.utils.agent import LocalAudioIO


class EchoLocalAudioIO(LocalAudioIO):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._audio_output_enabled: bool = True

    def set_audio_output_enabled(self, enabled: bool) -> None:
        self._audio_output_enabled = enabled

    async def capture_frame(self, audio_chunk: AudioChunk) -> None:
        if not self._audio_output_enabled:
            return

        await super().capture_frame(audio_chunk)


class EchoAgent(Agent):
    def __init__(
        self,
        *,
        stt: NotGivenOr[stt.STT] = NOT_GIVEN,
        vad: NotGivenOr[vad.VAD] = NOT_GIVEN,
    ) -> None:
        super().__init__(
            instructions="",
            turn_detection="manual",
            stt=stt,
            vad=vad,
        )


class EchoAgentSession(AgentSession):
    async def _forward_echo_audio_task(
        self, buffer: utils.aio.Chan[rtc.AudioFrame]
    ) -> None:
        async for frame in buffer:
            if self.output.audio:
                await self.output.audio.capture_frame(frame)

    async def _forward_audio_task(self) -> None:
        logger.info("Forwarding audio task")
        audio_input = self.input.audio
        if audio_input is None:
            return

        echo_audio_buffer = utils.aio.Chan[rtc.AudioFrame](maxsize=10)
        echo_audio_atask = asyncio.create_task(
            self._forward_echo_audio_task(echo_audio_buffer)
        )
        bstreamer: utils.audio.AudioByteStream | None = None
        try:
            prev_state: UserState = "away"
            async for frame in audio_input:
                if not self._activity:
                    continue
                self._activity.push_audio(frame)

                if not isinstance(self.current_agent, EchoAgent):
                    continue

                # forward audio directly if in echo mode
                if bstreamer is None:
                    bstreamer = utils.audio.AudioByteStream(
                        sample_rate=frame.sample_rate,
                        num_channels=frame.num_channels,
                        samples_per_channel=int(frame.sample_rate / 100),
                    )
                for f in bstreamer.push(frame.data):
                    if self._activity.vad:
                        if self._user_state != "speaking":
                            f = rtc.AudioFrame(
                                data=np.zeros(
                                    f.samples_per_channel * f.num_channels,
                                    dtype=np.int16,
                                ).tobytes(),
                                sample_rate=f.sample_rate,
                                samples_per_channel=f.samples_per_channel,
                                num_channels=f.num_channels,
                            )
                        elif prev_state != "speaking":
                            # from silence to speaking
                            while echo_audio_buffer.qsize() > 0:
                                echo_audio_buffer.recv_nowait()
                    prev_state = self._user_state
                    try:
                        echo_audio_buffer.send_nowait(f)
                    except utils.aio.channel.ChanFull:
                        logger.warning("Echo audio buffer is full")
                        pass
        finally:
            if echo_audio_buffer:
                echo_audio_buffer.close()
            if echo_audio_atask:
                echo_audio_atask.cancel()
