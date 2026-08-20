"""
test_real_bilingual_pipeline.py — Task 2: 真实双语一致性测试

验证:
1. 中英文 59 个相同 citation key 初始状态
2. 模拟注入 20 篇新文献
3. 最终 Chinese citations == English citations
4. 数量/Key/顺序不同 → FAIL
"""
import sys
import os
import re
import pytest

ENGINE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "engine")
sys.path.insert(0, ENGINE_DIR)

from bilingual_validator import BilingualValidator, BilingualCitationReport
from citation_registry import CitationIntegrityError

FIXTURES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")


def load_fixture(name):
    with open(os.path.join(FIXTURES_DIR, name), 'r', encoding='utf-8') as f:
        return f.read()


def extract_all_keys(text):
    return list(set(re.findall(r'@(\w+)', text)))


class TestRealBilingualPipeline:
    """Task 2: 真实双语管道测试"""

    def test_initial_59_keys_match(self):
        """初始状态: 中英文各有 59 个相同 key"""
        en_text = load_fixture("English_review.md")
        zh_text = load_fixture("Chinese_review.md")

        en_keys = extract_all_keys(en_text)
        zh_keys = extract_all_keys(zh_text)

        assert len(en_keys) == 59, f"EN should have 59 keys, got {len(en_keys)}"
        assert len(zh_keys) == 59, f"ZH should have 59 keys, got {len(zh_keys)}"
        assert set(en_keys) == set(zh_keys), \
            f"Keys differ: EN-ZH={set(en_keys)-set(zh_keys)}, ZH-EN={set(zh_keys)-set(en_keys)}"

    def test_validator_initial_59(self):
        """BilingualValidator 验证初始 59 个 key 一致"""
        en_text = load_fixture("English_review.md")
        zh_text = load_fixture("Chinese_review.md")

        validator = BilingualValidator()
        report = validator.compare_manuscripts(en_text, zh_text)

        assert report.en_unique == 59, f"EN total: {report.en_total}"
        assert report.zh_unique == 59, f"ZH total: {report.zh_total}"
        assert report.count_difference == 0
        assert len(report.missing_in_chinese) == 0
        assert len(report.missing_in_english) == 0
        assert report.is_valid
        # Should NOT raise
        report.raise_if_invalid()

    def test_inject_20_new_papers_preserves_consistency(self):
        """模拟注入 20 篇新文献后中英文引用仍然一致"""
        en_text = load_fixture("English_review.md")
        zh_text = load_fixture("Chinese_review.md")

        # 模拟新增 20 篇
        new_keys = [f'NewPaper2026_{i:03d}' for i in range(1, 21)]
        for i, key in enumerate(new_keys):
            en_text += f"\nAdditional finding reported [@{key}]."
            zh_text += f"\n另有研究发现[@{key}]。"

        # 验证
        en_keys = extract_all_keys(en_text)
        zh_keys = extract_all_keys(zh_text)

        assert len(en_keys) == 79, f"After injection: EN should have 79 keys, got {len(en_keys)}"
        assert len(zh_keys) == 79, f"After injection: ZH should have 79 keys, got {len(zh_keys)}"
        assert set(en_keys) == set(zh_keys), \
            f"Keys differ after injection"

    def test_validator_after_injection(self):
        """注入后 BilingualValidator 验证通过"""
        en_text = load_fixture("English_review.md")
        zh_text = load_fixture("Chinese_review.md")

        new_keys = [f'NewPaper2026_{i:03d}' for i in range(1, 21)]
        for i, key in enumerate(new_keys):
            en_text += f"\nAdditional finding reported [@{key}]."
            zh_text += f"\n另有研究发现[@{key}]。"

        validator = BilingualValidator()
        report = validator.compare_manuscripts(en_text, zh_text)

        assert report.en_unique == 79
        assert report.zh_unique == 79
        assert report.is_valid
        report.raise_if_invalid()

    def test_missing_in_zh_detected(self):
        """中文版缺失引用被检测"""
        en_text = load_fixture("English_review.md")
        zh_text = load_fixture("Chinese_review.md")

        # Add key to EN but not ZH
        en_text += "\nExtra reference [@ExtraKey2026]."

        validator = BilingualValidator()
        report = validator.compare_manuscripts(en_text, zh_text)

        assert not report.is_valid
        assert "ExtraKey2026" in report.missing_in_chinese
        assert report.count_difference > 0

        with pytest.raises(CitationIntegrityError):
            report.raise_if_invalid()

    def test_missing_in_en_detected(self):
        """英文版缺失引用被检测"""
        en_text = load_fixture("English_review.md")
        zh_text = load_fixture("Chinese_review.md")

        # Add key to ZH but not EN
        zh_text += "\n[@ExtraChineseKey2026]"

        validator = BilingualValidator()
        report = validator.compare_manuscripts(en_text, zh_text)

        assert not report.is_valid
        assert "ExtraChineseKey2026" in report.missing_in_english

        with pytest.raises(CitationIntegrityError):
            report.raise_if_invalid()

    def test_order_mismatch_detected(self):
        """引用顺序不一致被检测"""
        en_text = "[@KeyA] and [@KeyB]."
        zh_text = "[@KeyB] and [@KeyA]."

        validator = BilingualValidator()
        report = validator.compare_manuscripts(en_text, zh_text)

        # 两个 key 都存在，但顺序不同
        assert len(report.missing_in_chinese) == 0
        assert len(report.missing_in_english) == 0
        assert not report.order_consistent

    def test_empty_documents(self):
        """空文档验证通过"""
        validator = BilingualValidator()
        report = validator.compare_manuscripts("", "")
        assert report.is_valid
        assert report.en_total == 0
        report.raise_if_invalid()

    def test_report_fields_complete(self):
        """BilingualCitationReport 包含所有必要字段"""
        validator = BilingualValidator()
        report = validator.compare_manuscripts("[@key1]", "[@key1]")

        assert hasattr(report, 'en_total')
        assert hasattr(report, 'zh_total')
        assert hasattr(report, 'common_count')
        assert hasattr(report, 'missing_in_chinese')
        assert hasattr(report, 'missing_in_english')
        assert hasattr(report, 'count_difference')
        assert hasattr(report, 'order_consistent')
        assert hasattr(report, 'is_valid')
        assert hasattr(report, 'raise_if_invalid')


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
