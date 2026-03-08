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
        if entry.get("published_parsed"):
            published_at = datetime.fromtimestamp(
                mktime(entry["published_parsed"]), tz=timezone.utc
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
                if article["link"]:
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
