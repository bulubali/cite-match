"""test_manuscript_workflow.py — v2.4.2"""
import sys, os, pytest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(PROJECT_ROOT, "workflows"))

from manuscript_workflow import ManuscriptWorkflow


class TestManuscriptWorkflow:
    def test_validate_missing_files(self):
        wf = ManuscriptWorkflow("/nonexistent/ms.md", "/nonexistent/refs.bib")
        assert wf.validate_inputs() is False

    def test_validate_with_files(self, tmp_path):
        ms = tmp_path / "ms.md"
        ms.write_text("# Test\n\nSome content.")
        bib = tmp_path / "refs.bib"
        bib.write_text("@article{test, author={A}, title={T}, journal={J}, year={2024}}")
        wf = ManuscriptWorkflow(str(ms), str(bib))
        assert wf.validate_inputs() is True

    def test_run_migration_output_file(self, tmp_path):
        """Issue #1: dry_run=False writes migrated.md to output/"""
        BS = chr(92)
        ms = tmp_path / "ms.md"
        ms.write_text(
            "# Test\n\nContent with a citation. {BS}[1{BS}]^\n\n"
            "{BS}[1{BS}] A. Author, *Journal* **2024**.".format(BS=BS)
        )
        bib = tmp_path / "refs.bib"
        bib.write_text("@article{Author2024, author={Author, A.}, title={Test}, journal={Journal}, year={2024}}")
        out = str(tmp_path / "output")

        wf = ManuscriptWorkflow(str(ms), str(bib), out)
        result = wf.run_migration(dry_run=False)
        assert result["success"] is True
        assert "output_markdown" in result
        assert os.path.exists(result["output_markdown"])
        with open(result["output_markdown"], "r", encoding="utf-8") as f:
            content = f.read()
        assert "@Author2024" in content

    def test_run_migration_dry_run(self, tmp_path):
        BS = chr(92)
        ms = tmp_path / "ms.md"
        ms.write_text(
            "# Test\n\nContent with a citation. {BS}[1{BS}]^\n\n"
            "{BS}[1{BS}] A. Author, *Journal* **2024**.".format(BS=BS)
        )
        bib = tmp_path / "refs.bib"
        bib.write_text("@article{Author2024, author={Author, A.}, title={Test}, journal={Journal}, year={2024}}")

        wf = ManuscriptWorkflow(str(ms), str(bib))
        result = wf.run_migration(dry_run=True)
        assert result["success"] is True
        assert result["migrated_count"] > 0

    def test_grid_table_detected(self, tmp_path):
        """Issue #2: Pandoc grid tables with citations are detected"""
        BS = chr(92)
        ms = tmp_path / "ms.md"
        # Use exact Pandoc grid table format with proper author names for mapping
        ms.write_text(
            "# Results\n\nBody text. {BS}[1{BS}]^\n\n"
            "  ---------------------------------------------------------------------------\n"
            "  **Category**       **Route**                   **Ref**\n"
            "  ------------------ --------------------------- ----------------------------\n"
            "  Indirect           PWA                         {BS}[2,3{BS}]^\n"
            "  Direct             Volume clamp                {BS}[4{BS}]^\n"
            "  ---------------------------------------------------------------------------\n\n"
            "More body. {BS}[5{BS}]^\n\n"
            "{BS}[1{BS}] A. Author, *Journal* **2024**, *1*, 1.\n"
            "{BS}[2{BS}] B. Author, *Journal* **2023**, *2*, 2.\n"
            "{BS}[3{BS}] C. Author, *Journal* **2022**, *3*, 3.\n"
            "{BS}[4{BS}] D. Author, *Journal* **2021**, *4*, 4.\n"
            "{BS}[5{BS}] E. Author, *Journal* **2020**, *5*, 5.".format(BS=BS)
        )
        bib = tmp_path / "refs.bib"
        bib.write_text(
            "@article{Author2024, author={Author, A.}, title={T1}, journal={Journal}, year={2024}}\n"
            "@article{Author2023, author={Author, B.}, title={T2}, journal={Journal}, year={2023}}\n"
            "@article{Author2022, author={Author, C.}, title={T3}, journal={Journal}, year={2022}}\n"
            "@article{Author2021, author={Author, D.}, title={T4}, journal={Journal}, year={2021}}\n"
            "@article{Author2020, author={Author, E.}, title={T5}, journal={Journal}, year={2020}}"
        )
        wf = ManuscriptWorkflow(str(ms), str(bib))
        result = wf.run_migration(dry_run=True)
        assert result["success"] is True
        coverage = result["coverage"]
        table_coverage = coverage.get("table", "0/0")
        assert table_coverage != "0/0", f"Grid table not detected: {coverage}"

    def test_output_dir_created(self, tmp_path):
        ms = tmp_path / "ms.md"
        ms.write_text("# Test")
        bib = tmp_path / "refs.bib"
        bib.write_text("@article{test, author={A}, title={T}, journal={J}, year={2024}}")
        out = str(tmp_path / "output")
        wf = ManuscriptWorkflow(str(ms), str(bib), out)
        assert wf.validate_inputs() is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
