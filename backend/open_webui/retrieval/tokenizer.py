"""Tokenizers for the BM25 (keyword) half of hybrid search.

BM25 only matches whole tokens. The original implementation split on whitespace,
which works for languages that separate words with spaces but turns an unspaced
Chinese or Japanese sentence into one giant token that no query can ever match.

``cjk`` keeps whitespace splitting for everything else and turns each run of
Han/kana characters into overlapping character bigrams, the standard
dictionary-free technique for CJK keyword search. Indexing and querying must use
the same tokenizer, so callers resolve one with :func:`get_bm25_tokenizer` and
share it between both sides.

This module deliberately depends on the standard library only, so it can be
imported and unit tested without the rest of the retrieval stack.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Callable

log = logging.getLogger(__name__)

BM25_TOKENIZER_WHITESPACE = 'whitespace'
BM25_TOKENIZER_CJK = 'cjk'
BM25_TOKENIZERS = (BM25_TOKENIZER_WHITESPACE, BM25_TOKENIZER_CJK)
DEFAULT_BM25_TOKENIZER = BM25_TOKENIZER_CJK

Tokenizer = Callable[[str], list[str]]

# Han (incl. extension A and B-F, compatibility ideographs), Hiragana and Katakana.
# Hangul is left out on purpose: Korean separates words with spaces.
_CJK_RANGES = (
    '぀-ゟ'  # Hiragana
    '゠-ヿ'  # Katakana
    '㐀-䶿'  # CJK Unified Ideographs Extension A
    '一-鿿'  # CJK Unified Ideographs
    '豈-﫿'  # CJK Compatibility Ideographs
    '\U00020000-\U0002fa1f'  # Extensions B-F and the compatibility supplement
)
_CJK_ANY = re.compile(f'[{_CJK_RANGES}]')
_CJK_RUN = re.compile(f'[{_CJK_RANGES}]+')

# A piece sitting between CJK runs that holds no letter or digit (for example the
# full-width comma in "資料庫，並且") is punctuation, not a searchable token.
_HAS_WORD_CHAR = re.compile(r'\w', re.UNICODE)


def tokenize_whitespace(text: str) -> list[str]:
    """Split on whitespace. This is the behaviour hybrid search always had."""
    return text.split()


def tokenize_cjk(text: str) -> list[str]:
    """Whitespace split, with CJK runs expanded into overlapping character bigrams.

    - Text without any CJK character returns exactly what :func:`tokenize_whitespace`
      returns, so non-CJK corpora are unaffected.
    - A CJK run of length >= 2 becomes its bigrams: ``資料庫`` -> ``資料``, ``料庫``.
    - A CJK run of length 1 is kept as a single-character token.
    - Non-CJK text next to a CJK run stays a token (``Python3``); pieces made only
      of punctuation are dropped.
    """
    if not _CJK_ANY.search(text):
        return text.split()

    tokens: list[str] = []
    for chunk in text.split():
        position = 0
        for match in _CJK_RUN.finditer(chunk):
            if match.start() > position:
                _append_non_cjk(tokens, chunk[position : match.start()])
            run = match.group()
            if len(run) == 1:
                tokens.append(run)
            else:
                tokens.extend(run[i : i + 2] for i in range(len(run) - 1))
            position = match.end()
        if position < len(chunk):
            _append_non_cjk(tokens, chunk[position:])
    return tokens


def _append_non_cjk(tokens: list[str], piece: str) -> None:
    if _HAS_WORD_CHAR.search(piece):
        tokens.append(piece)


_TOKENIZERS: dict[str, Tokenizer] = {
    BM25_TOKENIZER_WHITESPACE: tokenize_whitespace,
    BM25_TOKENIZER_CJK: tokenize_cjk,
}


def is_valid_bm25_tokenizer(name: str | None) -> bool:
    return name in _TOKENIZERS


def get_bm25_tokenizer(name: str | None = None) -> Tokenizer:
    """Return the tokenizer registered under ``name``.

    ``None`` or an empty value selects the default. An unknown name also falls back
    to the default rather than failing a chat request over a bad setting.
    """
    if not name:
        return _TOKENIZERS[DEFAULT_BM25_TOKENIZER]
    tokenizer = _TOKENIZERS.get(name)
    if tokenizer is None:
        log.warning('Unknown BM25 tokenizer %r, falling back to %r', name, DEFAULT_BM25_TOKENIZER)
        return _TOKENIZERS[DEFAULT_BM25_TOKENIZER]
    return tokenizer
