"""
SwadesAI voice agent — appointment booking, live monitoring, takeover, warm transfer.
Run: python agent.py dev
Console test: python agent.py console
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from collections.abc import AsyncGenerator, AsyncIterable
from pathlib import Path

from dotenv import load_dotenv

from livekit import rtc
from livekit.agents import (
    Agent,
    AgentServer,
    AgentSession,
    JobContext,
    RunContext,
    cli,
    inference,
    llm,
    room_io,
)
from livekit.agents.beta.workflows import WarmTransferTask
from livekit.agents.beta.workflows.utils import InstructionParts
from livekit.agents.llm import ToolError, function_tool
from livekit.agents.voice import ModelSettings
from livekit.plugins import groq

from booking import init_db
from monitor import MonitorPublisher
from speech_filters import parse_all_leaked_tool_calls, sanitize_stream_chunk
from summary import generate_and_save_summary, generate_transfer_brief
from voice_config import build_instructions, build_stt_tts, greeting_instructions, normalize_language

ENV_PATHS = (
    Path(__file__).resolve().parent.parent / ".env",
    Path(__file__).resolve().parent / ".env",
    Path(__file__).resolve().parent.parent / ".env.local",
    Path(__file__).resolve().parent / ".env.local",
)


def load_project_env() -> None:
    for path in ENV_PATHS:
        if path.exists():
            load_dotenv(path, override=True)


load_project_env()

logger = logging.getLogger("swades-agent")

# --- Configuration (from environment) ---

AGENT_NAME = os.getenv("AGENT_NAME", "swades-agent")
# 8b uses far fewer tokens than 70b — important on Groq free tier (100k TPD)
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.1-8b-instant")
SIP_TRUNK_ID = os.getenv("LIVEKIT_SIP_OUTBOUND_TRUNK")
SUPERVISOR_PHONE = os.getenv("LIVEKIT_SUPERVISOR_PHONE_NUMBER")
SIP_NUMBER = os.getenv("LIVEKIT_SIP_NUMBER")
AGENT_LANGUAGE = normalize_language(os.getenv("AGENT_LANGUAGE"))


# --- Agent ---


class ReceptionistAgent(Agent):
    def __init__(self, monitor: MonitorPublisher) -> None:
        super().__init__(instructions=build_instructions(AGENT_LANGUAGE))
        self._monitor = monitor
        self._transfer_in_progress = False
        self._transfer_queued = False
        monitor.set_transfer_handler(self.queue_transfer)

    async def on_enter(self) -> None:
        self.session.generate_reply(
            instructions=greeting_instructions(AGENT_LANGUAGE)
        )

    async def _schedule_leaked_tool(self, name: str, args: dict[str, str]) -> None:
        if name == "record_caller_info":
            await self._monitor.update_collected_data(
                name=args.get("name"),
                reason=args.get("reason"),
                preferred_date=args.get("preferred_date"),
                preferred_time=args.get("preferred_time"),
                phone=args.get("phone"),
                booking_status="collecting",
            )
            return

        if name == "transfer_to_human":
            reason = args.get("reason", "caller request")
            await self.queue_transfer(reason)
            return

        if name == "check_availability":
            preferred_date = args.get("preferred_date") or self._monitor._collected_data.get(
                "preferred_date"
            )
            if preferred_date:
                await self._monitor._maybe_check_availability_and_reply(str(preferred_date))
            return

        if name == "book_appointment":
            await self._monitor._apply_tool_collected_data(name, args)
            return

        if name == "end_call":
            await self._monitor.end_call()
            return

    def _maybe_handle_leaked_tool(self, text: str) -> None:
        for name, args in parse_all_leaked_tool_calls(text):
            asyncio.create_task(self._schedule_leaked_tool(name, args))

    async def llm_node(
        self,
        chat_ctx: llm.ChatContext,
        tools: list[llm.Tool],
        model_settings: ModelSettings,
    ) -> AsyncGenerator[llm.ChatChunk | str, None]:
        async for chunk in Agent.default.llm_node(
            self, chat_ctx, tools, model_settings
        ):
            if isinstance(chunk, str):
                if chunk.isspace():
                    yield chunk
                    continue
                self._maybe_handle_leaked_tool(chunk)
                cleaned = sanitize_stream_chunk(chunk)
                if cleaned:
                    yield cleaned
                continue

            if isinstance(chunk, llm.ChatChunk) and chunk.delta and chunk.delta.content:
                content = chunk.delta.content
                if content.isspace():
                    yield chunk
                    continue
                self._maybe_handle_leaked_tool(content)
                cleaned = sanitize_stream_chunk(content)
                if not cleaned and not chunk.delta.tool_calls:
                    continue
                if cleaned != content:
                    chunk.delta.content = cleaned

            yield chunk

    def tts_node(self, text: AsyncIterable[str], model_settings: ModelSettings):
        async def filtered():
            async for chunk in text:
                if not chunk:
                    continue
                if chunk.isspace():
                    yield chunk
                    continue
                cleaned = sanitize_stream_chunk(chunk)
                if cleaned:
                    yield cleaned

        return Agent.default.tts_node(self, filtered(), model_settings)

    async def queue_transfer(self, reason: str = "caller request") -> None:
        """Ask the LLM to invoke transfer_to_human in the proper tool context."""
        if self._transfer_in_progress or self._transfer_queued:
            return
        self._transfer_queued = True
        logger.info("queueing transfer_to_human tool call: %s", reason)
        self.session.generate_reply(
            instructions=(
                f"The caller confirmed they want a human agent. Reason: {reason}. "
                "Silently invoke transfer_to_human with that reason now. "
                "Do not say tool names or JSON aloud."
            )
        )

    async def _execute_transfer(self, reason: str) -> str:
        if self._transfer_in_progress:
            return "Transfer already in progress."
        self._transfer_in_progress = True
        self._transfer_queued = False

        if not SIP_TRUNK_ID or not SUPERVISOR_PHONE:
            logger.warning(
                "transfer requested but SIP is not configured "
                "(LIVEKIT_SIP_OUTBOUND_TRUNK / LIVEKIT_SUPERVISOR_PHONE_NUMBER)"
            )
            apology = self.session.say(
                "I'm sorry, I'm unable to transfer your call right now. "
                "I can take a message or help you with booking instead.",
                allow_interruptions=False,
            )
            await apology.wait_for_playout()
            self._transfer_in_progress = False
            return (
                "Human transfer is not configured yet. Apologize and offer to take a "
                "message or help with booking instead."
            )

        self._monitor.set_intent("escalation")
        self._monitor.set_action("transferring")
        await self._monitor.publish_call_status("transferring")
        await self._monitor.publish_state()

        brief = await generate_transfer_brief(
            self._monitor.transcript_lines,
            self._monitor.collected_data_snapshot(),
            reason,
        )
        await self._monitor.publish({"type": "transfer_brief", "text": brief})

        hold_intro = self.session.say(
            "I'll summarize your call for our team member and ask if they're available "
            "to take over. Please hold for a moment.",
            allow_interruptions=False,
        )
        await hold_intro.wait_for_playout()

        hold = self.session.say(
            "Please hold while I connect you with a team member.",
            allow_interruptions=False,
        )
        await hold.wait_for_playout()

        transfer_instructions = (
            f"Transfer reason from caller: {reason}\n\n"
            f"Prepared call summary:\n{brief}\n\n"
            "Follow these steps exactly:\n"
            "1. Greet the human agent and read the summary above clearly.\n"
            "2. Ask: 'Would you like me to connect the caller to you now?'\n"
            "3. If they clearly agree (yes, sure, go ahead, ready), call connect_to_caller.\n"
            "4. If they decline or are unavailable (no, busy, not now), "
            "call decline_transfer with a short reason.\n"
            "5. Never call connect_to_caller until they explicitly agree."
        )

        try:
            await WarmTransferTask(
                sip_call_to=SUPERVISOR_PHONE,
                sip_trunk_id=SIP_TRUNK_ID,
                sip_number=SIP_NUMBER,
                chat_ctx=self.chat_ctx,
                instructions=InstructionParts(extra=transfer_instructions),
                stt=self.session.stt,
                llm=self.session.llm,
                tts=self.session.tts,
            )
        except ToolError as exc:
            logger.warning("warm transfer failed: %s", exc)
            await self._monitor.publish_call_status("connected")
            self._monitor.set_action("idle")
            await self._monitor.publish_state()
            unavailable = self.session.say(
                "I'm sorry, our team isn't available right now. "
                "Is there anything else I can help you with?",
                allow_interruptions=False,
            )
            await unavailable.wait_for_playout()
            self._transfer_in_progress = False
            return (
                "The team is not available right now. Apologize and ask if you can "
                "help with anything else or take a message."
            )

        farewell = self.session.say(
            "You are now connected with my colleague. I'll step off the line.",
            allow_interruptions=False,
        )
        await farewell.wait_for_playout()
        self.session.shutdown()
        return "Transfer complete."

    @function_tool
    async def check_availability(self, context: RunContext, preferred_date: str) -> str:
        """Check open appointment slots for a given date (YYYY-MM-DD or natural date).

        Call this before booking to show the caller available times.
        """
        if self._monitor.is_booking_confirmed():
            return self._monitor.booking_confirmation_message()

        self._monitor.set_intent("booking")
        self._monitor.set_action("checking_availability")
        await self._monitor.update_collected_data(
            preferred_date=preferred_date,
            booking_status="checking",
        )
        await self._monitor.publish_state()
        return await self._monitor.availability_for_agent(preferred_date)

    @function_tool
    async def book_appointment(
        self,
        context: RunContext,
        name: str,
        reason: str,
        slot_datetime: str,
        phone: str,
    ) -> str:
        """Book an appointment after the caller confirms name, reason, slot, and phone.

        slot_datetime must match an available slot (YYYY-MM-DD HH:MM, 24-hour).
        """
        if self._monitor.is_booking_confirmed():
            return (
                "The appointment is already saved. Confirm the booking to the caller, "
                "ask if they need anything else or are all set to end the call, "
                "and use end_call once they confirm they are done."
            )

        self._monitor.set_intent("booking")
        self._monitor.set_action("booking")
        slot = slot_datetime.strip()
        date_part, _, time_part = slot.partition(" ")
        await self._monitor.update_collected_data(
            name=name,
            reason=reason,
            preferred_date=date_part or None,
            preferred_time=time_part or None,
            phone=phone,
            booking_status="collecting",
        )
        await self._monitor.publish_state()

        return await self._monitor.try_book(name, reason, slot_datetime, phone)

    @function_tool
    async def end_call(self, context: RunContext) -> str:
        """End the call after the appointment is booked and the caller confirms they are done.

        Only call after confirming the booking and the caller says they have no other questions.
        """
        if not self._monitor.is_booking_confirmed():
            return (
                "The appointment is not booked yet. Finish booking first, then ask "
                "if the caller is all set to end the call."
            )
        await self._monitor.end_call()
        return "Call ended."

    @function_tool
    async def transfer_to_human(self, context: RunContext, reason: str) -> str:
        """Transfer to a human agent for billing, complaints, or when caller asks for a person.

        Only call after the caller confirms they want to be transferred.
        """
        return await self._execute_transfer(reason)


# --- LiveKit server ---


server = AgentServer()


def _register_takeover_handler(
    room: rtc.Room,
    session: AgentSession,
    monitor: MonitorPublisher,
) -> None:
    @room.on("data_received")
    def on_data(data: rtc.DataPacket) -> None:
        if data.topic != "monitor":
            return
        try:
            msg = json.loads(data.data.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            return

        if msg.get("type") != "takeover":
            return

        action = msg.get("action")

        async def handle() -> None:
            if action == "start":
                monitor.set_takeover(True)
                monitor.set_action("takeover")
                await monitor.publish_call_status("takeover")
                await monitor.publish_state()
                session.input.set_audio_enabled(False)
                session.output.set_audio_enabled(False)
                session.interrupt()
            elif action == "end":
                monitor.set_takeover(False)
                monitor.set_action("idle")
                await monitor.publish_call_status("connected")
                await monitor.publish_state()
                session.input.set_audio_enabled(True)
                session.output.set_audio_enabled(True)

        asyncio.create_task(handle())


@server.rtc_session(agent_name=AGENT_NAME)
async def entrypoint(ctx: JobContext) -> None:
    # Job workers are separate processes — reload .env here
    load_project_env()

    groq_api_key = os.getenv("GROQ_API_KEY")
    if not groq_api_key:
        raise ValueError(
            "GROQ_API_KEY is missing. Add it to the repo root .env file and restart "
            "python agent.py dev"
        )

    init_db()
    ctx.log_context_fields = {"room": ctx.room.name}

    speech_stt, speech_tts = build_stt_tts(AGENT_LANGUAGE)
    logger.info("voice pipeline: language=%s", AGENT_LANGUAGE)

    session = AgentSession(
        stt=speech_stt,
        llm=groq.LLM(
            model=GROQ_MODEL,
            api_key=groq_api_key,
            parallel_tool_calls=False,
        ),
        tts=speech_tts,
        turn_handling={"turn_detection": inference.TurnDetector()},
    )

    monitor = MonitorPublisher(ctx.room, session)
    monitor.attach()
    _register_takeover_handler(ctx.room, session, monitor)

    agent = ReceptionistAgent(monitor)
    caller_disconnect_handled = False

    async def on_shutdown() -> None:
        # Persist booking if the agent confirmed but never invoked book_appointment
        await monitor._maybe_auto_book(force=True)
        summary = await generate_and_save_summary(
            ctx.room.name,
            monitor.transcript_lines,
        )
        await monitor.publish_call_status("ended")
        await monitor.publish({"type": "summary", "text": summary})

    ctx.add_shutdown_callback(on_shutdown)

    async def _shutdown_after_caller_left() -> None:
        nonlocal caller_disconnect_handled
        if caller_disconnect_handled:
            return
        caller_disconnect_handled = True
        logger.info("caller disconnected — shutting down agent session")
        session.shutdown()

    def _should_end_on_disconnect(participant: rtc.RemoteParticipant) -> bool:
        identity = participant.identity
        if identity.startswith("watcher") or identity.startswith("human-agent"):
            return False
        agent_kind = getattr(rtc.ParticipantKind, "PARTICIPANT_KIND_AGENT", None)
        if agent_kind is not None and participant.kind == agent_kind:
            return False
        if identity.startswith("agent") or "agent" in identity.lower():
            return False
        return True

    @ctx.room.on("participant_disconnected")
    def _on_participant_disconnected(participant: rtc.RemoteParticipant) -> None:
        if not _should_end_on_disconnect(participant):
            return
        asyncio.create_task(_shutdown_after_caller_left())

    # Connect before session.start so monitor events and on_enter can publish safely
    await ctx.connect()

    await session.start(
        agent=agent,
        room=ctx.room,
        room_options=room_io.RoomOptions(
            delete_room_on_close=False,
            # Keep caller connected if outbound SIP dial fails (e.g. Twilio trial rejection)
            close_on_disconnect=False,
        ),
    )

    await monitor.publish_call_status("connected")


if __name__ == "__main__":
    cli.run_app(server)
