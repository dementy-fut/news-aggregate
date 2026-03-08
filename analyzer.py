# analyzer.py
import json
import logging
import os
import re
import time
from datetime import date

from google import genai
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


def get_client():
    return genai.Client(api_key=os.environ["GEMINI_API_KEY"])

MODEL = "gemini-2.0-flash"


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
    """Parse Gemini response into {article_id: score}."""
    cleaned = strip_code_block(response_text)
    data = json.loads(cleaned)
    result = {}
    for item in data:
        aid = item.get("id", "")
        score = item.get("score", 0)
        if aid in valid_ids and isinstance(score, int) and 1 <= score <= 10:
            result[aid] = score
    return result


def filter_by_importance(articles: list[dict], client) -> list[dict]:
    """Score articles and update DB. Returns only important ones (score >= 7)."""
    if not articles:
        return []

    batch_size = 30
    important = []

    for i in range(0, len(articles), batch_size):
        batch = articles[i : i + batch_size]
        prompt = build_importance_prompt(batch)
        valid_ids = [a["id"] for a in batch]

        try:
            response = client.models.generate_content(model=MODEL, contents=prompt)
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


def cluster_articles(articles: list[dict], client) -> list[dict]:
    """Group articles into event clusters."""
    if not articles:
        return []

    prompt = build_cluster_prompt(articles)
    try:
        response = client.models.generate_content(model=MODEL, contents=prompt)
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


def analyze_cluster(cluster: dict, articles_by_id: dict[str, dict], client) -> dict | None:
    """Analyze a single cluster and return event data for DB."""
    article_ids = cluster.get("article_ids", [])
    articles = [articles_by_id[aid] for aid in article_ids if aid in articles_by_id]

    if len(articles) < 2:
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
        response = client.models.generate_content(model=MODEL, contents=prompt)
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

    client = get_client()
    articles = get_unanalyzed_articles(category)
    logger.info(f"Found {len(articles)} unanalyzed articles")

    if not articles:
        return

    logger.info("Stage 0: Filtering by importance...")
    important = filter_by_importance(articles, client)
    logger.info(f"  {len(important)} articles passed importance filter (of {len(articles)})")

    if not important:
        return

    logger.info("Stage 1: Clustering articles into events...")
    clusters = cluster_articles(important, client)
    logger.info(f"  Found {len(clusters)} event clusters")

    logger.info("Stage 2: Analyzing each cluster...")
    articles_by_id = {a["id"]: a for a in important}

    for cluster in clusters:
        result = analyze_cluster(cluster, articles_by_id, client)
        if result:
            insert_event(result["event"], result["article_ids"])
            logger.info(f"  Saved event: {result['event']['title'][:60]}")


def analyze_all():
    """Run analysis for all categories."""
    from collector import load_config
    config = load_config()
    for category in config["categories"]:
        analyze_category(category)
