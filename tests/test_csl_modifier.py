"""test_csl_modifier.py — v2.5: CSL XML modification"""
import sys, os, pytest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(PROJECT_ROOT, "converters"))

from csl_modifier import CSLModifier


SAMPLE_CSL = """<?xml version="1.0" encoding="utf-8"?>
<style xmlns="http://purl.org/net/xbiblio/csl" class="in-text" version="1.0">
  <info><title>Test Style</title></info>
  <citation>
    <layout delimiter=", ">
      <text variable="author"/>
    </layout>
  </citation>
  <bibliography>
    <layout>
      <text variable="author"/>
    </layout>
  </bibliography>
</style>"""


@pytest.fixture
def csl_file(tmp_path):
    path = tmp_path / "test.csl"
    path.write_text(SAMPLE_CSL, encoding="utf-8")
    return str(path)


class TestCSLModifier:
    def test_loads_valid_csl(self, csl_file):
        modifier = CSLModifier(csl_file)
        assert modifier._root is not None

    def test_ensure_collapse(self, csl_file):
        modifier = CSLModifier(csl_file)
        modified = modifier.ensure_collapse()
        assert modified

    def test_full_author_mode(self, csl_file):
        modifier = CSLModifier(csl_file)
        modified = modifier.set_full_author_display()
        assert modified

    def test_default_author_mode(self, csl_file):
        modifier = CSLModifier(csl_file)
        modifier.set_full_author_display()
        modifier.set_default_author_display()
        # After default, et-al attrs should be removed

    def test_save_creates_new_file(self, csl_file, tmp_path):
        modifier = CSLModifier(csl_file)
        modifier.ensure_collapse()
        out = str(tmp_path / "output.csl")
        result = modifier.save(out)
        assert os.path.exists(result)
        assert result != csl_file  # does not overwrite original

    def test_save_preserves_xml(self, csl_file, tmp_path):
        modifier = CSLModifier(csl_file)
        modifier.ensure_collapse()
        out = str(tmp_path / "preserved.csl")
        modifier.save(out)
        with open(out, "r", encoding="utf-8") as f:
            content = f.read()
        assert "xml" in content.lower()

    def test_collapse_already_present(self, csl_file):
        modifier = CSLModifier(csl_file)
        modifier.ensure_collapse()
        modified_again = modifier.ensure_collapse()
        assert not modified_again  # already has collapse


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
