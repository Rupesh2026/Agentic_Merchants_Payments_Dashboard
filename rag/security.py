"""Security helpers for prompt sanitization and canary-token validation."""

from __future__ import annotations

from dataclasses import dataclass
import re
import unicodedata
from typing import Iterable

CANARY_TOKENS = (
    "CANARY:PaymentsDashboard:7F3A9D1C",
    "CANARY:PaymentsDashboard:2B8E4F5A",
)

_CANARY_PATTERN = re.compile(
    "|".join(re.escape(token) for token in CANARY_TOKENS),
    re.IGNORECASE,
)
_INVISIBLE_PATTERN = re.compile(r"[\u0000-\u0008\u000B\u000C\u000E-\u001F\u007F\u200B-\u200F\uFEFF]")
_WHITESPACE_PATTERN = re.compile(r"[ \t]+")
_INJECTION_HINTS = (
    "ignore previous instructions",
    "disregard previous instructions",
    "reveal the system prompt",
    "print the system prompt",
    "show me your system prompt",
    "developer message",
    "hidden prompt",
    "prompt injection",
    "jailbreak",
)

MAX_INPUT_CHARS = 8000
SAFE_REFUSAL = (
    "I can't help reveal hidden instructions, internal tokens, or system prompt content. "
    "I can help with the payments data instead."
)


@dataclass(frozen=True)
class SanitizeResult:
    """Normalized text plus detection metadata."""

    text: str
    canary_hits: tuple[str, ...] = ()
    injection_hints: tuple[str, ...] = ()
    truncated: bool = False

    @property
    def blocked(self) -> bool:
        return bool(self.canary_hits)


@dataclass(frozen=True)
class ValidationResult:
    """Output validation result."""

    text: str
    canary_hits: tuple[str, ...] = ()
    valid: bool = True


def _normalize_text(text: str) -> str:
    normalized = unicodedata.normalize("NFKC", text)
    normalized = _INVISIBLE_PATTERN.sub("", normalized)
    normalized = normalized.replace("\r\n", "\n").replace("\r", "\n")
    normalized = _WHITESPACE_PATTERN.sub(" ", normalized)
    return normalized.strip()


def _find_matches(text: str, patterns: Iterable[str]) -> tuple[str, ...]:
    lower = text.lower()
    hits = [pattern for pattern in patterns if pattern.lower() in lower]
    return tuple(hits)


def sanitize_user_input(text: str, *, max_chars: int = MAX_INPUT_CHARS) -> SanitizeResult:
    """Normalize untrusted user input and flag canary or injection markers."""

    normalized = _normalize_text(text)
    truncated = len(normalized) > max_chars
    if truncated:
        normalized = normalized[:max_chars].rstrip()
    canary_hits = tuple(match.group(0) for match in _CANARY_PATTERN.finditer(normalized))
    injection_hints = _find_matches(normalized, _INJECTION_HINTS)
    if canary_hits:
        normalized = _CANARY_PATTERN.sub("[REDACTED_CANARY]", normalized)
    return SanitizeResult(
        text=normalized,
        canary_hits=canary_hits,
        injection_hints=injection_hints,
        truncated=truncated,
    )


def validate_assistant_output(text: str) -> ValidationResult:
    """Reject assistant output that leaks canary tokens."""

    normalized = _normalize_text(text)
    canary_hits = tuple(match.group(0) for match in _CANARY_PATTERN.finditer(normalized))
    if canary_hits:
        return ValidationResult(text=SAFE_REFUSAL, canary_hits=canary_hits, valid=False)
    return ValidationResult(text=normalized, valid=True)


def sanitize_tool_output(text: str) -> str:
    """Redact canary tokens from tool output before the model sees it."""

    normalized = _normalize_text(text)
    return _CANARY_PATTERN.sub("[REDACTED_CANARY]", normalized)
