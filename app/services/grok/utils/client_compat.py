"""
Compatibility helpers for known upstream clients.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

_GROKSEARCH_SEARCH_MARKERS = (
    "breadth-first search",
    "citation_card",
    "every sentence must cite sources",
    "search in english first",
)

_GROKSEARCH_FETCH_MARKERS = (
    "# profile: web content fetcher",
    "table of contents",
    "html",
    "markdown",
)

_MARKER_THRESHOLD = 2
_GROKSEARCH_REQUEST_TIMEOUT_SECONDS = 45.0
_GROKSEARCH_STREAM_IDLE_TIMEOUT_SECONDS = 45.0
_GROKSEARCH_MAX_TOKEN_RETRIES = 1
_GROKSEARCH_REVERSE_MAX_RETRY = 0
_GROKSEARCH_PRIORITY_ROLES = ("system", "developer")
_COMPAT_PROMPT_ROLES = ("system", "developer")


@dataclass(frozen=True)
class ClientCompatOptions:
    suppress_think: bool = False
    suppress_media: bool = False
    request_timeout: float | None = None
    stream_idle_timeout: float | None = None
    max_token_retries: int | None = None
    reverse_max_retry: int | None = None
    custom_personality_roles: tuple[str, ...] = ()


def detect_client_compat(messages: list[dict[str, Any]] | None) -> ClientCompatOptions:
    system_text = _collect_system_text(messages or [])
    if not system_text:
        return ClientCompatOptions()
    if _looks_like_groksearch_prompt(system_text):
        return _groksearch_options()
    return ClientCompatOptions()


def _groksearch_options() -> ClientCompatOptions:
    return ClientCompatOptions(
        suppress_think=True,
        suppress_media=True,
        request_timeout=_GROKSEARCH_REQUEST_TIMEOUT_SECONDS,
        stream_idle_timeout=_GROKSEARCH_STREAM_IDLE_TIMEOUT_SECONDS,
        max_token_retries=_GROKSEARCH_MAX_TOKEN_RETRIES,
        reverse_max_retry=_GROKSEARCH_REVERSE_MAX_RETRY,
        custom_personality_roles=_GROKSEARCH_PRIORITY_ROLES,
    )


def _collect_system_text(messages: list[dict[str, Any]]) -> str:
    parts: list[str] = []
    for message in messages:
        if (message.get("role") or "") not in _COMPAT_PROMPT_ROLES:
            continue
        text = _extract_text(message.get("content"))
        if text:
            parts.append(text)
    return "\n".join(parts).lower()


def _extract_text(content: Any) -> str:
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, dict):
        content = [content]
    if not isinstance(content, list):
        return ""
    parts: list[str] = []
    for item in content:
        if not isinstance(item, dict):
            continue
        if item.get("type") != "text":
            continue
        text = item.get("text")
        if isinstance(text, str) and text.strip():
            parts.append(text.strip())
    return "\n".join(parts)


def _looks_like_groksearch_prompt(system_text: str) -> bool:
    return _match_markers(
        system_text, _GROKSEARCH_SEARCH_MARKERS
    ) or _match_markers(system_text, _GROKSEARCH_FETCH_MARKERS)


def _match_markers(system_text: str, markers: tuple[str, ...]) -> bool:
    matched = sum(1 for marker in markers if marker in system_text)
    return matched >= _MARKER_THRESHOLD


__all__ = ["ClientCompatOptions", "detect_client_compat"]
