# tests/test_analyzer.py
import json
from analyzer import build_importance_prompt, parse_importance_response, build_cluster_prompt, strip_code_block


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


def test_strip_code_block():
    """Should remove markdown code block wrapping."""
    assert strip_code_block('```json\n{"a": 1}\n```') == '{"a": 1}'
    assert strip_code_block('{"a": 1}') == '{"a": 1}'
    assert strip_code_block('```\n[1,2]\n```') == '[1,2]'
