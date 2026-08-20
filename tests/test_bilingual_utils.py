"""test_bilingual_utils.py — v2.5: Bilingual safety utilities"""
import sys, os, pytest

ENGINE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "engine")
sys.path.insert(0, ENGINE_DIR)

from bilingual_utils import (
    normalize_brackets, split_sentences_safely,
    safe_inject_before_punctuation, fuzzy_match_anchor,
)


class TestNormalizeBrackets:
    def test_fullwidth_to_halfwidth(self):
        assert normalize_brackets("［1］") == "[1]"
        assert normalize_brackets("【文献】") == "[文献]"

    def test_already_halfwidth(self):
        assert normalize_brackets("[1]") == "[1]"


class TestSplitSentences:
    def test_english(self):
        sents = split_sentences_safely("Hello. World!")
        assert len(sents) == 2

    def test_chinese(self):
        sents = split_sentences_safely("你好。世界！")
        assert len(sents) == 2


class TestSafeInject:
    def test_before_period(self):
        result = safe_inject_before_punctuation("This is a sensor.", "Key2024")
        assert result == "This is a sensor [@Key2024]."

    def test_no_punctuation(self):
        result = safe_inject_before_punctuation("A sensor", "Key2024")
        assert result == "A sensor [@Key2024]"


class TestFuzzyMatch:
    def test_exact_match(self):
        assert fuzzy_match_anchor("piezoelectric sensor", "This is a piezoelectric sensor.", 0.5)

    def test_no_match(self):
        assert not fuzzy_match_anchor("quantum", "This is a sensor.", 0.5)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
