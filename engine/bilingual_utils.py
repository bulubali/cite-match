"""
CiteMatch v2.5 — Bilingual Safety Utilities

Implements the required base toolkit from skills.md:
  - normalize_brackets() — fullwidth → halfwidth bracket conversion
"""
import re
import difflib


def normalize_brackets(text: str) -> str:
    """Convert fullwidth brackets to halfwidth, eliminating IME interference."""
    return text.translate(str.maketrans("［］【】", "[][]"))


def split_sentences_safely(text: str) -> list[str]:
    """Bilingual-compatible sentence splitting that preserves punctuation."""
    sentences = re.split(r"([.!?。！？])", text)
    result = []
    for i in range(0, len(sentences) - 1, 2):
        result.append(sentences[i] + sentences[i + 1])
    if len(sentences) % 2 != 0 and sentences[-1].strip():
        result.append(sentences[-1])
    return [s.strip() for s in result if s.strip()]


def safe_inject_before_punctuation(sentence: str, cite_key: str) -> str:
    """Inject citation before sentence-ending punctuation."""
    match = re.search(r"([.!?。！？」\"\\)]+)$", sentence)
    if match:
        punct = match.group(1)
        base = sentence[:-len(punct)]
        return f"{base} [@{cite_key}]{punct}"
    return f"{sentence} [@{cite_key}]"


def fuzzy_match_anchor(anchor: str, sentence: str, threshold: float = 0.65) -> bool:
    """Bilingual-compatible fuzzy sliding window match using SequenceMatcher."""
    matcher = difflib.SequenceMatcher(None, anchor.lower(), sentence.lower())
    match = matcher.find_longest_match(0, len(anchor), 0, len(sentence))
    return (match.size / len(anchor)) >= threshold
