import os
import sys
import importlib
import pytest
from unittest.mock import patch, MagicMock


def _reload_db():
    """Reload db module to reset global _client state."""
    import db
    db._client = None
    return db


def test_db_client_requires_env_vars():
    """db.get_client() should raise if env vars missing."""
    with patch.dict(os.environ, {}, clear=True):
        db = _reload_db()
        with pytest.raises(ValueError, match="SUPABASE_URL"):
            db.get_client()


def test_db_client_requires_service_key():
    """db.get_client() should raise if SUPABASE_SERVICE_KEY is missing."""
    with patch.dict(os.environ, {"SUPABASE_URL": "https://example.supabase.co"}, clear=True):
        db = _reload_db()
        with pytest.raises(ValueError, match="SUPABASE_SERVICE_KEY"):
            db.get_client()


def test_db_client_creates_client():
    """db.get_client() should call create_client with correct args."""
    with patch.dict(os.environ, {
        "SUPABASE_URL": "https://example.supabase.co",
        "SUPABASE_SERVICE_KEY": "test-key"
    }, clear=True):
        db = _reload_db()
        with patch("db.create_client") as mock_create:
            mock_create.return_value = MagicMock()
            client = db.get_client()
            mock_create.assert_called_once_with(
                "https://example.supabase.co", "test-key"
            )


def test_insert_article_skips_duplicate():
    """insert_article should return None if link already exists."""
    db = _reload_db()
    mock_client = MagicMock()
    db._client = mock_client

    # Simulate existing article found
    mock_select = MagicMock()
    mock_select.execute.return_value = MagicMock(data=[{"id": "existing-id"}])
    mock_client.table.return_value.select.return_value.eq.return_value = mock_select

    result = db.insert_article({"link": "https://example.com/article"})
    assert result is None


def test_insert_article_inserts_new():
    """insert_article should insert and return row for new article."""
    db = _reload_db()
    mock_client = MagicMock()
    db._client = mock_client

    # No existing article
    mock_select = MagicMock()
    mock_select.execute.return_value = MagicMock(data=[])
    mock_client.table.return_value.select.return_value.eq.return_value = mock_select

    # Insert returns new row
    inserted_row = {"id": "new-id", "link": "https://example.com/new"}
    mock_insert = MagicMock()
    mock_insert.execute.return_value = MagicMock(data=[inserted_row])
    mock_client.table.return_value.insert.return_value = mock_insert

    result = db.insert_article({"link": "https://example.com/new"})
    assert result == inserted_row


def test_get_events_by_date():
    """get_events_by_date should return events with linked articles."""
    db = _reload_db()
    mock_client = MagicMock()
    db._client = mock_client

    # Mock events query chain
    mock_events_result = MagicMock(data=[{
        "id": "event-1",
        "category": "world",
        "title": "Test Event",
        "event_date": "2026-03-08"
    }])
    (mock_client.table.return_value
     .select.return_value
     .eq.return_value
     .eq.return_value
     .order.return_value
     .execute.return_value) = mock_events_result

    # Mock event_articles query
    mock_links = MagicMock(data=[{"article_id": "art-1"}])
    mock_client.table.return_value.select.return_value.eq.return_value.execute.return_value = mock_links

    # Mock articles query
    mock_articles = MagicMock(data=[{"id": "art-1", "title": "Test Article"}])
    (mock_client.table.return_value
     .select.return_value
     .in_.return_value
     .execute.return_value) = mock_articles

    result = db.get_events_by_date("world", "2026-03-08")
    assert len(result) == 1


def test_get_available_dates():
    """get_available_dates should return deduplicated sorted dates."""
    db = _reload_db()
    mock_client = MagicMock()
    db._client = mock_client

    mock_result = MagicMock(data=[
        {"event_date": "2026-03-08"},
        {"event_date": "2026-03-08"},
        {"event_date": "2026-03-07"},
    ])
    (mock_client.table.return_value
     .select.return_value
     .eq.return_value
     .order.return_value
     .execute.return_value) = mock_result

    dates = db.get_available_dates("world")
    assert dates == ["2026-03-08", "2026-03-07"]
