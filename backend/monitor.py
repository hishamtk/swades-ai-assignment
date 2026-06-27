"""Publish monitor events to the LiveKit room data channel."""

from __future__ import annotations

import asyncio
import json
import logging
import re
from collections.abc import Awaitable, Callable
from typing import Any

from livekit import rtc
from livekit.agents import AgentSession

from booking import (
    availability_message,
    create_booking,
    find_booking_by_phone_and_slot,
    format_slot_human,
    get_available_slots,
    parse_preferred_date,
)
from intake_tracker import (
    _extract_date_time,
    detect_pending_field,
    extract_phone_chunk,
    infer_fields_from_user_reply,
    is_user_call_end_confirmation,
    is_user_confirmation,
    is_user_needs_more_help,
    looks_like_phone_chunk,
)
from speech_filters import parse_all_leaked_tool_calls, sanitize_for_speech

logger = logging.getLogger("monitor")

MONITOR_TOPIC = "monitor"

COLLECTED_DATA_FIELDS = (
    "name",
    "reason",
    "preferred_date",
    "preferred_time",
    "phone",
    "booking_status",
)


class MonitorPublisher:
    def __init__(self, room: rtc.Room, session: AgentSession) -> None:
        self._room = room
        self._session = session
        self._current_intent = "general"
        self._current_action = "idle"
        self._takeover_active = False
        self.transcript_lines: list[str] = []
        self._collected_data: dict[str, str | None] = {
            field: None for field in COLLECTED_DATA_FIELDS
        }
        self._pending_field: str | None = None
        self._booking_saved = False
        self._availability_replied_for: set[str] = set()
        self._phone_digit_buffer: str = ""
        self._awaiting_confirmation = False
        self._awaiting_call_end = False
        self._call_end_handled = False
        self._transfer_handler: Callable[[str], Awaitable[None]] | None = None
        self._transfer_cue_handled = False

    _CHECKING_AVAILABILITY = re.compile(
        r"\b("
        r"let me check|"
        r"i['']?ll(?: just)? check|"
        r"checking (?:what )?(?:time )?slots|"
        r"check (?:our )?schedule|"
        r"check availability|"
        r"available on that day|"
        r"time slots are available"
        r")\b",
        re.IGNORECASE,
    )
    _AWAITING_CONFIRMATION = re.compile(
        r"\b(is that correct|is that all set|all set\?|confirm that|shall i book|"
        r"just to confirm|does that sound)\b",
        re.IGNORECASE,
    )
    _BOOKED_CLAIM = re.compile(
        r"\b(i['']ve booked|appointment (?:is )?booked|you['']re all set|we['']ll see you then)\b",
        re.IGNORECASE,
    )
    _CALL_END_PROMPT = re.compile(
        r"\b(anything else|all set to end|end the call|goodbye for now|"
        r"need anything else|help you with anything else|are you all set)\b",
        re.IGNORECASE,
    )
    _TRANSFER_COMMITMENT = re.compile(
        r"\b(i['']ll transfer|let me transfer|connect you with|transfer (?:this )?call|"
        r"transfer you to|put you through to|getting someone for you)\b",
        re.IGNORECASE,
    )

    def _accumulate_phone(self, raw: str) -> str | None:
        if self._pending_field != "phone" and not self._phone_digit_buffer:
            if not looks_like_phone_chunk(raw):
                return None
        chunk = extract_phone_chunk(raw)
        if chunk:
            self._phone_digit_buffer += chunk
        if len(self._phone_digit_buffer) >= 7:
            phone = self._phone_digit_buffer
            self._phone_digit_buffer = ""
            return phone
        return None

    def set_transfer_handler(
        self,
        handler: Callable[[str], Awaitable[None]],
    ) -> None:
        self._transfer_handler = handler

    def collected_data_snapshot(self) -> dict[str, str | None]:
        return dict(self._collected_data)

    def is_booking_confirmed(self) -> bool:
        return self._booking_saved or self._collected_data.get("booking_status") == "confirmed"

    def booking_confirmation_message(self) -> str:
        name = self._collected_data.get("name") or "the caller"
        reason = self._collected_data.get("reason") or "their visit"
        phone = self._collected_data.get("phone") or ""
        slot = self._slot_datetime_from_collected()
        when = format_slot_human(slot) if slot else "the requested time"
        return (
            f"Confirmed. Appointment booked for {name} on {when} "
            f"for {reason}. Contact number {phone}. "
            "Tell the caller their appointment is confirmed. "
            "Do NOT say the slot is unavailable or offer other times. "
            "Then ask if they need anything else or if they are all set to end the call."
        )

    async def end_call(self) -> None:
        if self._call_end_handled or self._takeover_active:
            return
        self._call_end_handled = True
        self._awaiting_call_end = False
        self._current_action = "idle"
        await self.publish_state()
        logger.info("caller confirmed call end — shutting down session")
        farewell = self._session.say(
            "Thank you for calling Swades Health. We look forward to seeing you. Goodbye!",
            allow_interruptions=False,
        )
        await farewell.wait_for_playout()
        self._session.shutdown()

    async def _maybe_execute_transfer(self, raw: str, text: str) -> None:
        if self._transfer_cue_handled or not self._transfer_handler:
            return

        reason = "caller request"
        reason_match = re.search(
            r'\{\s*"reason"\s*:\s*"(?P<reason>[^"]+)"\s*\}',
            raw,
            re.IGNORECASE,
        )
        if reason_match:
            reason = reason_match.group("reason")
            self._transfer_cue_handled = True
        elif self._TRANSFER_COMMITMENT.search(text or raw):
            self._transfer_cue_handled = True
        else:
            return

        self._current_intent = "escalation"
        self._current_action = "transferring"
        await self.publish_state()
        logger.info("auto transfer triggered: %s", reason)
        await self._transfer_handler(reason)

    async def _maybe_check_availability_and_reply(
        self,
        preferred_date: str | None = None,
    ) -> None:
        if self.is_booking_confirmed():
            return
        date_str = preferred_date or self._collected_data.get("preferred_date")
        if not date_str or date_str in self._availability_replied_for:
            return

        try:
            parsed = parse_preferred_date(date_str)
            date_key = parsed.isoformat()
        except ValueError:
            date_key = date_str.strip()

        if date_key in self._availability_replied_for:
            return

        self._availability_replied_for.add(date_key)
        self._current_intent = "booking"
        self._current_action = "checking_availability"
        await self.update_collected_data(
            preferred_date=date_key,
            booking_status="checking",
        )
        await self.publish_state()

        result = availability_message(date_key)
        preferred_time = self._collected_data.get("preferred_time")
        time_hint = (
            f" The caller requested around {preferred_time}. "
            "Confirm that time if available, or offer the closest open slot."
            if preferred_time
            else ""
        )
        phone_hint = (
            " Then ask for their contact phone number to complete the booking."
            if not self._collected_data.get("phone")
            else " Ask them to confirm the booking details."
        )

        logger.info("auto availability check for %s: %s", date_key, result[:120])
        self._session.generate_reply(
            instructions=(
                f"Tell the caller: {result}{time_hint}{phone_hint} "
                "Speak naturally in 1-2 sentences. Do NOT mention tools, JSON, or function names."
            )
        )

    def _slot_datetime_from_collected(self) -> str | None:
        preferred_date = self._collected_data.get("preferred_date")
        if not preferred_date:
            return None
        preferred_time = self._collected_data.get("preferred_time") or "09:00"
        if len(preferred_time) == 4 and ":" in preferred_time:
            preferred_time = f"0{preferred_time}"
        # 12:30 PM stored as 12:30 — valid 24h; 01:00–11:59 AM/PM already normalized
        return f"{preferred_date} {preferred_time}"

    async def _persist_booking(
        self,
        name: str,
        reason: str,
        slot_datetime: str,
        phone: str,
    ) -> bool:
        if self._booking_saved or self._collected_data.get("booking_status") == "confirmed":
            return True

        slot = slot_datetime.strip()
        candidates = [slot]
        date_part = slot.split()[0] if slot else ""
        if date_part:
            try:
                for open_slot in get_available_slots(date_part):
                    if open_slot not in candidates:
                        candidates.append(open_slot)
            except ValueError:
                pass

        for candidate in candidates:
            try:
                create_booking(name, reason, candidate, phone)
                self._booking_saved = True
                booked_date, _, booked_time = candidate.partition(" ")
                await self.update_collected_data(
                    name=name,
                    reason=reason,
                    phone=phone,
                    preferred_date=booked_date or None,
                    preferred_time=booked_time or None,
                    booking_status="confirmed",
                )
                self._current_intent = "booking"
                self._current_action = "idle"
                self._awaiting_call_end = True
                logger.info("appointment saved: %s at %s", name, candidate)
                return True
            except ValueError as exc:
                logger.warning("booking attempt failed for %s: %s", candidate, exc)

        return False

    async def _maybe_auto_book(self, *, force: bool = False) -> None:
        if self._booking_saved:
            return
        name = self._collected_data.get("name")
        reason = self._collected_data.get("reason")
        phone = self._collected_data.get("phone")
        if not phone and len(self._phone_digit_buffer) >= 7:
            phone = self._phone_digit_buffer
            self._phone_digit_buffer = ""
            await self.update_collected_data(phone=phone)
        slot_datetime = self._slot_datetime_from_collected()
        if not all([name, reason, phone, slot_datetime]):
            if force:
                logger.warning(
                    "auto-book skipped — missing fields name=%s reason=%s phone=%s slot=%s",
                    bool(name),
                    bool(reason),
                    bool(phone),
                    slot_datetime,
                )
            return
        await self._persist_booking(name, reason, slot_datetime, phone)

    async def _finalize_on_confirm(self) -> None:
        self._awaiting_confirmation = False
        await self._maybe_auto_book(force=True)

    async def try_book(
        self,
        name: str,
        reason: str,
        slot_datetime: str,
        phone: str,
    ) -> str:
        """Book or return a confirmation if the appointment is already saved."""
        if self.is_booking_confirmed():
            return self.booking_confirmation_message()

        existing = find_booking_by_phone_and_slot(phone, slot_datetime)
        if existing is not None:
            self._booking_saved = True
            booked_date, _, booked_time = slot_datetime.strip().partition(" ")
            await self.update_collected_data(
                name=existing.name,
                reason=existing.reason,
                phone=existing.phone,
                preferred_date=booked_date or None,
                preferred_time=booked_time or None,
                booking_status="confirmed",
            )
            self._awaiting_call_end = True
            return self.booking_confirmation_message()

        saved = await self._persist_booking(name, reason, slot_datetime, phone)
        if saved:
            return self.booking_confirmation_message()
        return (
            f"Booking failed for {slot_datetime}. Offer other available times "
            "via check_availability."
        )

    async def availability_for_agent(self, preferred_date: str) -> str:
        if self.is_booking_confirmed():
            return self.booking_confirmation_message()
        return availability_message(preferred_date)

    async def publish(self, payload: dict[str, Any]) -> None:
        if not self._room.isconnected():
            return
        try:
            local = self._room.local_participant
            await local.publish_data(
                json.dumps(payload).encode("utf-8"),
                reliable=True,
                topic=MONITOR_TOPIC,
            )
        except Exception:
            logger.debug("skip monitor publish (room not ready)", exc_info=True)

    async def publish_call_status(self, status: str) -> None:
        await self.publish({"type": "call_status", "status": status})

    async def publish_state(self) -> None:
        state = getattr(self._session, "agent_state", "unknown")
        await self.publish(
            {
                "type": "state",
                "status": str(state),
                "intent": self._current_intent,
                "action": self._current_action,
                "takeover": self._takeover_active,
            }
        )

    async def publish_collected_data(self) -> None:
        await self.publish({"type": "collected_data", "data": dict(self._collected_data)})

    async def update_collected_data(self, **fields: str | None) -> None:
        changed = False
        for key, value in fields.items():
            if key not in self._collected_data or value is None:
                continue
            cleaned = str(value).strip()
            if not cleaned:
                continue
            if (
                key == "booking_status"
                and self._collected_data.get("booking_status") == "confirmed"
                and cleaned != "confirmed"
            ):
                continue
            if self._collected_data[key] != cleaned:
                self._collected_data[key] = cleaned
                changed = True
        if changed:
            await self.publish_collected_data()
            await self._maybe_auto_book()

    @staticmethod
    def _parse_tool_args(call) -> dict[str, Any]:
        raw = getattr(call, "arguments", None) or getattr(call, "args", None)
        if raw is None:
            return {}
        if isinstance(raw, dict):
            return raw
        if isinstance(raw, str):
            try:
                parsed = json.loads(raw)
                return parsed if isinstance(parsed, dict) else {}
            except json.JSONDecodeError:
                return {}
        return {}

    async def _apply_tool_collected_data(self, name: str, args: dict[str, Any]) -> None:
        if name == "record_caller_info":
            await self.update_collected_data(
                name=args.get("name"),
                reason=args.get("reason"),
                preferred_date=args.get("preferred_date"),
                preferred_time=args.get("preferred_time"),
                phone=args.get("phone"),
                booking_status="collecting",
            )
        elif name == "check_availability":
            preferred_date = args.get("preferred_date") or self._collected_data.get(
                "preferred_date"
            )
            if preferred_date:
                await self._maybe_check_availability_and_reply(str(preferred_date))
            else:
                await self.update_collected_data(booking_status="checking")
        elif name == "transfer_to_human":
            reason = str(args.get("reason") or "caller request")
            if self._transfer_handler:
                await self._maybe_execute_transfer(
                    json.dumps({"reason": reason}),
                    "",
                )
        elif name == "book_appointment":
            slot = str(args.get("slot_datetime", "")).strip()
            date_part, _, time_part = slot.partition(" ")
            name_val = str(args.get("name") or self._collected_data.get("name") or "").strip()
            reason_val = str(args.get("reason") or self._collected_data.get("reason") or "").strip()
            phone_val = str(args.get("phone") or self._collected_data.get("phone") or "").strip()
            slot_datetime = slot or self._slot_datetime_from_collected()
            if name_val and reason_val and phone_val and slot_datetime:
                await self._persist_booking(name_val, reason_val, slot_datetime, phone_val)
            else:
                await self.update_collected_data(
                    name=name_val or None,
                    reason=reason_val or None,
                    preferred_date=date_part or None,
                    preferred_time=time_part or None,
                    phone=phone_val or None,
                    booking_status="collecting",
                )

    async def _apply_leaked_tools(self, text: str) -> None:
        for name, args in parse_all_leaked_tool_calls(text):
            await self._apply_tool_collected_data(name, args)

    async def _apply_inferred_fields(self, fields: dict[str, str]) -> None:
        if not fields:
            return
        await self.update_collected_data(**fields)
        await self._maybe_auto_book()
        if fields.get("preferred_date"):
            await self._maybe_check_availability_and_reply(fields["preferred_date"])

    async def _on_agent_availability_cue(self, text: str) -> None:
        preferred_date, preferred_time = _extract_date_time(text)
        inferred: dict[str, str] = {}
        if preferred_date and not self._collected_data.get("preferred_date"):
            inferred["preferred_date"] = preferred_date
        if preferred_time and not self._collected_data.get("preferred_time"):
            inferred["preferred_time"] = preferred_time
        if inferred:
            inferred["booking_status"] = "collecting"
            await self._apply_inferred_fields(inferred)
        if self._CHECKING_AVAILABILITY.search(text):
            await self._maybe_check_availability_and_reply()

    def attach(self) -> None:
        @self._session.on("conversation_item_added")
        def _on_transcript(event) -> None:
            item = event.item
            raw = getattr(item, "text_content", None) or ""
            role = getattr(item, "role", "unknown")

            asyncio.create_task(self._apply_leaked_tools(raw))

            text = sanitize_for_speech(raw)
            if role == "assistant" and text:
                pending = detect_pending_field(text)
                if pending:
                    self._pending_field = pending
                asyncio.create_task(self._on_agent_availability_cue(text))
                asyncio.create_task(self._maybe_execute_transfer(raw, text))
                if self._AWAITING_CONFIRMATION.search(text):
                    self._awaiting_confirmation = True
                if self._BOOKED_CLAIM.search(text):
                    asyncio.create_task(self._maybe_auto_book(force=True))
                if self.is_booking_confirmed() and self._CALL_END_PROMPT.search(text):
                    self._awaiting_call_end = True
            elif role == "user" and raw.strip():
                if self.is_booking_confirmed() and self._awaiting_call_end:
                    if is_user_call_end_confirmation(raw):
                        asyncio.create_task(self.end_call())
                    elif is_user_needs_more_help(raw):
                        self._awaiting_call_end = False
                elif is_user_confirmation(raw) and self._awaiting_confirmation:
                    asyncio.create_task(self._finalize_on_confirm())
                phone = self._accumulate_phone(raw)
                inferred = infer_fields_from_user_reply(self._pending_field, raw)
                if phone:
                    inferred["phone"] = phone
                if inferred:
                    if self._pending_field != "phone" or phone:
                        self._pending_field = None
                    asyncio.create_task(self._apply_inferred_fields(inferred))
                elif phone:
                    asyncio.create_task(
                        self._apply_inferred_fields(
                            {"phone": phone, "booking_status": "collecting"}
                        )
                    )

            if not text:
                return
            self.transcript_lines.append(f"{role}: {text}")

            asyncio.create_task(
                self.publish(
                    {
                        "type": "transcript",
                        "role": role,
                        "text": text,
                    }
                )
            )

        @self._session.on("agent_state_changed")
        def _on_agent_state(_event) -> None:
            asyncio.create_task(self.publish_state())

        @self._session.on("function_tools_executed")
        def _on_tools(event) -> None:
            async def handle() -> None:
                for call in event.function_calls:
                    name = call.name
                    if name == "check_availability":
                        self._current_intent = "booking"
                        self._current_action = "checking_availability"
                    elif name == "book_appointment":
                        self._current_intent = "booking"
                        self._current_action = "booking"
                    elif name == "end_call":
                        self._current_action = "idle"
                        await self.end_call()
                        continue
                    elif name == "transfer_to_human":
                        self._current_intent = "escalation"
                        self._current_action = "transferring"
                        await self.publish_state()
                        continue
                    await self._apply_tool_collected_data(
                        name, self._parse_tool_args(call)
                    )
                await self.publish_state()

            asyncio.create_task(handle())

    def set_intent(self, intent: str) -> None:
        self._current_intent = intent

    def set_action(self, action: str) -> None:
        self._current_action = action

    def set_takeover(self, active: bool) -> None:
        self._takeover_active = active
