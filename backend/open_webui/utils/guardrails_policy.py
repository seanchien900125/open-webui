"""Pure rules for chat guardrails: personal data masking and prompt injection detection.

Deterministic and standard-library only, so the rules can be unit tested without a
server. Detection is heuristic: it catches common, well formed data and well known
attack phrasings, and it cannot promise to catch everything.

Findings never carry the matched text, only its kind and position, so callers can log
them without copying the sensitive data into logs.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

# What to do when something is found.
ACTION_OFF = 'off'
ACTION_LOG = 'log'
ACTION_MASK = 'mask'
ACTION_BLOCK = 'block'

PII_ACTIONS = (ACTION_OFF, ACTION_LOG, ACTION_MASK, ACTION_BLOCK)
INJECTION_ACTIONS = (ACTION_OFF, ACTION_LOG, ACTION_BLOCK)

PII_KINDS = ('email', 'phone', 'tw_id', 'credit_card', 'secret', 'ip_address')
DEFAULT_PII_KINDS = ('email', 'phone', 'tw_id', 'credit_card', 'secret')

# Highest priority first. Used to break ties when two detectors match the same span.
_KIND_PRIORITY = {
    kind: rank for rank, kind in enumerate(('secret', 'credit_card', 'tw_id', 'email', 'phone', 'ip_address'))
}


@dataclass(frozen=True)
class GuardrailSettings:
    enabled: bool = False
    pii_action: str = ACTION_MASK
    pii_kinds: tuple[str, ...] = DEFAULT_PII_KINDS
    injection_action: str = ACTION_LOG
    exempt_admins: bool = False

    @property
    def active(self) -> bool:
        return self.enabled and (self.pii_action != ACTION_OFF or self.injection_action != ACTION_OFF)


@dataclass(frozen=True)
class Finding:
    kind: str
    start: int
    end: int


# ---------------------------------------------------------------------------
# Personal data
# ---------------------------------------------------------------------------

_EMAIL = re.compile(r'[A-Za-z0-9._%+\-]+@[A-Za-z0-9\-]+(?:\.[A-Za-z0-9\-]+)*\.[A-Za-z]{2,}')

# Taiwan mobile (0912-345-678, +886 912 345 678), Taiwan landline with a separator
# (02-1234-5678, (02)1234-5678) and E.164 style international numbers.
_PHONE_TW_MOBILE = re.compile(r'(?<![\d+])(?:\+?886[-\s]?|0)9\d{2}[-\s]?\d{3}[-\s]?\d{3}(?!\d)')
_PHONE_TW_LANDLINE = re.compile(r'(?<![\d+])\(?0[2-8]\)?[-\s]?\d{3,4}[-\s]\d{4}(?!\d)')
_PHONE_INTL = re.compile(r'(?<![\d+])\+\d{1,3}[-\s]?\(?\d{1,4}\)?(?:[-\s]?\d{2,4}){2,4}(?!\d)')

_TW_ID = re.compile(r'(?<![A-Za-z0-9])[A-Z][12789]\d{8}(?!\d)')
_TW_ID_LETTER_VALUE = dict(
    zip(
        'ABCDEFGHJKLMNPQRSTUVXYWZIO',
        (10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31, 32, 33, 34, 35),
    )
)

_CARD = re.compile(r'(?<!\d)\d(?:[ -]?\d){12,18}(?!\d)')
_IPV4 = re.compile(r'(?<![\d.])(?:\d{1,3}\.){3}\d{1,3}(?![\d.])')

_SECRET = re.compile(
    '|'.join(
        (
            r'sk-[A-Za-z0-9_\-]{20,}',  # OpenAI style API keys
            r'AKIA[0-9A-Z]{16}',  # AWS access key id
            r'AIza[0-9A-Za-z_\-]{35}',  # Google API key
            r'gh[pousr]_[A-Za-z0-9]{36,}',  # GitHub tokens
            r'xox[baprs]-[A-Za-z0-9\-]{10,}',  # Slack tokens
            r'eyJ[A-Za-z0-9_\-]{10,}\.eyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}',  # JWT
            r'-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?(?:-----END [A-Z ]*PRIVATE KEY-----|\Z)',
        )
    )
)


def luhn_valid(digits: str) -> bool:
    """Whether a digit string passes the Luhn checksum used by payment cards."""
    if not digits.isdigit():
        return False
    total = 0
    for index, char in enumerate(reversed(digits)):
        number = int(char)
        if index % 2 == 1:
            number *= 2
            if number > 9:
                number -= 9
        total += number
    return total % 10 == 0


def tw_id_valid(value: str) -> bool:
    """Whether a Taiwan national ID (or resident certificate number) passes its checksum."""
    if len(value) != 10 or value[0] not in _TW_ID_LETTER_VALUE or not value[1:].isdigit():
        return False
    letter = _TW_ID_LETTER_VALUE[value[0]]
    total = letter // 10 + (letter % 10) * 9
    total += sum(int(digit) * weight for digit, weight in zip(value[1:9], range(8, 0, -1)))
    total += int(value[9])
    return total % 10 == 0


def _ipv4_valid(value: str) -> bool:
    return all(part == str(int(part)) and int(part) <= 255 for part in value.split('.'))


def _card_valid(value: str) -> bool:
    digits = re.sub(r'[ -]', '', value)
    return 13 <= len(digits) <= 19 and luhn_valid(digits)


# kind -> (patterns, optional check that a pattern match must also pass)
_DETECTORS: dict[str, tuple[tuple[re.Pattern, ...], Any]] = {
    'secret': ((_SECRET,), None),
    'credit_card': ((_CARD,), _card_valid),
    'tw_id': ((_TW_ID,), tw_id_valid),
    'email': ((_EMAIL,), None),
    'phone': ((_PHONE_TW_MOBILE, _PHONE_TW_LANDLINE, _PHONE_INTL), None),
    'ip_address': ((_IPV4,), _ipv4_valid),
}


def _iter_matches(text: str, kinds: frozenset[str]) -> Iterable[Finding]:
    for kind, (patterns, check) in _DETECTORS.items():
        if kind not in kinds:
            continue
        for pattern in patterns:
            for match in pattern.finditer(text):
                if check is None or check(match.group()):
                    yield Finding(kind, match.start(), match.end())


def find_pii(text: str, kinds: Iterable[str] = DEFAULT_PII_KINDS) -> list[Finding]:
    """Non-overlapping personal data findings in ``text``, in order of position.

    When detectors overlap, the longer match wins, then the more specific kind
    (a card number is not also reported as a phone number).
    """
    wanted = frozenset(kind for kind in kinds if kind in PII_KINDS)
    if not text or not wanted:
        return []
    candidates = sorted(
        _iter_matches(text, wanted),
        key=lambda finding: (finding.start - finding.end, finding.start, _KIND_PRIORITY[finding.kind]),
    )
    accepted: list[Finding] = []
    for finding in candidates:
        if all(finding.end <= other.start or finding.start >= other.end for other in accepted):
            accepted.append(finding)
    return sorted(accepted, key=lambda finding: finding.start)


def mask_pii(text: str, findings: Iterable[Finding]) -> str:
    """Replace each finding with a ``[KIND]`` placeholder."""
    result = []
    cursor = 0
    for finding in sorted(findings, key=lambda item: item.start):
        if finding.start < cursor:
            continue
        result.append(text[cursor : finding.start])
        result.append(f'[{finding.kind.upper()}]')
        cursor = finding.end
    result.append(text[cursor:])
    return ''.join(result)


# ---------------------------------------------------------------------------
# Prompt injection
# ---------------------------------------------------------------------------

_ZERO_WIDTH = dict.fromkeys(map(ord, '​‌‍⁠﻿­'))

# (category, pattern). Patterns run on normalised text: NFKC, lower case, one space between words.
_INJECTION_PATTERNS: tuple[tuple[str, re.Pattern], ...] = tuple(
    (category, re.compile(pattern))
    for category, pattern in (
        (
            'override_instructions',
            r'(?:ignore|disregard|forget|override|bypass)\s+(?:all\s+|any\s+|every\s+)?(?:of\s+)?(?:the\s+|your\s+|my\s+)?'
            r'(?:previous|prior|above|earlier|preceding|former|initial|system)\s+(?:instructions?|prompts?|rules?|messages?|directions?|guidelines?|context)',
        ),
        (
            'override_instructions',
            r'(?:forget|ignore)\s+(?:everything|all)\s+'
            r'(?:you\s+(?:know|were told|have been told)|above|before|i\s+said)',
        ),
        (
            'override_instructions',
            r'(?:忽略|無視|无视|忽視|忽视|不要理會|不要理会|不要遵守|別管|别管)(?:你)?(?:以上|上面|上述|之前|先前|前面|所有|全部|原本|原来|原來|系統)'
            r'.{0,6}(?:指示|指令|規則|规则|提示|內容|内容|設定|设定|限制|訊息|消息)',
        ),
        (
            'reveal_system_prompt',
            r'(?:reveal|show|print|repeat|output|display|leak|tell me|give me|what is|what are)\s+(?:me\s+)?(?:all\s+)?'
            r'(?:your|the)\s+(?:system|initial|hidden|original|secret)\s+(?:prompt|instructions?|message|rules)',
        ),
        (
            'reveal_system_prompt',
            r'(?:顯示|显示|輸出|输出|告訴我|告诉我|洩漏|泄露|洩露|印出|重複|重复|說出|说出|給我|给我)(?:你的|你|出)?'
            r'(?:完整的?)?(?:系統提示詞?|系统提示词?|系統指令|系统指令|初始指令|初始提示詞?|隱藏指令|隐藏指令|原始指令)',
        ),
        (
            'jailbreak_persona',
            r'(?:do anything now|\bdan\b\s+mode|developer mode|jailbreak(?:ed)?\b|\bdan\s+jailbreak)',
        ),
        (
            'jailbreak_persona',
            r'(?:you\s+are\s+now|from\s+now\s+on\s+you\s+are|act\s+as|pretend\s+(?:to\s+be|you\s+are))\s+(?:an?\s+)?'
            r'(?:unrestricted|unfiltered|uncensored|evil|jailbroken)',
        ),
        (
            'jailbreak_persona',
            r'pretend\s+(?:that\s+)?(?:you\s+have|there\s+are)\s+no\s+(?:restrictions|rules|guidelines|limits|filters)',
        ),
        ('jailbreak_persona', r'(?:越獄|越狱|開發者模式|开发者模式|無限制模式|无限制模式|沒有任何限制|没有任何限制)'),
        (
            'delimiter_spoof',
            r'(?:<\|?\s*(?:im_start|im_end|system|endoftext)\s*\|?>|\[/?inst\]|<<\s*/?sys\s*>>)',
        ),
    )
)


def normalize_for_scan(text: str) -> str:
    """Fold look-alike and invisible characters so simple obfuscation does not hide a phrase."""
    folded = unicodedata.normalize('NFKC', text).translate(_ZERO_WIDTH).lower()
    return re.sub(r'\s+', ' ', folded)


def detect_injection(text: str) -> list[str]:
    """Categories of prompt injection phrasing found in ``text``, without duplicates."""
    if not text:
        return []
    normalized = normalize_for_scan(text)
    found: list[str] = []
    for category, pattern in _INJECTION_PATTERNS:
        if category not in found and pattern.search(normalized):
            found.append(category)
    return found


# ---------------------------------------------------------------------------
# Applying the rules to a conversation
# ---------------------------------------------------------------------------


@dataclass
class GuardrailOutcome:
    """What happened to a request. Counts and categories only, never the matched text."""

    pii: dict[str, int] = field(default_factory=dict)
    injection: list[str] = field(default_factory=list)
    masked: bool = False
    blocked: str | None = None  # 'pii' or 'injection' when the request must be refused

    @property
    def triggered(self) -> bool:
        return bool(self.pii or self.injection)


def _text_parts(content: Any) -> list[tuple[str, int | None]]:
    """Text found in a message ``content``: ``(text, part index)``; index is ``None`` for a plain string."""
    if isinstance(content, str):
        return [(content, None)]
    if isinstance(content, list):
        return [
            (part['text'], index)
            for index, part in enumerate(content)
            if isinstance(part, dict) and part.get('type') == 'text' and isinstance(part.get('text'), str)
        ]
    return []


def _message_text(message: dict) -> str:
    return '\n'.join(text for text, _ in _text_parts(message.get('content')))


def _rewrite(message: dict, transform) -> dict:
    """A copy of ``message`` with ``transform`` applied to each text piece of its content."""
    content = message.get('content')
    if isinstance(content, str):
        return {**message, 'content': transform(content)}
    if isinstance(content, list):
        parts = [
            {**part, 'text': transform(part['text'])}
            if isinstance(part, dict) and part.get('type') == 'text' and isinstance(part.get('text'), str)
            else part
            for part in content
        ]
        return {**message, 'content': parts}
    return message


def apply_guardrails(messages: list[dict], settings: GuardrailSettings) -> tuple[list[dict], GuardrailOutcome]:
    """Check the newest user message and return the messages to send on, plus what was found.

    * The newest user message is the only one that is reported on or can block, so a
      refused message does not make every later request in the same chat fail.
    * With the ``mask`` action every user message is masked, because stored history
      still holds the original text and would otherwise reach the model on the next turn.
    * Only user messages are touched; system, assistant and tool messages pass through.
    """
    outcome = GuardrailOutcome()
    last_user = next(
        (index for index in range(len(messages) - 1, -1, -1) if messages[index].get('role') == 'user'), None
    )
    if not settings.active or last_user is None:
        return messages, outcome

    kinds = settings.pii_kinds if settings.pii_action != ACTION_OFF else ()
    _scan_latest(_message_text(messages[last_user]), settings, kinds, outcome)
    if outcome.blocked or settings.pii_action != ACTION_MASK or not kinds:
        return messages, outcome

    return _mask_user_messages(messages, kinds, outcome), outcome


def _scan_latest(text: str, settings: GuardrailSettings, kinds: tuple[str, ...], outcome: GuardrailOutcome) -> None:
    """Record what the newest user message contains and whether it must be refused."""
    for finding in find_pii(text, kinds):
        outcome.pii[finding.kind] = outcome.pii.get(finding.kind, 0) + 1
    if settings.injection_action != ACTION_OFF:
        outcome.injection = detect_injection(text)

    if outcome.pii and settings.pii_action == ACTION_BLOCK:
        outcome.blocked = 'pii'
    elif outcome.injection and settings.injection_action == ACTION_BLOCK:
        outcome.blocked = 'injection'


def _mask_user_messages(messages: list[dict], kinds: tuple[str, ...], outcome: GuardrailOutcome) -> list[dict]:
    def mask(text: str) -> str:
        return mask_pii(text, find_pii(text, kinds))

    result = []
    for message in messages:
        rewritten = _rewrite(message, mask) if message.get('role') == 'user' else message
        outcome.masked = outcome.masked or rewritten != message
        result.append(rewritten)
    return result


def clean_pii_kinds(value: Any) -> tuple[str, ...]:
    """Known PII kinds from a stored list, in canonical order; unknown entries are dropped."""
    if not isinstance(value, (list, tuple, set, frozenset)):
        return DEFAULT_PII_KINDS
    chosen = {kind for kind in value if isinstance(kind, str)}
    return tuple(kind for kind in PII_KINDS if kind in chosen)


def clean_action(value: Any, allowed: tuple[str, ...], default: str) -> str:
    return value if isinstance(value, str) and value in allowed else default
