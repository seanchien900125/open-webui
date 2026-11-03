"""Unit tests for the BM25 tokenizers used by hybrid search.

The tokenizer module depends on the standard library only. It is loaded straight
from its file so these tests do not need the rest of the backend installed.
"""

import importlib.util
import logging
from pathlib import Path

import pytest

_MODULE_PATH = Path(__file__).resolve().parents[2] / 'open_webui' / 'retrieval' / 'tokenizer.py'
_spec = importlib.util.spec_from_file_location('bm25_tokenizer_under_test', _MODULE_PATH)
tokenizer = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(tokenizer)


class TestWhitespaceCompatibility:
    """Text without CJK must tokenize exactly as the old `text.split()` did."""

    @pytest.mark.parametrize(
        'text',
        [
            '',
            '   ',
            'hello world',
            'Hello,  World!\nsecond line\tTabbed',
            'snake_case kebab-case CamelCase 3.14 v0.12.5',
            'données françaises, naïve café',
            'Привет мир',
            '데이터베이스 검색 엔진',  # Korean separates words with spaces
        ],
    )
    def test_matches_str_split(self, text):
        assert tokenizer.tokenize_cjk(text) == text.split()
        assert tokenizer.tokenize_whitespace(text) == text.split()


class TestCjkBigrams:
    def test_chinese_run_becomes_overlapping_bigrams(self):
        assert tokenizer.tokenize_cjk('資料庫') == ['資料', '料庫']

    def test_two_characters_make_one_token(self):
        assert tokenizer.tokenize_cjk('檢索') == ['檢索']

    def test_single_character_is_kept(self):
        assert tokenizer.tokenize_cjk('我 愛') == ['我', '愛']
        assert tokenizer.tokenize_cjk('a的b') == ['a', '的', 'b']

    def test_whitespace_still_separates_runs(self):
        assert tokenizer.tokenize_cjk('資料庫 檢索') == ['資料', '料庫', '檢索']

    def test_mixed_script_keeps_latin_tokens_whole(self):
        assert tokenizer.tokenize_cjk('使用Python3開發資料庫') == [
            '使用',
            'Python3',
            '開發',
            '發資',
            '資料',
            '料庫',
        ]

    def test_fullwidth_punctuation_between_runs_is_dropped(self):
        assert tokenizer.tokenize_cjk('資料庫，並且') == ['資料', '料庫', '並且']
        assert tokenizer.tokenize_cjk('（檢索）') == ['檢索']

    def test_japanese_kana_and_kanji(self):
        assert tokenizer.tokenize_cjk('データベース') == ['デー', 'ータ', 'タベ', 'ベー', 'ース']
        assert tokenizer.tokenize_cjk('検索エンジン') == ['検索', '索エ', 'エン', 'ンジ', 'ジン']

    def test_supplementary_plane_han(self):
        # U+20000 and U+20001 are outside the Basic Multilingual Plane.
        assert tokenizer.tokenize_cjk('\U00020000\U00020001') == ['\U00020000\U00020001']

    def test_traditional_and_simplified_are_both_covered(self):
        assert tokenizer.tokenize_cjk('向量资料库') == ['向量', '量资', '资料', '料库']


class TestRegistry:
    def test_default_is_cjk(self):
        assert tokenizer.get_bm25_tokenizer(None) is tokenizer.tokenize_cjk
        assert tokenizer.get_bm25_tokenizer('') is tokenizer.tokenize_cjk
        assert tokenizer.DEFAULT_BM25_TOKENIZER == 'cjk'

    def test_named_lookup(self):
        assert tokenizer.get_bm25_tokenizer('whitespace') is tokenizer.tokenize_whitespace
        assert tokenizer.get_bm25_tokenizer('cjk') is tokenizer.tokenize_cjk

    def test_unknown_name_falls_back_to_default_with_warning(self, caplog):
        with caplog.at_level(logging.WARNING):
            assert tokenizer.get_bm25_tokenizer('jieba') is tokenizer.tokenize_cjk
        assert 'jieba' in caplog.text

    def test_validation(self):
        assert tokenizer.is_valid_bm25_tokenizer('cjk')
        assert tokenizer.is_valid_bm25_tokenizer('whitespace')
        assert not tokenizer.is_valid_bm25_tokenizer('jieba')
        assert not tokenizer.is_valid_bm25_tokenizer('')
        assert not tokenizer.is_valid_bm25_tokenizer(None)


CORPUS = [
    '向量資料庫可以儲存文件的嵌入向量，並支援相似度搜尋。',
    '今天的天氣很好，適合出門散步與運動。',
    '公司的請假規定：員工每年享有十四天的特休假。',
    '混合檢索結合關鍵字與語意搜尋，提升召回率。',
    '咖啡豆的烘焙程度會影響風味與酸度。',
]


class TestBm25Relevance:
    """End to end with the real BM25 implementation the backend uses."""

    @pytest.fixture
    def bm25(self):
        return pytest.importorskip('rank_bm25')

    def _rank(self, bm25, tokenize, query):
        index = bm25.BM25Okapi([tokenize(doc) for doc in CORPUS])
        scores = index.get_scores(tokenize(query))
        return scores, max(range(len(CORPUS)), key=lambda i: scores[i])

    def test_whitespace_tokenizer_cannot_match_unspaced_chinese(self, bm25):
        scores, _ = self._rank(bm25, tokenizer.tokenize_whitespace, '特休假規定')
        assert all(score == 0 for score in scores)

    @pytest.mark.parametrize(
        ('query', 'expected'),
        [
            ('特休假規定', 2),
            ('向量資料庫', 0),
            ('關鍵字搜尋', 3),
            ('烘焙風味', 4),
        ],
    )
    def test_cjk_tokenizer_finds_the_right_document(self, bm25, query, expected):
        scores, best = self._rank(bm25, tokenizer.tokenize_cjk, query)
        assert best == expected
        assert scores[best] > 0
