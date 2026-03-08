# tests/test_collector.py
from unittest.mock import patch, MagicMock
from collector import parse_feed_entries


def test_parse_feed_entries_extracts_fields():
    """parse_feed_entries should extract title, link, summary, published from RSS."""
    mock_feed = MagicMock()
    mock_feed.entries = [
        {
            "title": "Test headline",
            "link": "https://example.com/article1",
            "summary": "Test summary text",
            "published_parsed": (2026, 3, 8, 12, 0, 0, 0, 0, 0),
        }
    ]
    mock_feed.bozo = False

    with patch("collector.feedparser.parse", return_value=mock_feed):
        results = parse_feed_entries("https://fake.rss/feed", "test_source", "world")

    assert len(results) == 1
    assert results[0]["title"] == "Test headline"
    assert results[0]["link"] == "https://example.com/article1"
    assert results[0]["source"] == "test_source"
    assert results[0]["category"] == "world"
    assert results[0]["summary"] == "Test summary text"
    assert results[0]["published_at"] is not None


def test_parse_feed_entries_handles_empty_feed():
    """parse_feed_entries should return empty list for empty/broken feed."""
    mock_feed = MagicMock()
    mock_feed.entries = []
    mock_feed.bozo = True

    with patch("collector.feedparser.parse", return_value=mock_feed):
        results = parse_feed_entries("https://fake.rss/feed", "test_source", "world")

    assert results == []
