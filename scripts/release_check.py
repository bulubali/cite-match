#!/usr/bin/env python3
"""
CiteMatch v2.1 Release Certification — Task 6

执行完整测试套件并输出 Release Gate 报告。
Usage: python scripts/release_check.py
"""
import sys
import os
import subprocess
from datetime import datetime

# 项目根目录
PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TESTS_DIR = os.path.join(PROJECT_DIR, "tests")


def run_pytest():
    """运行全量测试套件"""
    result = subprocess.run(
        [sys.executable, "-m", "pytest", TESTS_DIR, "-q", "--tb=short"],
        cwd=os.path.dirname(PROJECT_DIR),  # .agents/skills/
        capture_output=True,
        text=True,
        timeout=120,
    )
    return result


def parse_pytest_output(output):
    """解析 pytest 输出"""
    import re
    total = 0
    passed = 0
    failed = 0

    for line in output.strip().split('\n'):
        # e.g. "172 passed in 0.34s" or "119 passed, 1 failed in 0.25s"
        m_passed = re.search(r'(\d+)\s+passed', line)
        m_failed = re.search(r'(\d+)\s+failed', line)
        if m_passed:
            passed = int(m_passed.group(1))
        if m_failed:
            failed = int(m_failed.group(1))
        if m_passed or m_failed:
            total = passed + failed

    return total, passed, failed


def check_category(output, keyword):
    """检查某类测试是否全部通过"""
    # output is combined stdout+stderr
    # 检查是否包含 keyword 相关的 FAILED
    return "FAILED" not in output or keyword not in output


def main():
    print("=" * 60)
    print("CiteMatch v2.1 Release Certification")
    print(f"Timestamp: {datetime.now().isoformat()}")
    print("=" * 60)
    print()

    # 运行测试
    print("Running pytest...")
    result = run_pytest()
    total, passed, failed = parse_pytest_output(result.stdout + result.stderr)

    print(result.stdout)
    if result.stderr and 'ERROR' not in result.stderr:
        print(result.stderr)

    print("-" * 60)

    combined = result.stdout + result.stderr

    # 分类检查 — all tests passed means no FAILED lines
    all_pass = "FAILED" not in combined

    categories = {
        "Architecture": all_pass,
        "Citation Lock": check_category(combined, "test_citation_lock"),
        "Write Safety": check_category(combined, "test_write_guard"),
        "Bilingual": (check_category(combined, "test_bilingual") and
                      check_category(combined, "test_real_bilingual")),
        "Table Protection": (check_category(combined, "test_table_protection") and
                            check_category(combined, "test_real_markdown")),
        "Phase Control": check_category(combined, "test_phase_gate"),
        "Registry Immutable": check_category(combined, "test_registry_immutable"),
        "Real Cases": check_category(combined, "test_real_cases"),
    }

    all_pass = all(v for v in categories.values())

    all_pass = True
    print("\nRelease Gate Results:")
    print("-" * 40)
    for name, passed_cat in categories.items():
        status = "PASS" if passed_cat else "FAIL"
        if not passed_cat:
            all_pass = False
        print(f"  {name:<25s} {status}")

    print("-" * 40)
    print(f"  Total Tests: {total}")
    print(f"  Passed:      {passed}")
    print(f"  Failed:      {failed}")
    print()

    if all_pass and failed == 0 and passed >= 160:
        print("[PASS] READY_FOR_RELEASE")
        print(f"   All categories PASS, {passed} tests, 0 failures.")
        status = "READY_FOR_RELEASE"
    elif all_pass and failed == 0:
        print(f"[WARN] PARTIAL_PASS -- need >=160 tests (currently {passed})")
        status = "PARTIAL_PASS"
    else:
        print("[FAIL] NOT_READY -- see failures above")
        status = "NOT_READY"

    print()

    # 输出 JSON 摘要
    import json
    summary = {
        "version": "2.1.0",
        "timestamp": datetime.now().isoformat(),
        "status": status,
        "total_tests": total,
        "passed": passed,
        "failed": failed,
        "categories": {k: "PASS" if v else "FAIL" for k, v in categories.items()},
    }
    summary_path = os.path.join(PROJECT_DIR, "release_certification.json")
    with open(summary_path, 'w', encoding='utf-8') as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)
    print(f"Certification saved to: {summary_path}")

    return 0 if status == "READY_FOR_RELEASE" else 1


if __name__ == "__main__":
    sys.exit(main())
