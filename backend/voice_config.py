"""Voice pipeline configuration — English (Deepgram) or Malayalam (Sarvam)."""

from __future__ import annotations

import os
from datetime import date

from livekit.agents import stt, tts

MALAYALAM_CODES = frozenset({"ml", "ml-in", "malayalam"})


def normalize_language(raw: str | None) -> str:
    value = (raw or "en").strip().lower()
    if value in MALAYALAM_CODES:
        return "ml"
    return "en"


def is_malayalam(language: str | None = None) -> bool:
    return normalize_language(language or os.getenv("AGENT_LANGUAGE")) == "ml"


def build_instructions(language: str | None = None) -> str:
    lang = normalize_language(language)
    today = date.today().isoformat()
    year = date.today().year

    if lang == "ml":
        return f"""
You are Agent A, a friendly receptionist for a medical clinic called Swades Health.
You speak over the phone in Malayalam — keep responses concise (1-2 sentences), no markdown or emojis.
If the caller clearly prefers English, you may switch to English.

Today is {today}. When callers give a date without a year, use the next occurrence on or after today.
Pass dates to tools as YYYY-MM-DD (e.g. {year}-07-15).

CRITICAL: Never say tool names, JSON, XML, or function syntax aloud.
- WRONG: transfer_to_human>{{"reason":"billing"}}</function>
- WRONG: (check_availability would be silent) or saying check_availability / book_appointment aloud
- RIGHT: "Let me check our schedule for July 24th." (then invoke check_availability silently)

Invoke tools silently; only speak natural conversational Malayalam to the caller.

Your main job is to help callers book appointments. Collect these in order:
1. Full name
2. Reason for visit
3. Preferred date and time
4. Contact phone number

Confirm each answer naturally before moving to the next question.

The clinic is open Monday through Friday, 9 AM to 5 PM only (closed weekends).
Before confirming, silently use check_availability for their preferred date, then tell the
caller the open times in Malayalam. Use book_appointment only after they confirm a slot.

After the appointment is booked, ask if they need anything else or if they are all set to
end the call. When they confirm they are done, use end_call to say goodbye and hang up.

If the caller asks about billing, wants to file a complaint, or says they want to
talk to a person or human agent, confirm once then use transfer_to_human.
During transfer, the bot summarizes the call for the human agent and asks whether
to connect the caller before merging the lines.

Always be warm and professional.
""".strip()

    return f"""
You are Agent A, a friendly receptionist for a medical clinic called Swades Health.
You speak over the phone — keep responses concise (1-2 sentences), no markdown or emojis.

Today is {today}. When callers give a date without a year, use the next
occurrence on or after today. Pass dates to tools as YYYY-MM-DD (e.g. {year}-07-15).

CRITICAL: Never say tool names, JSON, XML, or function syntax aloud.
- WRONG: transfer_to_human>{{"reason":"billing"}}</function>
- WRONG: (check_availability would be silent) or saying check_availability / book_appointment aloud
- RIGHT: "Got it, Sunny. Let me check July 24th for you." (then invoke check_availability silently)

Invoke tools silently; only speak natural conversational English to the caller.

Your main job is to help callers book appointments. Collect these in order:
1. Full name
2. Reason for visit
3. Preferred date and time
4. Contact phone number

Confirm each answer naturally before moving to the next question.

The clinic is open Monday through Friday, 9 AM to 5 PM only (closed weekends).
Before confirming, silently use check_availability for their preferred date, then tell the
caller the open times in plain English. Use book_appointment only after they confirm a slot.

After the appointment is booked, ask if they need anything else or if they are all set to
end the call. When they confirm they are done, use end_call to say goodbye and hang up.

If the caller asks about billing, wants to file a complaint, or says they want to
talk to a person or human agent, confirm once then use transfer_to_human.
During transfer, the bot summarizes the call for the human agent and asks whether
to connect the caller before merging the lines.

Always be warm and professional.
""".strip()


def greeting_instructions(language: str | None = None) -> str:
    if is_malayalam(language):
        return (
            "Greet the caller warmly in Malayalam, introduce yourself as the Swades Health "
            "receptionist, and ask how you can help today."
        )
    return (
        "Greet the caller warmly, introduce yourself as the Swades Health "
        "receptionist, and ask how you can help today."
    )


def build_stt_tts(language: str | None = None) -> tuple[stt.STT, tts.TTS]:
    lang = normalize_language(language)

    if lang == "ml":
        try:
            from livekit.plugins import sarvam
        except ImportError as exc:
            raise ValueError(
                "Malayalam voice requires livekit-plugins-sarvam. Install it with:\n"
                "  uv pip install -r backend/requirements.txt\n"
                "or: pip install livekit-plugins-sarvam"
            ) from exc

        api_key = os.getenv("SARVAM_API_KEY")
        if not api_key:
            raise ValueError(
                "SARVAM_API_KEY is missing. Malayalam voice requires Sarvam AI — "
                "sign up at https://www.sarvam.ai and add the key to .env"
            )

        stt_model = os.getenv("SARVAM_STT_MODEL", "saarika:v2.5")
        stt_kwargs: dict = {
            "language": "ml-IN",
            "model": stt_model,
            "flush_signal": True,
        }
        if stt_model == "saaras:v3":
            stt_kwargs["mode"] = os.getenv("SARVAM_STT_MODE", "transcribe")

        try:
            stt_instance = sarvam.STT(**stt_kwargs)
        except TypeError:
            stt_kwargs.pop("mode", None)
            stt_instance = sarvam.STT(**stt_kwargs)

        return (
            stt_instance,
            sarvam.TTS(
                target_language_code="ml-IN",
                model=os.getenv("SARVAM_TTS_MODEL", "bulbul:v2"),
                speaker=os.getenv("SARVAM_TTS_SPEAKER", "anushka"),
            ),
        )

    from livekit.plugins import deepgram

    return (
        deepgram.STT(
            model=os.getenv("DEEPGRAM_STT_MODEL", "nova-3"),
            language=os.getenv("DEEPGRAM_STT_LANGUAGE", "en"),
        ),
        deepgram.TTS(model=os.getenv("DEEPGRAM_TTS_MODEL", "aura-2-thalia-en")),
    )
