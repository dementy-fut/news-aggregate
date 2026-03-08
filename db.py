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
