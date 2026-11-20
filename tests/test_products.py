import sys
sys.path.insert(0, '/home/sandbox/aisignal-pipeline')
from src.crawler.products import parse_tool_page

SAMPLE = open('/tmp/toolpage.html').read() if __import__('os').path.exists('/tmp/toolpage.html') else None


def test_parse_real_tool_page():
    if SAMPLE is None:
        import pytest; pytest.skip("no fixture")
    rec = parse_tool_page(SAMPLE, "https://opentools.ai/tools/naiseai")
    assert rec is not None
    assert rec.content.productName == "Naise.ai"
    assert rec.content.pricingModel.value == "PAID"
    assert rec.source.url.endswith("/tools/naiseai")


def test_parse_garbage_returns_none_or_slug():
    rec = parse_tool_page("<html><body>nothing</body></html>",
                          "https://opentools.ai/tools/sometool")
    assert rec is not None
    assert rec.content.productName == "Sometool"


def test_pricing_default():
    rec = parse_tool_page("<html></html>", "https://opentools.ai/tools/x")
    assert rec.content.pricingModel.value in ("FREE", "FREEMIUM")
