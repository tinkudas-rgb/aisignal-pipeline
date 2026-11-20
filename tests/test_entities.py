import sys
sys.path.insert(0, '/home/sandbox/aisignal-pipeline')
from src.resolve.entities import EntityResolver, normalize

r = EntityResolver()


def test_exact():
    assert r.resolve("OpenAI") == ("OpenAI", "exact", 1.0)


def test_legal_suffixes():
    assert r.resolve("OpenAI, Inc.") == ("OpenAI", "normalized", 0.97)
    assert r.resolve("Anthropic")[0] == "Anthropic"


def test_alias():
    assert r.resolve("open ai") == ("OpenAI", "alias", 0.95)
    assert r.resolve("HuggingFace") == ("Hugging Face", "alias", 0.95)
    assert r.resolve("DeepMind") == ("Google DeepMind", "alias", 0.95)


def test_case_and_punct():
    assert r.resolve("OPENAI")[0] == "OpenAI"
    assert r.resolve("  openai  ")[0] == "OpenAI"


def test_unmatched_passthrough():
    name, strat, conf = r.resolve("Some Random Startup XYZ")
    assert name == "Some Random Startup XYZ" and strat == "unmatched" and conf == 1.0


def test_empty():
    assert r.resolve("")[1] == "unmatched"


def test_normalize_strips_legal():
    assert normalize("Acme Corp.") == "acme"
    assert normalize("Stability AI") == "stability ai"  # 'ai' is a name, not a suffix
