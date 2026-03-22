"""
Search citation extraction helpers.
"""

from __future__ import annotations

from typing import Any

import orjson

CITATION_CARD_TYPE = "citation_card"
TITLE_KEYS = ("title", "name", "label", "displayTitle", "display_name")
SEARCH_RESULT_FIELDS = (
    "citedWebSearchResults",
    "webSearchResults",
    "citedRagResults",
    "ragResults",
    "searchProductResults",
)


def merge_sources(*source_lists: list[dict[str, str]]) -> list[dict[str, str]]:
    """Merge source lists and deduplicate them by URL."""
    merged: list[dict[str, str]] = []
    seen: set[str] = set()

    for items in source_lists:
        for item in items or []:
            url = _normalize_str(item.get("url"))
            if not url or url in seen:
                continue
            seen.add(url)
            source = {"url": url}
            title = _normalize_str(item.get("title"))
            if title:
                source["title"] = title
            description = _normalize_str(item.get("description"))
            if description:
                source["description"] = description
            merged.append(source)

    return merged


def extract_sources_from_model_response(
    model_response: dict[str, Any],
) -> list[dict[str, str]]:
    """Extract cited sources from a Grok modelResponse payload."""
    if not isinstance(model_response, dict):
        return []

    result_lookup = _build_result_lookup(model_response)
    sources: list[dict[str, str]] = []

    for raw_card in model_response.get("cardAttachmentsJson") or []:
        source = _extract_source_from_card(raw_card, result_lookup)
        if source:
            sources.append(source)

    if sources:
        return merge_sources(sources)

    fallback: list[dict[str, str]] = []
    for field in ("citedWebSearchResults", "citedRagResults"):
        for item in model_response.get(field) or []:
            normalized = _normalize_result_item(item)
            if normalized:
                fallback.append(normalized)

    return merge_sources(fallback)


def extract_sources_from_card_attachment(
    card_attachment: dict[str, Any],
) -> list[dict[str, str]]:
    """Extract cited sources from a streaming cardAttachment event."""
    if not isinstance(card_attachment, dict):
        return []
    source = _extract_source_from_card(card_attachment.get("jsonData"))
    if not source:
        return []
    return [source]


def append_sources_markdown(
    text: str,
    sources: list[dict[str, str]],
) -> str:
    """Append a markdown Sources block that GrokSearch can parse."""
    merged = merge_sources(sources)
    if not merged:
        return text

    lines = ["## Sources"]
    for item in merged:
        url = item["url"]
        title = _normalize_title(item.get("title")) or url
        lines.append(f"- [{title}]({url})")

    block = "\n".join(lines)
    if not text or not text.strip():
        return f"{block}\n"
    return f"{text.rstrip()}\n\n{block}\n"


def _build_result_lookup(model_response: dict[str, Any]) -> dict[str, dict[str, str]]:
    lookup: dict[str, dict[str, str]] = {}

    for field in SEARCH_RESULT_FIELDS:
        for item in model_response.get(field) or []:
            normalized = _normalize_result_item(item)
            if not normalized:
                continue
            lookup.setdefault(normalized["url"], normalized)

    return lookup


def _normalize_result_item(item: Any) -> dict[str, str] | None:
    if not isinstance(item, dict):
        return None

    url = _normalize_str(item.get("url") or item.get("link") or item.get("href"))
    if not url.startswith(("http://", "https://")):
        return None

    normalized = {"url": url}
    title = _normalize_title(item.get("title") or item.get("name") or item.get("label"))
    if title:
        normalized["title"] = title
    description = _normalize_str(
        item.get("description") or item.get("snippet") or item.get("content")
    )
    if description:
        normalized["description"] = description
    return normalized


def _extract_source_from_card(
    raw_card: Any,
    result_lookup: dict[str, dict[str, str]] | None = None,
) -> dict[str, str] | None:
    card = _parse_card(raw_card)
    if not isinstance(card, dict):
        return None

    if not _is_citation_card(card):
        return None

    url = _find_card_url(card)
    if not url.startswith(("http://", "https://")):
        return None

    source = {"url": url}
    result_meta = (result_lookup or {}).get(url, {})

    title = _normalize_title(
        result_meta.get("title")
        or _find_card_title(card)
    )
    if title:
        source["title"] = title

    description = _normalize_str(
        result_meta.get("description")
        or _find_card_description(card)
    )
    if description:
        source["description"] = description

    return source


def _parse_card(raw_card: Any) -> dict[str, Any] | None:
    if isinstance(raw_card, dict):
        return raw_card
    if not isinstance(raw_card, str) or not raw_card.strip():
        return None
    try:
        parsed = orjson.loads(raw_card)
    except orjson.JSONDecodeError:
        return None
    if not isinstance(parsed, dict):
        return None
    return parsed


def _is_citation_card(card: dict[str, Any]) -> bool:
    candidates = [
        card.get("cardType"),
        card.get("card_type"),
        card.get("data-type"),
        card.get("dataType"),
        card.get("type"),
    ]
    for value in candidates:
        text = _normalize_str(value).lower()
        if text == CITATION_CARD_TYPE or "citation" in text:
            return True
    return False


def _find_card_url(card: dict[str, Any]) -> str:
    direct = _normalize_str(card.get("url") or card.get("href") or card.get("link"))
    if direct.startswith(("http://", "https://")):
        return direct

    for value in _walk_values(card):
        text = _normalize_str(value)
        if text.startswith(("http://", "https://")):
            return text
    return ""


def _find_card_title(card: dict[str, Any]) -> str:
    for key in TITLE_KEYS:
        title = _normalize_title(card.get(key))
        if title:
            return title

    for key, value in _walk_items(card):
        if key in TITLE_KEYS:
            title = _normalize_title(value)
            if title:
                return title
    return ""


def _find_card_description(card: dict[str, Any]) -> str:
    candidates = (
        card.get("description"),
        card.get("snippet"),
        card.get("content"),
        card.get("summary"),
    )
    for value in candidates:
        text = _normalize_str(value)
        if text:
            return text

    for key, value in _walk_items(card):
        if key in {"description", "snippet", "content", "summary"}:
            text = _normalize_str(value)
            if text:
                return text
    return ""


def _walk_values(value: Any) -> list[Any]:
    values: list[Any] = []
    stack: list[Any] = [value]

    while stack:
        current = stack.pop()
        if isinstance(current, dict):
            stack.extend(current.values())
            continue
        if isinstance(current, list):
            stack.extend(current)
            continue
        values.append(current)

    return values


def _walk_items(value: Any) -> list[tuple[str, Any]]:
    items: list[tuple[str, Any]] = []
    stack: list[Any] = [value]

    while stack:
        current = stack.pop()
        if isinstance(current, dict):
            for key, child in current.items():
                if isinstance(key, str):
                    items.append((key, child))
                stack.append(child)
            continue
        if isinstance(current, list):
            stack.extend(current)

    return items


def _normalize_str(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    return ""


def _normalize_title(value: Any) -> str:
    title = _normalize_str(value)
    if not title:
        return ""
    return " ".join(title.split())


__all__ = [
    "append_sources_markdown",
    "extract_sources_from_card_attachment",
    "extract_sources_from_model_response",
    "merge_sources",
]
