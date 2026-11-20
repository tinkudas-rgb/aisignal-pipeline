"""Source configuration for the pipeline. Keyless sources only."""
from __future__ import annotations

# Phase I - bulk acquisition
YC_OSS_ALL = "https://yc-oss.github.io/api/companies/all.json"
OPENTOOLS_SITEMAP = "https://opentools.ai/tools-sitemap.xml"
OPENTOOLS_BASE = "https://opentools.ai"
HF_SPACES_API = "https://huggingface.co/api/spaces"
PWC_API = "https://paperswithcode.co/api/v1"
ARXIV_API = "https://export.arxiv.org/api/query"

# Phase II - news feeds (5 distinct AI news sources)
NEWS_FEEDS = {
    "TechCrunch AI": "https://techcrunch.com/category/artificial-intelligence/feed/",
    "The Verge AI": "https://www.theverge.com/rss/ai-artificial-intelligence/index.xml",
    "MIT Technology Review AI": "https://www.technologyreview.com/topic/artificial-intelligence/feed",
    "Ars Technica AI": "https://arstechnica.com/ai/feed/",
    "VentureBeat AI": "https://venturebeat.com/category/ai/feed/",
}

# Fallback feeds, promoted in order if a primary feed fails at fetch time,
# so the "5 distinct sources" guarantee survives an outage.
NEWS_FEED_FALLBACKS = {
    "VentureBeat AI": ["https://the-decoder.com/feed/",
                       "https://news.google.com/rss/search?q=artificial+intelligence&hl=en-US&gl=US&ceid=US:en"],
}

# Phase II - job boards (5 distinct boards with AI-relevant roles)
JOB_SOURCES = {
    "Arbeitnow": "https://www.arbeitnow.com/api/job-board-api",
    "RemoteOK": "https://remoteok.com/api",
    "Jobicy": "https://jobicy.com/api/v2/remote-jobs?count=50&industry=data-science",
    "Remotive": "https://remotive.com/api/remote-jobs?limit=50",
    "WeWorkRemotely": "https://weworkremotely.com/categories/remote-programming-jobs.rss",
}

AI_KEYWORDS = [
    "ai", "artificial intelligence", "machine learning", "ml ", "llm",
    "deep learning", "nlp", "computer vision", "data scien", "genai",
    "generative", "neural", "agent", "model", "inference", "robotics",
]

USER_AGENTS = [
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_5) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Safari/537.36",
]

# Phase IV - seed canonical entity list (mock registry of 50 known AI companies)
SEED_CANONICAL = [
    "OpenAI", "Anthropic", "Google DeepMind", "Meta AI", "Mistral AI",
    "Cohere", "Hugging Face", "Stability AI", "Midjourney", "Runway",
    "Perplexity", "Scale AI", "Databricks", "Palantir", "Cerebras",
    "Groq", "Together AI", "Fireworks AI", "Replicate", "Weights & Biases",
    "LangChain", "Pinecone", "Weaviate", "Chroma", "Qdrant",
    "ElevenLabs", "Character.AI", "Inflection AI", "xAI", "Adept AI",
    "Cursor", "Codeium", "Tabnine", "Sourcegraph", "Jasper",
    "Copy.ai", "Writer", "Notion AI", "Canva", "Adobe Firefly",
    "Pika", "Synthesia", "HeyGen", "Descript", "Otter.ai",
    "Harvey", "Glean", "Hebbia", "Sierra", "Devin",
]
