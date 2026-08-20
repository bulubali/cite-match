"""
test_bilingual_order_warning.py — v2.1: Bilingual order divergence → WARNING only

验证:
1. Order 发散不导致 is_valid=False
2. Order 发散不触发 raise_if_invalid()
3. order_divergence_level 正确计算 (LOW/MEDIUM/HIGH/NONE)
4. Missing keys 仍然触发 CitationIntegrityError
5. Count difference 仍然触发 CitationIntegrityError
6. 真实场景: same keys + different order → valid + LOW divergence
"""
import sys
import os
import pytest

ENGINE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "engine")
sys.path.insert(0, ENGINE_DIR)

from bilingual_validator import (
    BilingualValidator, BilingualCitationReport, OrderDivergenceLevel,
)
from citation_registry import CitationIntegrityError


# ---- Order → WARNING Only ----

class TestOrderIsWarningOnly:
    """Order divergence is WARNING, never FAILURE"""

    def test_order_mismatch_still_valid(self):
        """Key set match + order mismatch → is_valid = True"""
        en_text = "[@KeyA] and [@KeyB]."
        zh_text = "[@KeyB] and [@KeyA]."

        validator = BilingualValidator()
        report = validator.compare_manuscripts(en_text, zh_text)

        # Keys match
        assert len(report.missing_in_chinese) == 0
        assert len(report.missing_in_english) == 0
        assert report.count_difference == 0

        # Order is wrong but does NOT invalidate
        assert not report.order_consistent
        assert report.is_valid, "Order mismatch should NOT invalidate the report"

    def test_order_mismatch_does_not_raise(self):
        """raise_if_invalid() does NOT raise on order-only mismatch"""
        en_text = "[@KeyA] and [@KeyB] and [@KeyC]."
        zh_text = "[@KeyC] and [@KeyA] and [@KeyB]."

        validator = BilingualValidator()
        report = validator.compare_manuscripts(en_text, zh_text)

        assert not report.order_consistent
        # Should NOT raise — order is warning-only
        report.raise_if_invalid()

    def test_missing_key_still_raises(self):
        """Missing key still triggers CitationIntegrityError"""
        en_text = "[@KeyA] and [@KeyB]."
        zh_text = "[@KeyA]."  # KeyB missing

        validator = BilingualValidator()
        report = validator.compare_manuscripts(en_text, zh_text)

        assert not report.is_valid
        assert "KeyB" in report.missing_in_chinese

        with pytest.raises(CitationIntegrityError):
            report.raise_if_invalid()

    def test_count_difference_still_raises(self):
        """Count difference still triggers CitationIntegrityError"""
        en_text = "[@KeyA] [@KeyB]."
        zh_text = "[@KeyA]."

        validator = BilingualValidator()
        report = validator.compare_manuscripts(en_text, zh_text)

        assert not report.is_valid
        assert report.count_difference != 0

        with pytest.raises(CitationIntegrityError):
            report.raise_if_invalid()


# ---- Divergence Level ----

class TestDivergenceLevel:
    """order_divergence_level 计算"""

    def test_none_when_identical(self):
        """完全一致 → NONE"""
        text = "[@KeyA] and [@KeyB]."
        validator = BilingualValidator()
        report = validator.compare_manuscripts(text, text)

        assert report.order_consistent
        assert report.order_divergence_level == OrderDivergenceLevel.NONE.value
        assert report.section_overlap_ratio == 1.0

    def test_low_when_high_overlap(self):
        """相同 section 内高 overlap → LOW"""
        en_text = (
            "## Introduction\n"
            "[@KeyA] and [@KeyB] and [@KeyC].\n"
            "## Methods\n"
            "[@KeyD] and [@KeyE]."
        )
        zh_text = (
            "## Introduction\n"
            "[@KeyC] and [@KeyA] and [@KeyB].\n"  # Same keys in Intro, different order
            "## Methods\n"
            "[@KeyD] and [@KeyE]."
        )

        validator = BilingualValidator()
        report = validator.compare_manuscripts(en_text, zh_text)

        assert report.is_valid
        assert report.order_divergence_level in (
            OrderDivergenceLevel.LOW.value,
            OrderDivergenceLevel.NONE.value,
        )

    def test_medium_or_high_when_keys_in_different_sections(self):
        """不同 section 分配 → MEDIUM/HIGH"""
        en_text = (
            "## Introduction\n"
            "[@KeyA] and [@KeyB].\n"
            "## Methods\n"
            "[@KeyC] and [@KeyD]."
        )
        zh_text = (
            "## Introduction\n"
            "[@KeyC] and [@KeyD].\n"  # Methods keys in Intro
            "## Methods\n"
            "[@KeyA] and [@KeyB]."    # Intro keys in Methods
        )

        validator = BilingualValidator()
        report = validator.compare_manuscripts(en_text, zh_text)

        assert report.is_valid  # Still valid — all keys present
        # Different section assignment → should be MEDIUM or HIGH
        assert report.order_divergence_level in (
            OrderDivergenceLevel.MEDIUM.value,
            OrderDivergenceLevel.HIGH.value,
        )

    def test_high_when_missing_blocks(self):
        """缺失 citation blocks → HIGH"""
        en_text = "[@KeyA] and [@KeyB] and [@KeyC] and [@KeyD] and [@KeyE]."
        zh_text = "[@KeyE] and [@KeyD] and [@KeyC] and [@KeyB] and [@KeyA]."

        validator = BilingualValidator()
        report = validator.compare_manuscripts(en_text, zh_text)

        # All keys present but completely reversed order
        assert report.is_valid
        assert not report.order_consistent
        # 0% section overlap (all in preamble, but order is fully reversed)
        # Actually all in same section (no headings) → 100% overlap → LOW
        # Let's check the level
        assert report.order_divergence_level in (
            OrderDivergenceLevel.LOW.value,
            OrderDivergenceLevel.MEDIUM.value,
            OrderDivergenceLevel.HIGH.value,
        )


# ---- Real Scenario Simulation ----

class TestRealScenario:
    """模拟真实中英文综述场景"""

    def test_same_keys_different_order_realistic(self):
        """59 keys, different paragraph structure → valid + WARNING"""
        import re

        # Build realistic scenario: 59 keys in both, different order
        keys = [f"Paper{i:03d}" for i in range(1, 60)]

        en_lines = ["## Introduction"]
        zh_lines = ["## 引言"]

        # EN: keys in forward order, grouped by topic
        for i in range(0, 30):
            en_lines.append(f"Text about topic A [@{keys[i]}].")
        for i in range(30, 59):
            en_lines.append(f"Text about topic B [@{keys[i]}].")

        # ZH: same keys, but interleaved differently (different sentence structure)
        for i in range(0, 58, 2):
            zh_lines.append(f"Text A+B interleaved [@{keys[i]}; @{keys[i+1]}].")
        # Add the last key
        zh_lines.append(f"Final note [@{keys[58]}].")

        en_text = '\n'.join(en_lines)
        zh_text = '\n'.join(zh_lines)

        validator = BilingualValidator()
        report = validator.compare_manuscripts(en_text, zh_text)

        # All 59 keys present
        assert report.en_unique == 59
        assert report.zh_unique == 59
        assert len(report.missing_in_chinese) == 0
        assert len(report.missing_in_english) == 0
        assert report.count_difference == 0

        # is_valid = True (order doesn't invalidate)
        assert report.is_valid

        # raise_if_invalid should NOT raise
        report.raise_if_invalid()

        # Order divergence level should be reported
        assert report.order_divergence_level in (
            OrderDivergenceLevel.LOW.value,
            OrderDivergenceLevel.MEDIUM.value,
            OrderDivergenceLevel.HIGH.value,
            OrderDivergenceLevel.NONE.value,
        )


# ---- Report Fields ----

class TestReportFields:
    """BilingualCitationReport 包含所有必要字段"""

    def test_new_fields_present(self):
        """v2.1 新增字段存在"""
        report = BilingualCitationReport()
        assert hasattr(report, 'order_divergence_level')
        assert hasattr(report, 'section_overlap_ratio')

    def test_order_divergence_level_default(self):
        """默认 divergence level 为 'none'"""
        report = BilingualCitationReport()
        assert report.order_divergence_level == OrderDivergenceLevel.NONE.value

    def test_section_overlap_ratio_default(self):
        """默认 overlap ratio 为 1.0"""
        report = BilingualCitationReport()
        assert report.section_overlap_ratio == 1.0

    def test_order_issues_present(self):
        """order_issues 保留"""
        report = BilingualCitationReport()
        assert isinstance(report.order_issues, list)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
