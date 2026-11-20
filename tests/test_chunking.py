import sys
sys.path.insert(0, '/home/sandbox/aisignal-pipeline')
from src.llm.orchestrator import (MAX_TOKENS_PER_CALL, estimate_tokens,
                                  semantic_chunk)


def test_short_text_untouched():
    text = "hello world"
    assert semantic_chunk(text) == text


def test_long_text_within_budget():
    text = "head\n" + "x" * 200 + "\n" + ("body line\n" * 20000)
    out = semantic_chunk(text)
    assert estimate_tokens(out) <= MAX_TOKENS_PER_CALL + 50
    assert "head" in out


def test_boilerplate_dropped():
    text = "real content here\nsubscribe to our newsletter now\n" + "y" * 100
    out = semantic_chunk(text)
    assert "newsletter" not in out.lower()


def test_estimate_monotonic():
    assert estimate_tokens("") >= 1
    assert estimate_tokens("abcd" * 1000) > estimate_tokens("abcd")
