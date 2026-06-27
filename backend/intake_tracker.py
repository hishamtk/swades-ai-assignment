"""Infer booking fields from conversation when tools are not invoked properly."""

from __future__ import annotations

import re
from datetime import date

from booking import parse_preferred_date

_NAME_PROMPT = re.compile(
    r"\b(full name|your name|tell me your name|what(?:'s| is) your name|give me your name)\b",
    re.IGNORECASE,
)
_REASON_PROMPT = re.compile(
    r"\b(reason for (?:your )?visit|why are you (?:coming|visiting)|what brings you in)\b",
    re.IGNORECASE,
)
_PHONE_PROMPT = re.compile(
    r"\b(phone number|contact number|provide your phone|your phone)\b",
    re.IGNORECASE,
)
_DATE_PROMPT = re.compile(
    r"\b(preferred date|what date|when would you like|date and time|appointment slot|available appointment)\b",
    re.IGNORECASE,
)
_WORD_ONES = {
    "zero": "0", "oh": "0", "o": "0",
    "one": "1", "two": "2", "three": "3", "four": "4", "five": "5",
    "six": "6", "seven": "7", "eight": "8", "nine": "9",
}
_ORDINAL_WORDS = {
    "first": "1", "second": "2", "third": "3", "fourth": "4", "fifth": "5",
    "sixth": "6", "seventh": "7", "eighth": "8", "ninth": "9", "tenth": "10",
    "eleventh": "11", "twelfth": "12", "thirteenth": "13", "fourteenth": "14",
    "fifteenth": "15", "sixteenth": "16", "seventeenth": "17", "eighteenth": "18",
    "nineteenth": "19", "twentieth": "20", "twenty-first": "21", "twenty-second": "22",
    "twenty-third": "23", "twenty-fourth": "24", "twenty-fifth": "25",
    "twenty-sixth": "26", "twenty-seventh": "27", "twenty-eighth": "28",
    "twenty-ninth": "29", "thirtieth": "30", "thirty-first": "31",
}
_HOUR_WORDS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
    "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12,
}
_MINUTE_WORDS = {
    "five": 5, "ten": 10, "fifteen": 15, "twenty": 20, "twenty-five": 25,
    "thirty": 30, "forty": 40, "forty-five": 45, "fifty": 50,
}
# Spoken day-of-month (e.g. "July twenty" → 20); ordinals like "eleventh" live in _ORDINAL_WORDS.
_DAY_WORDS = {
    **_ORDINAL_WORDS,
    "one": "1", "two": "2", "three": "3", "four": "4", "five": "5",
    "six": "6", "seven": "7", "eight": "8", "nine": "9", "ten": "10",
    "eleven": "11", "twelve": "12", "thirteen": "13", "fourteen": "14",
    "fifteen": "15", "sixteen": "16", "seventeen": "17", "eighteen": "18",
    "nineteen": "19", "twenty": "20", "twenty-one": "21", "twenty-two": "22",
    "twenty-three": "23", "twenty-four": "24", "twenty-five": "25",
    "twenty-six": "26", "twenty-seven": "27", "twenty-eight": "28",
    "twenty-nine": "29", "thirty": "30", "thirty-one": "31",
}
_MONTH_NAMES = (
    r"january|february|march|april|may|june|july|august|september|october|"
    r"november|december|jan|feb|mar|apr|jun|jul|aug|sep|sept|oct|nov|dec"
)
_TIME_PROMPT = re.compile(
    r"\b(which time|what time|time do you prefer|pick a time|choose a time)\b",
    re.IGNORECASE,
)
_NAME_WITH_REASON = re.compile(
    r"^(?:okay,?\s*)?(?P<name>[A-Za-z]+)\s+with\s+(?P<reason>.+)$",
    re.IGNORECASE,
)


def _normalize_spoken(text: str) -> str:
    normalized = text.lower()
    for word, digit in sorted(_ORDINAL_WORDS.items(), key=lambda item: -len(item[0])):
        normalized = re.sub(rf"\b{re.escape(word)}\b", digit, normalized)
    return normalized


def detect_pending_field(agent_text: str) -> str | None:
    text = agent_text.lower()
    if _NAME_PROMPT.search(text):
        return "name"
    if _REASON_PROMPT.search(text):
        return "reason"
    if _PHONE_PROMPT.search(text):
        return "phone"
    if _DATE_PROMPT.search(text):
        return "preferred_date"
    if _TIME_PROMPT.search(text):
        return "preferred_time"
    return None


def _clean_name(raw: str) -> str | None:
    value = raw.strip(" .,!?:;\"'")
    if not value or len(value) > 80:
        return None
    words = value.split()
    if len(words) > 5:
        return None
    return " ".join(word.capitalize() for word in words)


def _clean_reason(raw: str) -> str | None:
    value = raw.strip(" .,!?:;\"'")
    if not value or len(value) > 200:
        return None
    return value[0].upper() + value[1:] if value else None


def _spoken_digits(raw: str) -> str:
    tokens = re.findall(r"\d+|[a-zA-Z]+", raw.lower())
    digits: list[str] = []
    for token in tokens:
        if token.isdigit():
            digits.append(token)
        elif token in _WORD_ONES:
            digits.append(_WORD_ONES[token])
    return "".join(digits)


def _clean_phone(raw: str) -> str | None:
    digits = re.sub(r"\D", "", raw)
    if len(digits) < 7:
        digits = _spoken_digits(raw)
    if len(digits) < 7:
        return None
    return digits


def _day_token_to_int(token: str) -> int | None:
    token = token.lower().strip()
    if token.isdigit():
        day = int(token)
        return day if 1 <= day <= 31 else None
    mapped = _DAY_WORDS.get(token)
    if mapped:
        return int(mapped)
    return None


def _parse_spoken_time(normalized: str) -> tuple[str | None, str]:
    """Return (HH:MM or None, text with the time portion removed)."""
    time_match = re.search(
        r"\b(\d{1,2}|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve)"
        r"(?:\s+(thirty|fifteen|twenty|twenty-five|ten|five|forty|forty-five|fifty|\d{1,2}))?"
        r"(?::(\d{2}))?\s*(am|pm)\b",
        normalized,
    )
    if not time_match:
        return None, normalized

    hour_token = time_match.group(1)
    hour = int(hour_token) if hour_token.isdigit() else _HOUR_WORDS.get(hour_token, 0)
    minute_token = time_match.group(2)
    if minute_token:
        minute = (
            f"{_MINUTE_WORDS[minute_token]:02d}"
            if minute_token in _MINUTE_WORDS
            else f"{int(minute_token):02d}"
        )
    else:
        minute = time_match.group(3) or "00"
    meridiem = time_match.group(4)
    if meridiem == "pm" and hour < 12:
        hour += 12
    if meridiem == "am" and hour == 12:
        hour = 0
    preferred_time = f"{hour:02d}:{minute}" if hour else None
    remainder = normalized[: time_match.start()] + normalized[time_match.end() :]
    return preferred_time, remainder.strip()


def _parse_date_hint(text: str) -> str | None:
    normalized = _normalize_spoken(text)

    for pattern in (
        r"\b(\d{1,2})(?:st|nd|rd|th)?\s+of\s+([A-Za-z]+)(?:\s+(\d{4}))?\b",
        r"\b([A-Za-z]+)\s+(\d{1,2})(?:st|nd|rd|th)?(?:,?\s+(\d{4}))?\b",
        r"\b(\d{4}-\d{2}-\d{2})\b",
    ):
        match = re.search(pattern, normalized, re.IGNORECASE)
        if not match:
            continue
        try:
            year = None
            if match.lastindex and match.lastindex >= 2 and match.group(2).isalpha():
                day, month, year = match.group(1), match.group(2), match.group(3)
                hint = f"{day} {month.title()}"
            elif match.group(1)[0].isalpha():
                month, day, year = match.group(1), match.group(2), match.group(3)
                hint = (
                    f"{month.title()} {day}, {year}"
                    if year
                    else f"{month.title()} {day}"
                )
            else:
                hint = match.group(1)
            if year and "year" not in hint and match.group(1)[0].isalpha() is False:
                hint = f"{hint} {year}"
            return parse_preferred_date(hint).isoformat()
        except (ValueError, AttributeError, IndexError):
            continue

    day_word = "|".join(
        sorted({re.escape(word) for word in _DAY_WORDS}, key=len, reverse=True)
    )
    spoken_month = re.search(
        rf"\b({_MONTH_NAMES})\s+(?P<day>\d{{1,2}}|{day_word})\b(?:,?\s*(?P<year>\d{{4}}))?",
        normalized,
        re.IGNORECASE,
    )
    if spoken_month:
        month = spoken_month.group(1)
        day_num = _day_token_to_int(spoken_month.group("day"))
        year = spoken_month.group("year")
        if day_num:
            hint = (
                f"{month.title()} {day_num}, {year}"
                if year
                else f"{month.title()} {day_num}"
            )
            try:
                return parse_preferred_date(hint).isoformat()
            except ValueError:
                pass

    return None


def _extract_date_time(raw: str) -> tuple[str | None, str | None]:
    normalized = _normalize_spoken(raw)
    preferred_time, date_text = _parse_spoken_time(normalized)
    preferred_date = _parse_date_hint(date_text or normalized)
    return preferred_date, preferred_time


def infer_fields_from_user_reply(
    pending_field: str | None,
    user_text: str,
) -> dict[str, str]:
    text = user_text.strip()
    if not text:
        return {}

    fields: dict[str, str] = {}

    name_reason = _NAME_WITH_REASON.match(text)
    if name_reason:
        name = _clean_name(name_reason.group("name"))
        reason = _clean_reason(name_reason.group("reason"))
        if name:
            fields["name"] = name
        if reason:
            fields["reason"] = reason

    if pending_field == "name":
        name = _clean_name(text)
        if name:
            fields["name"] = name
    elif pending_field == "reason":
        first = re.split(r"[.!?]\s+", text, maxsplit=1)[0]
        reason = _clean_reason(first)
        if reason:
            fields["reason"] = reason
        preferred_date, preferred_time = _extract_date_time(text)
        if preferred_date:
            fields["preferred_date"] = preferred_date
        if preferred_time:
            fields["preferred_time"] = preferred_time
    elif pending_field == "phone":
        phone = _clean_phone(text)
        if phone:
            fields["phone"] = phone
    elif pending_field == "preferred_date":
        preferred_date, preferred_time = _extract_date_time(text)
        if preferred_date:
            fields["preferred_date"] = preferred_date
        if preferred_time:
            fields["preferred_time"] = preferred_time
    elif pending_field == "preferred_time":
        preferred_date, preferred_time = _extract_date_time(text)
        if preferred_time:
            fields["preferred_time"] = preferred_time
        if preferred_date and "preferred_date" not in fields:
            fields["preferred_date"] = preferred_date

    if any(
        word in text.lower()
        for word in ("headache", "pain", "fever", "cough", "checkup", "back pain")
    ):
        first = re.split(r"[.!?]\s+", text, maxsplit=1)[0]
        reason = _clean_reason(first)
        if reason and "reason" not in fields:
            fields["reason"] = reason

    preferred_date, preferred_time = _extract_date_time(text)
    if preferred_date and "preferred_date" not in fields:
        fields["preferred_date"] = preferred_date
    if preferred_time and "preferred_time" not in fields:
        fields["preferred_time"] = preferred_time

    phone = _clean_phone(text)
    if phone and "phone" not in fields and pending_field == "phone":
        fields["phone"] = phone

    if fields:
        fields["booking_status"] = "collecting"

    return fields


def is_user_confirmation(text: str) -> bool:
    return bool(
        re.match(
            r"^\s*(yes|yeah|yep|yup|correct|that's right|that is correct|"
            r"sounds good|all set|confirmed|okay|ok)\.?\s*$",
            text.strip(),
            re.IGNORECASE,
        )
    )


def is_user_call_end_confirmation(text: str) -> bool:
    normalized = text.strip().lower()
    if not normalized:
        return False
    if is_user_confirmation(text):
        return True
    return bool(
        re.match(
            r"^\s*(no thanks|no thank you|that's all|that is all|nothing else|"
            r"i'm good|i am good|we're good|we are good|goodbye|bye|"
            r"you can hang up|hang up|end the call|all done|that's it)\.?\s*$",
            normalized,
        )
        or re.search(
            r"\b(nothing else|no other questions|that's all i need|all set)\b",
            normalized,
        )
    )


def is_user_needs_more_help(text: str) -> bool:
    normalized = text.strip().lower()
    return bool(
        re.search(
            r"\b(wait|hold on|actually|one more|another question|not yet|"
            r"before you go|i still need|can you also|what about)\b",
            normalized,
        )
    )


def extract_phone_chunk(text: str) -> str:
    """Return digit characters from a spoken or numeric phone fragment."""
    digits = re.sub(r"\D", "", text)
    if digits:
        return digits
    return _spoken_digits(text)


def looks_like_phone_chunk(text: str) -> bool:
    return bool(extract_phone_chunk(text))
