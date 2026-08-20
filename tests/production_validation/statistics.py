"""
Production Validation — Statistics Engine

Computes all validation metrics from engine output and writes
validation_statistics.json.

Metrics:
- Original / Used / Pending / Injected / Matched / Floating counts
- Coverage percentage
- Average and max similarity
- Average and max density
- Table / Figure / Abstract / Review citation counts
- Word / Paragraph / Sentence counts
"""
import os, sys, re, json
from collections import Counter

ENGINE_DIR = os.path.join(os.path.dirname(__file__), os.pardir, os.pardir, "engine")
if ENGINE_DIR not in sys.path:
    sys.path.insert(0, ENGINE_DIR)


class ValidationStatistics:
    """Compute validation metrics from CiteMatch engine output"""

    def __init__(self, output_dir: str, bib_path: str, manuscript_path: str):
        self._output_dir = output_dir
        self._bib_path = bib_path
        self._manuscript_path = manuscript_path

    def compute(self) -> dict:
        stats = {}
        stats.update(self._count_references())
        stats.update(self._count_pending())
        stats.update(self._count_injected())
        stats.update(self._compute_density())
        stats.update(self._compute_similarity())
        stats.update(self._count_by_zone())
        stats.update(self._count_document())
        stats.update(self._count_output_files())
        return stats

    def _count_references(self) -> dict:
        """Count original, used, matched references"""
        try:
            from bib_parser import BibTeXParser
            parser = BibTeXParser()
            entries = parser.parse_file(self._bib_path)
            total_bib = len(entries)
        except Exception:
            total_bib = 0

        used = 0
        if os.path.exists(self._manuscript_path):
            with open(self._manuscript_path, "r", encoding="utf-8") as f:
                text = f.read()
            used = len(set(re.findall(r'@([A-Za-z0-9_-]+)', text)))

        # Count from candidate table
        candidate_path = os.path.join(self._output_dir, "Citation_Candidate_Table.md")
        accepted = 0
        rejected = 0
        floating = 0
        if os.path.exists(candidate_path):
            with open(candidate_path, "r", encoding="utf-8") as f:
                table = f.read()
            accepted = len(re.findall(r'✅', table))
            rejected = len(re.findall(r'❌', table))
            floating = len(re.findall(r'ROUTING', table))

        return {
            "original_references": total_bib,
            "used_references": used,
            "pending_references": total_bib - used,
            "injected_references": accepted,
            "matched_references": accepted,
            "floating_references": floating,
            "coverage_pct": round(accepted / max(total_bib - used, 1) * 100, 1),
        }

    def _count_pending(self) -> dict:
        pending_path = os.path.join(self._output_dir, "pending_keys.txt")
        count = 0
        if os.path.exists(pending_path):
            with open(pending_path, "r") as f:
                count = len([l for l in f if l.strip()])
        return {"pending_keys_file_count": count}

    def _count_injected(self) -> dict:
        """Count injections in manuscript"""
        if not os.path.exists(self._manuscript_path):
            return {"total_citations": 0, "unique_citekeys": 0}
        with open(self._manuscript_path, "r", encoding="utf-8") as f:
            text = f.read()
        citations = re.findall(r'\[@[^\]]+\]', text)
        unique = set(re.findall(r'@([A-Za-z0-9_-]+)', text))
        return {
            "total_citation_blocks": len(citations),
            "unique_citekeys_in_manuscript": len(unique),
        }

    def _compute_density(self) -> dict:
        if not os.path.exists(self._manuscript_path):
            return {"avg_sentence_density": 0, "max_sentence_density": 0,
                    "avg_paragraph_density": 0, "max_paragraph_density": 0}
        with open(self._manuscript_path, "r", encoding="utf-8") as f:
            text = f.read()

        sentences = re.split(r'(?<=[.!?。！？])\s+', text)
        sent_densities = [len(re.findall(r'\[@[^\]]+\]', s)) for s in sentences if len(s) > 10]
        paragraphs = [p for p in re.split(r'\n\s*\n', text) if len(p.strip()) > 20]
        para_densities = [len(re.findall(r'\[@[^\]]+\]', p)) for p in paragraphs]

        return {
            "avg_sentence_density": round(sum(sent_densities) / max(len(sent_densities), 1), 2),
            "max_sentence_density": max(sent_densities) if sent_densities else 0,
            "avg_paragraph_density": round(sum(para_densities) / max(len(para_densities), 1), 2),
            "max_paragraph_density": max(para_densities) if para_densities else 0,
        }

    def _compute_similarity(self) -> dict:
        candidate_path = os.path.join(self._output_dir, "Citation_Candidate_Table.md")
        if not os.path.exists(candidate_path):
            return {"avg_similarity": 0, "max_similarity": 0}
        with open(candidate_path, "r", encoding="utf-8") as f:
            table = f.read()
        scores = [float(s) for s in re.findall(r'\|\s*([\d.]+)\s*\|', table)
                  if 0 < float(s) <= 1.0]
        return {
            "avg_similarity": round(sum(scores) / max(len(scores), 1), 3),
            "max_similarity": round(max(scores), 3) if scores else 0,
        }

    def _count_by_zone(self) -> dict:
        """Count citations in table, figure, abstract zones"""
        if not os.path.exists(self._manuscript_path):
            return {"table_citation_count": 0, "figure_citation_count": 0,
                    "abstract_citation_count": 0, "review_citation_count": 0}
        with open(self._manuscript_path, "r", encoding="utf-8") as f:
            text = f.read()

        # Abstract
        abs_match = re.search(r'^#\s*Abstract\s*\n(.*?)(?=^#\s)', text,
                            re.MULTILINE | re.DOTALL | re.IGNORECASE)
        abstract_cites = len(re.findall(r'\[@[^\]]+\]', abs_match.group(1))) if abs_match else 0

        # Figures
        figure_cites = 0
        for m in re.finditer(r'!\[([^\]]*)\]\(', text):
            figure_cites += len(re.findall(r'\[@[^\]]+\]', m.group(1)))

        # Tables (markdown pipe tables)
        table_cites = 0
        in_table = False
        for line in text.split('\n'):
            if '|' in line and line.count('|') >= 2:
                in_table = True
                table_cites += len(re.findall(r'\[@[^\]]+\]', line))
            elif in_table and '|' not in line:
                in_table = False

        # Review papers
        review_cites = 0
        summary_path = os.path.join(self._output_dir, "References_Summary.md")
        if os.path.exists(summary_path):
            with open(summary_path, "r", encoding="utf-8") as f:
                review_keys = set(re.findall(r'\| @(\w+) \| review \|', f.read(), re.IGNORECASE))
            for key in review_keys:
                review_cites += len(re.findall(re.escape(key), text))

        return {
            "table_citation_count": table_cites,
            "figure_citation_count": figure_cites,
            "abstract_citation_count": abstract_cites,
            "review_citation_count": review_cites,
        }

    def _count_document(self) -> dict:
        if not os.path.exists(self._manuscript_path):
            return {"word_count": 0, "paragraph_count": 0, "sentence_count": 0}
        with open(self._manuscript_path, "r", encoding="utf-8") as f:
            text = f.read()
        words = len(re.findall(r'\b\w+\b', text))
        paragraphs = len([p for p in re.split(r'\n\s*\n', text) if len(p.strip()) > 20])
        sentences = len([s for s in re.split(r'(?<=[.!?。！？])\s+', text) if len(s.strip()) > 10])
        return {"word_count": words, "paragraph_count": paragraphs, "sentence_count": sentences}

    def _count_output_files(self) -> dict:
        expected = [
            "draft.md", "migrated.md", "injected.md",
            "References_Summary.md", "Citation_Candidate_Table.md",
            "pending_keys.txt", "Final_Manuscript.docx",
        ]
        found = []
        missing = []
        for fname in expected:
            path = os.path.join(self._output_dir, fname)
            if os.path.exists(path):
                found.append(fname)
            else:
                missing.append(fname)
        return {"output_files_found": len(found), "output_files_missing": len(missing),
                "output_files_list": found, "missing_files_list": missing}


def save_statistics(stats: dict, output_path: str):
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(stats, f, indent=2, ensure_ascii=False)
    return output_path


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser(description="Validation Statistics Engine")
    p.add_argument("--output", required=True, help="Path to output directory")
    p.add_argument("--bib", required=True, help="Path to .bib file")
    p.add_argument("--manuscript", required=True, help="Path to injected manuscript")
    args = p.parse_args()
    vs = ValidationStatistics(args.output, args.bib, args.manuscript)
    stats = vs.compute()
    print(json.dumps(stats, indent=2, ensure_ascii=False))
