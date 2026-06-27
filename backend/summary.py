"""Post-call summary generation."""

from __future__ import annotations

import logging
import os
from pathlib import Path

from dotenv import load_dotenv
from groq import Groq

from booking import format_slot_human, save_call_summary
from voice_config import is_malayalam

logger = logging.getLogger("summary")

GROQ_SUMMARY_MODEL = os.getenv("GROQ_SUMMARY_MODEL", "llama-3.1-8b-instant")


def _ensure_env() -> None:
    root = Path(__file__).resolve().parent.parent
    for path in (root / ".env", Path(__file__).resolve().parent / ".env"):
        if path.exists():
            load_dotenv(path, override=True)


async def generate_and_save_summary(
    room_name: str,
    transcript_lines: list[str],
    monitor_publish=None,
) -> str:
    transcript = "\n".join(transcript_lines) or "No conversation recorded."
    # Keep summary requests small to preserve Groq free-tier quota
    if len(transcript) > 6000:
        transcript = transcript[-6000:]
    summary = transcript[:500]

    _ensure_env()
    api_key = os.getenv("GROQ_API_KEY")
    if api_key:
        try:
            client = Groq(api_key=api_key)
            response = client.chat.completions.create(
                model=GROQ_SUMMARY_MODEL,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "Summarize this phone call in 3-5 bullet points. "
                            "Include caller intent, booking details if any, "
                            "and whether a transfer or takeover occurred."
                            + (" Write the summary in Malayalam." if is_malayalam() else "")
                        ),
                    },
                    {"role": "user", "content": transcript},
                ],
                max_tokens=300,
            )
            summary = response.choices[0].message.content or summary
        except Exception:
            logger.exception("failed to generate LLM summary")

    save_call_summary(room_name, summary)
    if monitor_publish:
        await monitor_publish({"type": "summary", "text": summary})

    return summary


def _format_collected_context(collected_data: dict[str, str | None]) -> str:
    lines: list[str] = []
    name = collected_data.get("name")
    reason = collected_data.get("reason")
    phone = collected_data.get("phone")
    booking_status = collected_data.get("booking_status")
    preferred_date = collected_data.get("preferred_date")
    preferred_time = collected_data.get("preferred_time")

    if name:
        lines.append(f"Caller name: {name}")
    if reason:
        lines.append(f"Reason for call: {reason}")
    if preferred_date:
        slot = f"{preferred_date} {preferred_time or ''}".strip()
        try:
            lines.append(f"Requested appointment: {format_slot_human(slot)}")
        except ValueError:
            lines.append(f"Requested date/time: {slot}")
    if phone:
        lines.append(f"Contact phone: {phone}")
    if booking_status:
        lines.append(f"Booking status: {booking_status}")

    return "\n".join(lines)


async def generate_transfer_brief(
    transcript_lines: list[str],
    collected_data: dict[str, str | None],
    transfer_reason: str,
) -> str:
    """Short supervisor-facing summary before warm transfer."""
    transcript = "\n".join(transcript_lines) or "No conversation recorded."
    if len(transcript) > 4000:
        transcript = transcript[-4000:]

    structured = _format_collected_context(collected_data)
    fallback = (
        f"Transfer reason: {transfer_reason}\n"
        f"{structured}\n\n"
        f"Recent conversation:\n{transcript[-1200:]}"
    )

    _ensure_env()
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        return fallback

    try:
        client = Groq(api_key=api_key)
        response = client.chat.completions.create(
            model=GROQ_SUMMARY_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Write a concise warm-transfer brief for a human agent in 3-5 sentences. "
                        "Include who the caller is, why they called, any booking details collected, "
                        "and why a human is needed now. Be factual and speakable aloud."
                        + (" Write in Malayalam." if is_malayalam() else "")
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"Transfer reason: {transfer_reason}\n\n"
                        f"Collected data:\n{structured or 'None'}\n\n"
                        f"Transcript:\n{transcript}"
                    ),
                },
            ],
            max_tokens=220,
        )
        return response.choices[0].message.content or fallback
    except Exception:
        logger.exception("failed to generate transfer brief")
        return fallback
