"""Strip leaked LLM tool syntax so it is never spoken aloud."""

from __future__ import annotations

import json
import re

# Tool names the LLM may leak as spoken text instead of proper function calls.
TOOL_NAMES = (
    "check_availability",
    "book_appointment",
    "end_call",
    "transfer_to_human",
    "record_caller_info",
)
_TOOL_NAME_PATTERN = "|".join(re.escape(name) for name in TOOL_NAMES)

# Spoken patterns like: transfer_to_human>{"reason":"billing"}</function>
_LEAKED_TOOL = re.compile(
    rf"(?P<name>{_TOOL_NAME_PATTERN})"
    r"\s*[>(]?\s*(?P<args>\{.*?\})?\s*(?:</function>)?\)?",
    re.IGNORECASE | re.DOTALL,
)
# tool_name followed by a JSON object without > or (
_TOOL_THEN_JSON = re.compile(
    rf"(?P<name>{_TOOL_NAME_PATTERN})\s+(?P<args>\{{.*?\}})",
    re.IGNORECASE | re.DOTALL,
)
# Bare JSON the LLM speaks instead of invoking a tool, e.g. {"reason":"human agent"}
_BARE_TOOL_JSON = re.compile(
    r'\{\s*"(?:reason|name|phone|slot_datetime|preferred_date|preferred_time)"\s*:\s*"[^"]*"(?:\s*,\s*"(?:reason|name|phone|slot_datetime|preferred_date|preferred_time)"\s*:\s*"[^"]*")*\s*\}',
    re.IGNORECASE,
)
_BARE_REASON_JSON = re.compile(
    r'\{\s*"reason"\s*:\s*"(?P<reason>[^"]+)"\s*\}',
    re.IGNORECASE,
)
# Parentheticals that mention tools, e.g. (check_availability would be silent)
_TOOL_PAREN = re.compile(
    rf"\([^)]*?(?:{_TOOL_NAME_PATTERN})[^)]*?\)",
    re.IGNORECASE,
)
# Bare tool name mentions in running text
_BARE_TOOL_MENTION = re.compile(
    rf"\b(?:{_TOOL_NAME_PATTERN})\b(?:\s+would\s+be\s+silent)?",
    re.IGNORECASE,
)
_XML_TOOL = re.compile(r"<function[^>]*>.*?(?:</function>|$)", re.IGNORECASE | re.DOTALL)
_TOOL_NAME_ONLY = re.compile(
    rf"^\s*({_TOOL_NAME_PATTERN})\b.*$",
    re.IGNORECASE | re.DOTALL,
)


def _parse_leaked_args(raw_args: str | None) -> dict[str, str]:
    if not raw_args:
        return {}
    try:
        parsed = json.loads(raw_args)
        if isinstance(parsed, dict):
            return {str(k): str(v) for k, v in parsed.items()}
    except json.JSONDecodeError:
        pass
    return {}


def parse_leaked_tool_call(text: str) -> tuple[str, dict[str, str]] | None:
    calls = parse_all_leaked_tool_calls(text)
    return calls[0] if calls else None


def parse_all_leaked_tool_calls(text: str) -> list[tuple[str, dict[str, str]]]:
    results: list[tuple[str, dict[str, str]]] = []
    seen: set[tuple[str, str]] = set()

    def add_call(name: str, args: dict[str, str]) -> None:
        if name == "transfer_to_human" and "reason" not in args:
            args["reason"] = "caller request"
        key = (name, json.dumps(args, sort_keys=True))
        if key not in seen:
            seen.add(key)
            results.append((name, args))

    for match in _LEAKED_TOOL.finditer(text):
        add_call(match.group("name").lower(), _parse_leaked_args(match.group("args")))

    for match in _TOOL_THEN_JSON.finditer(text):
        add_call(match.group("name").lower(), _parse_leaked_args(match.group("args")))

    for match in _BARE_REASON_JSON.finditer(text):
        add_call("transfer_to_human", {"reason": match.group("reason")})

    return results


def _strip_tool_artifacts(text: str) -> str:
    cleaned = _XML_TOOL.sub("", text)
    cleaned = _TOOL_PAREN.sub("", cleaned)
    cleaned = _TOOL_THEN_JSON.sub("", cleaned)
    cleaned = _LEAKED_TOOL.sub("", cleaned)
    cleaned = _BARE_TOOL_JSON.sub("", cleaned)
    cleaned = _BARE_TOOL_MENTION.sub("", cleaned)
    cleaned = cleaned.replace("</function>", "").replace("<function", "")
    return cleaned


def sanitize_for_speech(text: str) -> str:
    if not text:
        return ""

    cleaned = _strip_tool_artifacts(text)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()

    if not cleaned or _TOOL_NAME_ONLY.match(cleaned):
        return ""

    return cleaned


def sanitize_stream_chunk(text: str) -> str:
    """Sanitize a streamed LLM/TTS token without stripping boundary spaces."""
    if not text:
        return ""
    if text.isspace():
        return text

    cleaned = _strip_tool_artifacts(text)

    if not cleaned or _TOOL_NAME_ONLY.match(cleaned.strip()):
        return ""

    return cleaned
