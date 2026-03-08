# News Lens Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build an MVP news aggregator that collects RSS from 13 sources, uses Gemini to filter/cluster/analyze coverage, stores in Supabase, and displays on a static Vercel site with day pagination.

**Architecture:** Python pipeline (collector → analyzer) runs every 3-4h via GitHub Actions. Supabase stores articles and events. Static HTML/CSS/JS frontend reads Supabase directly via anon key.

**Tech Stack:** Python 3.11+, feedparser, google-generativeai, supabase-py, Supabase (PostgreSQL), Gemini 2.0 Flash, vanilla HTML/CSS/JS, Vercel, GitHub Actions.

**Design doc:** `docs/plans/2026-03-08-news-lens-design.md`

---

### Task 1: Project scaffolding and dependencies

**Files:**
- Create: `requirements.txt`
- Create: `config.yaml`
- Create: `.env.example`
- Create: `.gitignore`

**Step 1: Initialize git repo**

```bash
cd /c/Users/Dem/ai/news-lens
git init
```

**Step 2: Create .gitignore**

```
__pycache__/
*.pyc
.env
venv/
.venv/
node_modules/
```

**Step 3: Create requirements.txt**

```
feedparser>=6.0
google-generativeai>=0.8
supabase>=2.0
python-dotenv>=1.0
pyyaml>=6.0
```

**Step 4: Create .env.example**

```
GEMINI_API_KEY=your_gemini_api_key
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_SERVICE_KEY=your_service_role_key
```

**Step 5: Create config.yaml**

```yaml
categories:
  world:
    label: "World"
    importance_threshold: 7
    sources:
      - name: reuters
        url: "https://www.rss-bridge.org/bridge01/?action=display&bridge=FilterBridge&url=https%3A%2F%2Fwww.reuters.com%2Fworld%2F&format=Atom"
        bias: neutral
      - name: bbc
        url: "https://feeds.bbci.co.uk/news/world/rss.xml"
        bias: center
      - name: cnn
        url: "http://rss.cnn.com/rss/edition_world.rss"
        bias: center-left
      - name: fox_news
        url: "https://moxie.foxnews.com/google-publisher/world.xml"
        bias: right
      - name: aljazeera
        url: "https://www.aljazeera.com/xml/rss/all.xml"
        bias: alternative
      - name: ap_news
        url: "https://rsshub.app/apnews/topics/world-news"
        bias: neutral
      - name: guardian
        url: "https://www.theguardian.com/world/rss"
        bias: left
      - name: rt
        url: "https://www.rt.com/rss/news/"
        bias: russian-state

  ai:
    label: "AI"
    importance_threshold: 7
    sources:
      - name: techcrunch_ai
        url: "https://techcrunch.com/category/artificial-intelligence/feed/"
        bias: tech-industry
      - name: theverge_ai
        url: "https://www.theverge.com/rss/ai-artificial-intelligence/index.xml"
        bias: consumer-tech
      - name: arstechnica
        url: "https://feeds.arstechnica.com/arstechnica/technology-lab"
        bias: technical
      - name: venturebeat_ai
        url: "https://venturebeat.com/category/ai/feed/"
        bias: enterprise
      - name: mit_tech_review
        url: "https://www.technologyreview.com/feed/"
        bias: research
```

> **Note:** Some RSS URLs may need to be verified/updated at implementation time. Reuters and AP don't have official public RSS — alternatives like RSSHub or RSS-Bridge may be needed.

**Step 6: Create virtual environment and install deps**

```bash
python -m venv venv
source venv/Scripts/activate
pip install -r requirements.txt
```

**Step 7: Commit**

```bash
git add .gitignore requirements.txt config.yaml .env.example
git commit -m "feat: project scaffolding with config and dependencies"
```

---

### Task 2: Supabase setup and db.py

**Files:**
- Create: `db.py`
- Create: `tests/test_db.py`

**Prerequisites:** Create a Supabase project at https://supabase.com, then run the following SQL in the Supabase SQL Editor:

```sql
-- Enable UUID generation
create extension if not exists "uuid-ossp";

-- Articles table
create table articles (
  id uuid primary key default uuid_generate_v4(),
  source text not null,
  category text not null,
  title text not null,
  link text unique not null,
  summary text,
  importance int,
  published_at timestamptz,
  collected_at timestamptz default now()
);

create index idx_articles_category on articles(category);
create index idx_articles_published on articles(published_at);
create index idx_articles_importance on articles(importance);

-- Events table
create table events (
  id uuid primary key default uuid_generate_v4(),
  category text not null,
  title text not null,
  summary text,
  coverage_analysis jsonb,
  credibility_score text,
  credibility_reasoning text,
  event_date date not null,
  analyzed_at timestamptz default now()
);

create index idx_events_category on events(category);
create index idx_events_date on events(event_date);

-- Junction table
create table event_articles (
  event_id uuid references events(id) on delete cascade,
  article_id uuid references articles(id) on delete cascade,
  primary key (event_id, article_id)
);

-- Row Level Security
alter table articles enable row level security;
alter table events enable row level security;
alter table event_articles enable row level security;

-- Anon can only read
create policy "anon_read_articles" on articles for select using (true);
create policy "anon_read_events" on events for select using (true);
create policy "anon_read_event_articles" on event_articles for select using (true);

-- Service role can do everything (default)
```

**Step 1: Write test for db client initialization**

```python
# tests/test_db.py
import os
import pytest
from unittest.mock import patch, MagicMock

def test_db_client_requires_env_vars():
    """db.get_client() should raise if env vars missing."""
    with patch.dict(os.environ, {}, clear=True):
        from db import get_client
        with pytest.raises(ValueError, match="SUPABASE_URL"):
            get_client()
```

**Step 2: Run test to verify it fails**

```bash
pytest tests/test_db.py -v
```
Expected: FAIL — `db` module doesn't exist yet.

**Step 3: Implement db.py**

```python
# db.py
import os
from datetime import datetime, date
from dotenv import load_dotenv
from supabase import create_client, Client

load_dotenv()

_client: Client | None = None


def get_client() -> Client:
    global _client
    if _client:
        return _client

    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_KEY")
    if not url:
        raise ValueError("SUPABASE_URL environment variable is required")
    if not key:
        raise ValueError("SUPABASE_SERVICE_KEY environment variable is required")

    _client = create_client(url, key)
    return _client


def insert_article(article: dict) -> dict | None:
    """Insert article if link doesn't already exist. Returns inserted row or None if duplicate."""
    client = get_client()
    existing = client.table("articles").select("id").eq("link", article["link"]).execute()
    if existing.data:
        return None
    result = client.table("articles").insert(article).execute()
    return result.data[0] if result.data else None


def get_unanalyzed_articles(category: str) -> list[dict]:
    """Get articles that haven't been assigned to any event yet."""
    client = get_client()
    # Get all article IDs already in event_articles
    assigned = client.table("event_articles").select("article_id").execute()
    assigned_ids = [r["article_id"] for r in assigned.data]

    query = client.table("articles").select("*").eq("category", category)
    if assigned_ids:
        query = query.not_.in_("id", assigned_ids)
    result = query.execute()
    return result.data


def insert_event(event: dict, article_ids: list[str]) -> dict:
    """Insert event and link it to articles."""
    client = get_client()
    result = client.table("events").insert(event).execute()
    event_row = result.data[0]

    for aid in article_ids:
        client.table("event_articles").insert({
            "event_id": event_row["id"],
            "article_id": aid
        }).execute()

    return event_row


def get_events_by_date(category: str, event_date: str) -> list[dict]:
    """Get events for a specific date and category, with linked articles."""
    client = get_client()
    events = (
        client.table("events")
        .select("*")
        .eq("category", category)
        .eq("event_date", event_date)
        .order("analyzed_at", desc=True)
        .execute()
    )

    for event in events.data:
        links = (
            client.table("event_articles")
            .select("article_id")
            .eq("event_id", event["id"])
            .execute()
        )
        article_ids = [r["article_id"] for r in links.data]
        if article_ids:
            articles = (
                client.table("articles")
                .select("*")
                .in_("id", article_ids)
                .execute()
            )
            event["articles"] = articles.data
        else:
            event["articles"] = []

    return events.data


def get_available_dates(category: str) -> list[str]:
    """Get list of dates that have events, for navigation."""
    client = get_client()
    result = (
        client.table("events")
        .select("event_date")
        .eq("category", category)
        .order("event_date", desc=True)
        .execute()
    )
    return list(dict.fromkeys(r["event_date"] for r in result.data))


def update_article_importance(article_id: str, importance: int):
    """Update importance score for an article."""
    client = get_client()
    client.table("articles").update({"importance": importance}).eq("id", article_id).execute()
```

**Step 4: Run test to verify it passes**

```bash
pytest tests/test_db.py -v
```
Expected: PASS

**Step 5: Commit**

```bash
git add db.py tests/test_db.py
git commit -m "feat: Supabase database client with CRUD operations"
```

---

### Task 3: RSS Collector

**Files:**
- Create: `collector.py`
- Create: `tests/test_collector.py`

**Step 1: Write test for RSS parsing**

```python
# tests/test_collector.py
from unittest.mock import patch, MagicMock
from collector import parse_feed_entries


def test_parse_feed_entries_extracts_fields():
    """parse_feed_entries should extract title, link, summary, published from RSS."""
    mock_feed = MagicMock()
    mock_feed.entries = [
        MagicMock(
            title="Test headline",
            link="https://example.com/article1",
            summary="Test summary text",
            published_parsed=(2026, 3, 8, 12, 0, 0, 0, 0, 0),
        )
    ]
    mock_feed.bozo = False

    with patch("collector.feedparser.parse", return_value=mock_feed):
        results = parse_feed_entries("https://fake.rss/feed", "test_source", "world")

    assert len(results) == 1
    assert results[0]["title"] == "Test headline"
    assert results[0]["link"] == "https://example.com/article1"
    assert results[0]["source"] == "test_source"
    assert results[0]["category"] == "world"


def test_parse_feed_entries_handles_empty_feed():
    """parse_feed_entries should return empty list for empty/broken feed."""
    mock_feed = MagicMock()
    mock_feed.entries = []
    mock_feed.bozo = True

    with patch("collector.feedparser.parse", return_value=mock_feed):
        results = parse_feed_entries("https://fake.rss/feed", "test_source", "world")

    assert results == []
```

**Step 2: Run test to verify it fails**

```bash
pytest tests/test_collector.py -v
```
Expected: FAIL — `collector` module doesn't exist.

**Step 3: Implement collector.py**

```python
# collector.py
import logging
from datetime import datetime, timezone
from time import mktime

import feedparser
import yaml

from db import insert_article

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def load_config(path: str = "config.yaml") -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def parse_feed_entries(url: str, source_name: str, category: str) -> list[dict]:
    """Parse RSS feed and return list of article dicts."""
    feed = feedparser.parse(url)

    if feed.bozo and not feed.entries:
        logger.warning(f"Failed to parse feed from {source_name}: {url}")
        return []

    articles = []
    for entry in feed.entries:
        published_at = None
        if hasattr(entry, "published_parsed") and entry.published_parsed:
            published_at = datetime.fromtimestamp(
                mktime(entry.published_parsed), tz=timezone.utc
            ).isoformat()

        articles.append({
            "source": source_name,
            "category": category,
            "title": entry.get("title", "").strip(),
            "link": entry.get("link", "").strip(),
            "summary": entry.get("summary", "").strip(),
            "published_at": published_at,
        })

    return articles


def collect_all() -> dict[str, int]:
    """Collect articles from all sources in config. Returns {source: count} of new articles."""
    config = load_config()
    stats = {}

    for cat_key, cat_config in config["categories"].items():
        for source in cat_config["sources"]:
            name = source["name"]
            url = source["url"]

            logger.info(f"Collecting from {name} ({cat_key})...")
            articles = parse_feed_entries(url, name, cat_key)

            new_count = 0
            for article in articles:
                if article["link"]:  # skip entries without links
                    result = insert_article(article)
                    if result:
                        new_count += 1

            stats[name] = new_count
            logger.info(f"  {name}: {new_count} new articles (of {len(articles)} parsed)")

    return stats


if __name__ == "__main__":
    stats = collect_all()
    total = sum(stats.values())
    logger.info(f"Collection complete. {total} new articles total.")
```

**Step 4: Run tests to verify they pass**

```bash
pytest tests/test_collector.py -v
```
Expected: PASS

**Step 5: Commit**

```bash
git add collector.py tests/test_collector.py
git commit -m "feat: RSS collector with multi-source feed parsing"
```

---

### Task 4: Gemini Analyzer

**Files:**
- Create: `analyzer.py`
- Create: `tests/test_analyzer.py`

**Step 1: Write test for importance prompt formatting**

```python
# tests/test_analyzer.py
import json
from unittest.mock import patch, MagicMock, AsyncMock
from analyzer import build_importance_prompt, parse_importance_response, build_cluster_prompt


def test_build_importance_prompt():
    """Should format articles into a numbered prompt."""
    articles = [
        {"id": "abc", "title": "Major earthquake hits Japan", "summary": "A 7.2 earthquake..."},
        {"id": "def", "title": "Celebrity gossip update", "summary": "Some celebrity did..."},
    ]
    prompt = build_importance_prompt(articles)
    assert "1." in prompt
    assert "Major earthquake hits Japan" in prompt
    assert "Celebrity gossip update" in prompt
    assert "1-10" in prompt


def test_parse_importance_response_valid():
    """Should parse JSON response into {article_id: score} dict."""
    response_text = json.dumps([
        {"id": "abc", "score": 9},
        {"id": "def", "score": 2},
    ])
    result = parse_importance_response(response_text, ["abc", "def"])
    assert result == {"abc": 9, "def": 2}


def test_parse_importance_response_handles_markdown():
    """Should handle response wrapped in ```json code blocks."""
    response_text = '```json\n[{"id": "abc", "score": 8}]\n```'
    result = parse_importance_response(response_text, ["abc"])
    assert result == {"abc": 8}


def test_build_cluster_prompt():
    """Should format articles for clustering."""
    articles = [
        {"id": "a1", "source": "reuters", "title": "Event X happened", "summary": "Details..."},
        {"id": "a2", "source": "bbc", "title": "Event X occurs", "summary": "More details..."},
    ]
    prompt = build_cluster_prompt(articles)
    assert "reuters" in prompt
    assert "Event X happened" in prompt
    assert "JSON" in prompt
```

**Step 2: Run tests to verify they fail**

```bash
pytest tests/test_analyzer.py -v
```
Expected: FAIL — `analyzer` module doesn't exist.

**Step 3: Implement analyzer.py**

```python
# analyzer.py
import json
import logging
import os
import re
import time
from datetime import date

import google.generativeai as genai
from dotenv import load_dotenv

from db import (
    get_unanalyzed_articles,
    update_article_importance,
    insert_event,
)

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

REQUEST_DELAY = 5  # seconds between Gemini calls


def get_model():
    genai.configure(api_key=os.environ["GEMINI_API_KEY"])
    return genai.GenerativeModel("gemini-2.0-flash")


def strip_code_block(text: str) -> str:
    """Remove ```json ... ``` wrapping if present."""
    text = text.strip()
    match = re.match(r"```(?:json)?\s*\n?(.*?)\n?\s*```", text, re.DOTALL)
    return match.group(1).strip() if match else text


# --- Stage 0: Importance filtering ---

def build_importance_prompt(articles: list[dict]) -> str:
    lines = []
    for i, a in enumerate(articles, 1):
        lines.append(f'{i}. [id: {a["id"]}] {a["title"]}\n   {a.get("summary", "")[:200]}')

    articles_text = "\n".join(lines)
    return f"""Rate the importance of each news article on a scale of 1-10.

Criteria:
- 10: Global event that changes the geopolitical/economic/technological landscape
- 7-9: Significant event, important to know about
- 4-6: Ordinary news
- 1-3: Clickbait, celebrity gossip, filler content, opinion pieces about nothing

Return ONLY a JSON array: [{{"id": "article_id", "score": N}}, ...]

Articles:
{articles_text}"""


def parse_importance_response(response_text: str, valid_ids: list[str]) -> dict[str, int]:
    """Parse Gemini response into {{article_id: score}}."""
    cleaned = strip_code_block(response_text)
    data = json.loads(cleaned)
    result = {}
    for item in data:
        aid = item.get("id", "")
        score = item.get("score", 0)
        if aid in valid_ids and isinstance(score, int) and 1 <= score <= 10:
            result[aid] = score
    return result


def filter_by_importance(articles: list[dict], model) -> list[dict]:
    """Score articles and update DB. Returns only important ones (score >= 7)."""
    if not articles:
        return []

    # Process in batches of 30 (to stay within token limits)
    batch_size = 30
    important = []

    for i in range(0, len(articles), batch_size):
        batch = articles[i : i + batch_size]
        prompt = build_importance_prompt(batch)
        valid_ids = [a["id"] for a in batch]

        try:
            response = model.generate_content(prompt)
            scores = parse_importance_response(response.text, valid_ids)

            for article in batch:
                score = scores.get(article["id"], 5)
                update_article_importance(article["id"], score)
                if score >= 7:
                    important.append(article)
                    logger.info(f"  [{score}] {article['title'][:60]}")

            time.sleep(REQUEST_DELAY)
        except Exception as e:
            logger.error(f"Importance scoring failed for batch: {e}")
            # On failure, include all articles from this batch (fail open)
            important.extend(batch)

    return important


# --- Stage 1: Clustering ---

def build_cluster_prompt(articles: list[dict]) -> str:
    lines = []
    for a in articles:
        lines.append(f'- [id: {a["id"]}] [{a["source"]}] {a["title"]}\n  {a.get("summary", "")[:200]}')

    articles_text = "\n".join(lines)
    return f"""Group these news articles by the event they describe. Articles about the same real-world event should be in the same group.

Rules:
- Only group articles that clearly describe the SAME specific event
- Articles from the same source can be in the same group
- Articles that don't match any group should be in a single-article group
- Each article can only be in one group

Return ONLY a JSON array:
[
  {{
    "event_title": "Short descriptive title of the event",
    "event_summary": "1-2 sentence factual summary of what happened",
    "article_ids": ["id1", "id2", ...]
  }},
  ...
]

Articles:
{articles_text}"""


def parse_cluster_response(response_text: str) -> list[dict]:
    cleaned = strip_code_block(response_text)
    return json.loads(cleaned)


def cluster_articles(articles: list[dict], model) -> list[dict]:
    """Group articles into event clusters."""
    if not articles:
        return []

    prompt = build_cluster_prompt(articles)
    try:
        response = model.generate_content(prompt)
        clusters = parse_cluster_response(response.text)
        time.sleep(REQUEST_DELAY)
        return clusters
    except Exception as e:
        logger.error(f"Clustering failed: {e}")
        return []


# --- Stage 2: Deep analysis ---

def build_analysis_prompt(cluster: dict, articles: list[dict]) -> str:
    lines = []
    for a in articles:
        lines.append(f'### {a["source"]}\nTitle: {a["title"]}\n{a.get("summary", "")}\n')

    articles_text = "\n".join(lines)
    return f"""Analyze how different news sources cover this event:

Event: {cluster["event_title"]}
Summary: {cluster["event_summary"]}

Articles from different sources:
{articles_text}

Provide your analysis as JSON:
{{
  "coverage_analysis": {{
    "<source_name>": {{
      "tone": "neutral/positive/negative/critical/defensive/alarmist",
      "focus": "what aspect this source emphasizes",
      "key_claims": ["specific factual claims made"],
      "omissions": "what this source doesn't mention that others do"
    }}
  }},
  "credibility_score": "confirmed|likely|unverified|disputed",
  "credibility_reasoning": "Why this score — based on source agreement/disagreement on core facts"
}}

Credibility criteria:
- confirmed: all sources agree on core facts
- likely: most sources agree, minor differences
- unverified: few sources or insufficient data to verify
- disputed: sources directly contradict each other on facts (not opinions)

Return ONLY the JSON object."""


def analyze_cluster(cluster: dict, articles_by_id: dict[str, dict], model) -> dict | None:
    """Analyze a single cluster and return event data for DB."""
    article_ids = cluster.get("article_ids", [])
    articles = [articles_by_id[aid] for aid in article_ids if aid in articles_by_id]

    if len(articles) < 2:
        # Single-source event: store without deep analysis
        return {
            "event": {
                "title": cluster["event_title"],
                "summary": cluster["event_summary"],
                "coverage_analysis": None,
                "credibility_score": "unverified",
                "credibility_reasoning": "Single source, cannot cross-reference",
                "event_date": date.today().isoformat(),
            },
            "article_ids": article_ids,
        }

    prompt = build_analysis_prompt(cluster, articles)
    try:
        response = model.generate_content(prompt)
        analysis = json.loads(strip_code_block(response.text))
        time.sleep(REQUEST_DELAY)

        return {
            "event": {
                "title": cluster["event_title"],
                "summary": cluster["event_summary"],
                "coverage_analysis": analysis.get("coverage_analysis"),
                "credibility_score": analysis.get("credibility_score", "unverified"),
                "credibility_reasoning": analysis.get("credibility_reasoning", ""),
                "event_date": date.today().isoformat(),
            },
            "article_ids": article_ids,
        }
    except Exception as e:
        logger.error(f"Analysis failed for '{cluster['event_title']}': {e}")
        return None


# --- Main pipeline ---

def analyze_category(category: str):
    """Run full analysis pipeline for one category."""
    logger.info(f"=== Analyzing category: {category} ===")

    model = get_model()
    articles = get_unanalyzed_articles(category)
    logger.info(f"Found {len(articles)} unanalyzed articles")

    if not articles:
        return

    # Stage 0: Importance filtering
    logger.info("Stage 0: Filtering by importance...")
    important = filter_by_importance(articles, model)
    logger.info(f"  {len(important)} articles passed importance filter (of {len(articles)})")

    if not important:
        return

    # Stage 1: Clustering
    logger.info("Stage 1: Clustering articles into events...")
    clusters = cluster_articles(important, model)
    logger.info(f"  Found {len(clusters)} event clusters")

    # Stage 2: Deep analysis
    logger.info("Stage 2: Analyzing each cluster...")
    articles_by_id = {a["id"]: a for a in important}

    for cluster in clusters:
        result = analyze_cluster(cluster, articles_by_id, model)
        if result:
            insert_event(result["event"], result["article_ids"])
            logger.info(f"  Saved event: {result['event']['title'][:60]}")


def analyze_all():
    """Run analysis for all categories."""
    from collector import load_config
    config = load_config()
    for category in config["categories"]:
        analyze_category(category)
```

**Step 4: Run tests to verify they pass**

```bash
pytest tests/test_analyzer.py -v
```
Expected: PASS

**Step 5: Commit**

```bash
git add analyzer.py tests/test_analyzer.py
git commit -m "feat: Gemini analyzer with importance filtering, clustering, and coverage analysis"
```

---

### Task 5: Main entry point

**Files:**
- Create: `main.py`

**Step 1: Implement main.py**

```python
# main.py
import logging
import sys

from collector import collect_all
from analyzer import analyze_all

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def main():
    logger.info("=== News Lens pipeline starting ===")

    # Step 1: Collect
    logger.info("--- Phase 1: Collecting RSS feeds ---")
    stats = collect_all()
    total_new = sum(stats.values())
    logger.info(f"Collection done: {total_new} new articles")

    if total_new == 0:
        logger.info("No new articles. Skipping analysis.")
        return

    # Step 2: Analyze
    logger.info("--- Phase 2: Analyzing articles ---")
    analyze_all()

    logger.info("=== Pipeline complete ===")


if __name__ == "__main__":
    main()
```

**Step 2: Commit**

```bash
git add main.py
git commit -m "feat: main pipeline entry point (collect → analyze)"
```

---

### Task 6: Frontend — HTML structure

**Files:**
- Create: `frontend/index.html`

**Step 1: Create frontend directory**

```bash
mkdir -p frontend
```

**Step 2: Create index.html**

```html
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>News Lens</title>
    <link rel="stylesheet" href="style.css">
</head>
<body>
    <header>
        <h1>News Lens</h1>
        <p class="subtitle">Cross-source news analysis</p>
    </header>

    <nav class="tabs">
        <button class="tab active" data-category="world">World</button>
        <button class="tab" data-category="ai">AI</button>
    </nav>

    <div class="controls">
        <div class="date-nav">
            <button id="prev-day">&larr;</button>
            <span id="current-date"></span>
            <button id="next-day">&rarr;</button>
        </div>
        <div class="filters">
            <select id="credibility-filter">
                <option value="all">All</option>
                <option value="confirmed">Confirmed</option>
                <option value="likely">Likely</option>
                <option value="unverified">Unverified</option>
                <option value="disputed">Disputed</option>
            </select>
            <label class="toggle">
                <input type="checkbox" id="top-only" checked>
                Top stories only
            </label>
        </div>
    </div>

    <main id="events-container">
        <div class="loading">Loading...</div>
    </main>

    <script src="https://cdn.jsdelivr.net/npm/@supabase/supabase-js@2"></script>
    <script src="app.js"></script>
</body>
</html>
```

**Step 3: Commit**

```bash
git add frontend/index.html
git commit -m "feat: frontend HTML structure with tabs, date nav, filters"
```

---

### Task 7: Frontend — CSS styling

**Files:**
- Create: `frontend/style.css`

**Step 1: Create style.css**

```css
* {
    margin: 0;
    padding: 0;
    box-sizing: border-box;
}

body {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    background: #0f0f0f;
    color: #e0e0e0;
    max-width: 900px;
    margin: 0 auto;
    padding: 20px;
}

header {
    text-align: center;
    margin-bottom: 24px;
}

header h1 {
    font-size: 28px;
    font-weight: 700;
    color: #ffffff;
}

.subtitle {
    color: #888;
    font-size: 14px;
    margin-top: 4px;
}

/* Tabs */
.tabs {
    display: flex;
    gap: 8px;
    margin-bottom: 20px;
    border-bottom: 1px solid #2a2a2a;
    padding-bottom: 12px;
}

.tab {
    background: none;
    border: 1px solid #333;
    color: #888;
    padding: 8px 20px;
    border-radius: 6px;
    cursor: pointer;
    font-size: 14px;
    transition: all 0.2s;
}

.tab:hover {
    color: #ccc;
    border-color: #555;
}

.tab.active {
    background: #1a1a2e;
    color: #fff;
    border-color: #4a4ae0;
}

/* Controls */
.controls {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 24px;
    flex-wrap: wrap;
    gap: 12px;
}

.date-nav {
    display: flex;
    align-items: center;
    gap: 12px;
}

.date-nav button {
    background: #1a1a1a;
    border: 1px solid #333;
    color: #ccc;
    width: 36px;
    height: 36px;
    border-radius: 6px;
    cursor: pointer;
    font-size: 16px;
    transition: all 0.2s;
}

.date-nav button:hover {
    background: #2a2a2a;
}

.date-nav button:disabled {
    opacity: 0.3;
    cursor: not-allowed;
}

#current-date {
    font-size: 16px;
    font-weight: 600;
    min-width: 120px;
    text-align: center;
}

.filters {
    display: flex;
    align-items: center;
    gap: 16px;
}

.filters select {
    background: #1a1a1a;
    border: 1px solid #333;
    color: #ccc;
    padding: 8px 12px;
    border-radius: 6px;
    font-size: 13px;
}

.toggle {
    display: flex;
    align-items: center;
    gap: 6px;
    font-size: 13px;
    color: #888;
    cursor: pointer;
}

.toggle input {
    accent-color: #4a4ae0;
}

/* Event cards */
.event-card {
    background: #1a1a1a;
    border: 1px solid #2a2a2a;
    border-radius: 10px;
    padding: 20px;
    margin-bottom: 16px;
    transition: border-color 0.2s;
}

.event-card:hover {
    border-color: #3a3a3a;
}

.event-header {
    display: flex;
    align-items: flex-start;
    gap: 12px;
    cursor: pointer;
}

.credibility-dot {
    width: 10px;
    height: 10px;
    border-radius: 50%;
    margin-top: 6px;
    flex-shrink: 0;
}

.credibility-dot.confirmed { background: #4caf50; }
.credibility-dot.likely { background: #ff9800; }
.credibility-dot.unverified { background: #9e9e9e; }
.credibility-dot.disputed { background: #f44336; }

.event-title {
    font-size: 17px;
    font-weight: 600;
    color: #fff;
    flex-grow: 1;
}

.event-meta {
    display: flex;
    gap: 12px;
    margin-top: 8px;
    margin-left: 22px;
    font-size: 13px;
    color: #888;
}

.event-meta .badge {
    padding: 2px 8px;
    border-radius: 4px;
    font-size: 11px;
    text-transform: uppercase;
    font-weight: 600;
}

.badge.confirmed { background: #1b3a1b; color: #4caf50; }
.badge.likely { background: #3a2e1b; color: #ff9800; }
.badge.unverified { background: #2a2a2a; color: #9e9e9e; }
.badge.disputed { background: #3a1b1b; color: #f44336; }

.event-summary {
    margin-top: 12px;
    margin-left: 22px;
    font-size: 14px;
    color: #bbb;
    line-height: 1.5;
}

/* Expandable analysis */
.event-analysis {
    display: none;
    margin-top: 16px;
    margin-left: 22px;
    padding-top: 16px;
    border-top: 1px solid #2a2a2a;
}

.event-analysis.open {
    display: block;
}

.source-analysis {
    margin-bottom: 16px;
}

.source-analysis h4 {
    font-size: 14px;
    color: #4a4ae0;
    margin-bottom: 6px;
}

.source-analysis .tone {
    font-size: 12px;
    color: #888;
    margin-bottom: 4px;
}

.source-analysis .focus {
    font-size: 13px;
    color: #bbb;
    line-height: 1.4;
}

.credibility-section {
    margin-top: 16px;
    padding: 12px;
    background: #111;
    border-radius: 6px;
}

.credibility-section h4 {
    font-size: 13px;
    color: #888;
    margin-bottom: 6px;
}

.credibility-section p {
    font-size: 13px;
    color: #bbb;
    line-height: 1.4;
}

.article-links {
    margin-top: 16px;
}

.article-links h4 {
    font-size: 13px;
    color: #888;
    margin-bottom: 8px;
}

.article-links a {
    display: block;
    color: #6a6ae0;
    text-decoration: none;
    font-size: 13px;
    margin-bottom: 4px;
}

.article-links a:hover {
    text-decoration: underline;
}

.article-links .source-label {
    color: #666;
    font-size: 11px;
    margin-right: 6px;
}

/* States */
.loading {
    text-align: center;
    color: #888;
    padding: 60px 0;
    font-size: 15px;
}

.empty {
    text-align: center;
    color: #666;
    padding: 60px 0;
    font-size: 15px;
}
```

**Step 2: Commit**

```bash
git add frontend/style.css
git commit -m "feat: frontend dark theme styling"
```

---

### Task 8: Frontend — JavaScript app logic

**Files:**
- Create: `frontend/app.js`

**Step 1: Create app.js**

```javascript
// app.js
// Replace these with your Supabase project values
const SUPABASE_URL = "YOUR_SUPABASE_URL";
const SUPABASE_ANON_KEY = "YOUR_SUPABASE_ANON_KEY";

const supabase = window.supabase.createClient(SUPABASE_URL, SUPABASE_ANON_KEY);

// State
let currentCategory = "world";
let currentDate = new Date().toISOString().split("T")[0]; // YYYY-MM-DD
let availableDates = [];

// DOM elements
const eventsContainer = document.getElementById("events-container");
const currentDateEl = document.getElementById("current-date");
const prevDayBtn = document.getElementById("prev-day");
const nextDayBtn = document.getElementById("next-day");
const credibilityFilter = document.getElementById("credibility-filter");
const topOnlyToggle = document.getElementById("top-only");

// --- Data fetching ---

async function fetchAvailableDates() {
    const { data, error } = await supabase
        .from("events")
        .select("event_date")
        .eq("category", currentCategory)
        .order("event_date", { ascending: false });

    if (error) {
        console.error("Failed to fetch dates:", error);
        return;
    }

    // Deduplicate
    availableDates = [...new Set(data.map((r) => r.event_date))];

    // If current date has no events, jump to most recent
    if (availableDates.length > 0 && !availableDates.includes(currentDate)) {
        currentDate = availableDates[0];
    }

    updateNavButtons();
}

async function fetchEvents() {
    eventsContainer.innerHTML = '<div class="loading">Loading...</div>';

    const credFilter = credibilityFilter.value;

    let query = supabase
        .from("events")
        .select("*")
        .eq("category", currentCategory)
        .eq("event_date", currentDate)
        .order("analyzed_at", { ascending: false });

    if (credFilter !== "all") {
        query = query.eq("credibility_score", credFilter);
    }

    const { data: events, error } = await query;

    if (error) {
        eventsContainer.innerHTML = '<div class="empty">Error loading events.</div>';
        console.error(error);
        return;
    }

    if (!events || events.length === 0) {
        eventsContainer.innerHTML = '<div class="empty">No events for this date.</div>';
        return;
    }

    // Fetch articles for each event
    for (const event of events) {
        const { data: links } = await supabase
            .from("event_articles")
            .select("article_id")
            .eq("event_id", event.id);

        if (links && links.length > 0) {
            const articleIds = links.map((l) => l.article_id);
            const { data: articles } = await supabase
                .from("articles")
                .select("*")
                .in("id", articleIds);
            event.articles = articles || [];
        } else {
            event.articles = [];
        }
    }

    renderEvents(events);
}

// --- Rendering ---

function renderEvents(events) {
    eventsContainer.innerHTML = "";

    for (const event of events) {
        const card = document.createElement("div");
        card.className = "event-card";
        card.innerHTML = renderEventCard(event);
        eventsContainer.appendChild(card);

        // Click to expand
        card.querySelector(".event-header").addEventListener("click", () => {
            const analysis = card.querySelector(".event-analysis");
            analysis.classList.toggle("open");
        });
    }
}

function renderEventCard(event) {
    const score = event.credibility_score || "unverified";
    const sourceCount = event.articles ? event.articles.length : 0;

    let analysisHtml = "";
    if (event.coverage_analysis) {
        const sources = event.coverage_analysis;
        let sourceSections = "";
        for (const [sourceName, info] of Object.entries(sources)) {
            sourceSections += `
                <div class="source-analysis">
                    <h4>${sourceName}</h4>
                    <div class="tone">Tone: ${info.tone || "n/a"}</div>
                    <div class="focus">${info.focus || ""}</div>
                </div>`;
        }
        analysisHtml = sourceSections;
    }

    let linksHtml = "";
    if (event.articles && event.articles.length > 0) {
        const links = event.articles
            .map(
                (a) =>
                    `<a href="${a.link}" target="_blank" rel="noopener">
                        <span class="source-label">[${a.source}]</span> ${a.title}
                    </a>`
            )
            .join("");
        linksHtml = `<div class="article-links"><h4>Sources</h4>${links}</div>`;
    }

    return `
        <div class="event-header">
            <span class="credibility-dot ${score}"></span>
            <span class="event-title">${event.title}</span>
        </div>
        <div class="event-meta">
            <span>${sourceCount} source${sourceCount !== 1 ? "s" : ""}</span>
            <span class="badge ${score}">${score}</span>
        </div>
        <div class="event-summary">${event.summary || ""}</div>
        <div class="event-analysis">
            ${analysisHtml}
            ${event.credibility_reasoning ? `
                <div class="credibility-section">
                    <h4>Credibility Assessment</h4>
                    <p>${event.credibility_reasoning}</p>
                </div>` : ""}
            ${linksHtml}
        </div>`;
}

// --- Navigation ---

function updateNavButtons() {
    currentDateEl.textContent = formatDate(currentDate);

    const idx = availableDates.indexOf(currentDate);
    nextDayBtn.disabled = idx <= 0;
    prevDayBtn.disabled = idx >= availableDates.length - 1;
}

function formatDate(dateStr) {
    const d = new Date(dateStr + "T00:00:00");
    return d.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
}

prevDayBtn.addEventListener("click", () => {
    const idx = availableDates.indexOf(currentDate);
    if (idx < availableDates.length - 1) {
        currentDate = availableDates[idx + 1];
        updateNavButtons();
        fetchEvents();
    }
});

nextDayBtn.addEventListener("click", () => {
    const idx = availableDates.indexOf(currentDate);
    if (idx > 0) {
        currentDate = availableDates[idx - 1];
        updateNavButtons();
        fetchEvents();
    }
});

// --- Tabs ---

document.querySelectorAll(".tab").forEach((tab) => {
    tab.addEventListener("click", () => {
        document.querySelector(".tab.active").classList.remove("active");
        tab.classList.add("active");
        currentCategory = tab.dataset.category;
        fetchAvailableDates().then(fetchEvents);
    });
});

// --- Filters ---

credibilityFilter.addEventListener("change", fetchEvents);
topOnlyToggle.addEventListener("change", fetchEvents);

// --- Init ---

fetchAvailableDates().then(fetchEvents);
```

**Step 2: Commit**

```bash
git add frontend/app.js
git commit -m "feat: frontend JS with Supabase queries, day pagination, tabs, filters"
```

---

### Task 9: GitHub Actions workflow

**Files:**
- Create: `.github/workflows/collect.yml`

**Step 1: Create workflow**

```yaml
# .github/workflows/collect.yml
name: Collect and Analyze News

on:
  schedule:
    - cron: '0 */3 * * *'  # Every 3 hours
  workflow_dispatch:  # Allow manual trigger

jobs:
  pipeline:
    runs-on: ubuntu-latest

    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: Install dependencies
        run: pip install -r requirements.txt

      - name: Run pipeline
        env:
          GEMINI_API_KEY: ${{ secrets.GEMINI_API_KEY }}
          SUPABASE_URL: ${{ secrets.SUPABASE_URL }}
          SUPABASE_SERVICE_KEY: ${{ secrets.SUPABASE_SERVICE_KEY }}
        run: python main.py
```

**Step 2: Commit**

```bash
git add .github/workflows/collect.yml
git commit -m "feat: GitHub Actions cron workflow for pipeline"
```

---

### Task 10: Vercel deployment setup

**Files:**
- Create: `vercel.json`

**Step 1: Create vercel.json in project root**

```json
{
    "buildCommand": null,
    "outputDirectory": "frontend",
    "framework": null
}
```

**Step 2: Update app.js with actual Supabase credentials**

Replace `YOUR_SUPABASE_URL` and `YOUR_SUPABASE_ANON_KEY` in `frontend/app.js` with actual values from Supabase dashboard (Settings → API).

> **Note:** The anon key is safe to expose in frontend — it only allows read access due to RLS policies.

**Step 3: Deploy to Vercel**

```bash
# Install Vercel CLI if needed
npm i -g vercel

# Deploy
cd /c/Users/Dem/ai/news-lens
vercel --prod
```

Follow prompts to link to your Vercel account.

**Step 4: Commit**

```bash
git add vercel.json
git commit -m "feat: Vercel deployment config"
```

---

### Task 11: End-to-end test

**Step 1: Set up .env with real credentials**

Copy `.env.example` to `.env` and fill in:
- `GEMINI_API_KEY` from https://aistudio.google.com/apikey
- `SUPABASE_URL` and `SUPABASE_SERVICE_KEY` from Supabase dashboard

**Step 2: Run Supabase SQL migration**

Execute the SQL from Task 2 in Supabase SQL Editor.

**Step 3: Run collector only**

```bash
cd /c/Users/Dem/ai/news-lens
source venv/Scripts/activate
python -c "from collector import collect_all; print(collect_all())"
```

Expected: prints dict of `{source: new_article_count}`. Check Supabase table `articles` has rows.

**Step 4: Run full pipeline**

```bash
python main.py
```

Expected: logs show collection, importance scoring, clustering, analysis. Check Supabase `events` table.

**Step 5: Test frontend locally**

```bash
cd frontend
python -m http.server 8000
```

Open http://localhost:8000 — should show events for today's date.

**Step 6: Verify RSS feeds**

Check that all configured RSS URLs return valid feeds. Fix any broken URLs in `config.yaml`.

**Step 7: Commit any fixes**

```bash
git add -A
git commit -m "fix: adjust RSS URLs and config after e2e testing"
```

---

### Task 12: GitHub repo and secrets

**Step 1: Create GitHub repo**

```bash
cd /c/Users/Dem/ai/news-lens
gh repo create news-lens --private --source=. --push
```

**Step 2: Add secrets for GitHub Actions**

```bash
gh secret set GEMINI_API_KEY
gh secret set SUPABASE_URL
gh secret set SUPABASE_SERVICE_KEY
```

**Step 3: Trigger workflow manually to verify**

```bash
gh workflow run collect.yml
gh run list --limit 1
```

Watch the run complete successfully.

**Step 4: Verify Vercel auto-deploys on push**

Link Vercel project to the GitHub repo for automatic deployments.
