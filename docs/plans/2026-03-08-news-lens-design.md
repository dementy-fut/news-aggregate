# News Lens — MVP Design

## Overview

System that monitors news from multiple sources, clusters articles about the same event, compares how different outlets cover it, and provides credibility assessment. Filters out noise to show only the most important stories.

## Architecture

```
RSS Sources → Collector (Python) → Supabase (PostgreSQL)
                                        ↓
                                  Analyzer (Gemini Flash)
                                        ↓
                                  Supabase (results)
                                        ↓
                                  Frontend (Vercel)
```

**Pipeline (runs every 3-4 hours via GitHub Actions cron):**

1. **Collector** — parses RSS feeds, saves new articles to Supabase
2. **Analyzer** — three stages:
   - **Stage 0: Importance filtering** — Gemini scores each article 1-10, threshold 7+
   - **Stage 1: Clustering** — groups articles about the same event
   - **Stage 2: Deep analysis** — compares coverage tone/focus, assesses credibility
3. **Frontend** — static site reads from Supabase via JS client

## Categories

### World
Reuters, BBC News, CNN, Fox News, Al Jazeera, AP News, The Guardian, RT English.

Purpose: compare how the same global event is covered across outlets with different editorial positions.

### AI
TechCrunch AI, The Verge AI, Ars Technica, VentureBeat AI, MIT Technology Review.

Purpose: track real AI breakthroughs, filter out clickbait and hype.

### Future (not in MVP)
Crypto, social media trends, etc. — add as new category in config.

## Sources

| Source | Category | Bias/Angle |
|--------|----------|------------|
| Reuters | World | Neutral, factual |
| BBC News | World | Center, British |
| CNN | World | Center-left, American |
| Fox News | World | Right, American |
| Al Jazeera | World | Middle East perspective |
| AP News | World | Neutral, wire agency |
| The Guardian | World | Left, British |
| RT English | World | Russian state perspective |
| TechCrunch AI | AI | Tech industry |
| The Verge AI | AI | Consumer tech |
| Ars Technica | AI | Technical depth |
| VentureBeat AI | AI | Enterprise/business |
| MIT Tech Review | AI | Research-focused |

## Database (Supabase)

### Table: articles
| Field | Type | Description |
|-------|------|-------------|
| id | uuid, PK | |
| source | text | "reuters", "bbc", "rt", etc. |
| category | text | "world" / "ai" |
| title | text | Headline |
| link | text, unique | Article URL |
| summary | text | Description from RSS |
| importance | int | 1-10, scored by Gemini |
| published_at | timestamp | Publication date |
| collected_at | timestamp | When collected |

### Table: events
| Field | Type | Description |
|-------|------|-------------|
| id | uuid, PK | |
| category | text | "world" / "ai" |
| title | text | Event name (from Gemini) |
| summary | text | What happened |
| coverage_analysis | jsonb | Per-source tone/focus/claims |
| credibility_score | text | confirmed/likely/unverified/disputed |
| credibility_reasoning | text | Why this score |
| event_date | date | For pagination by day |
| analyzed_at | timestamp | When analyzed |

### Table: event_articles
| Field | Type | Description |
|-------|------|-------------|
| event_id | uuid, FK → events | |
| article_id | uuid, FK → articles | |

### coverage_analysis example (jsonb)
```json
{
  "reuters": {"tone": "neutral", "focus": "casualties", "key_claims": ["..."]},
  "fox_news": {"tone": "critical", "focus": "government response", "key_claims": ["..."]},
  "rt": {"tone": "defensive", "focus": "western hypocrisy", "key_claims": ["..."]}
}
```

### Security
- anon key: SELECT only (frontend read-only)
- service key: INSERT/UPDATE (Python scripts)

## Gemini Integration

**Model:** Gemini 2.0 Flash via Google AI Studio (free tier)

**Limits:** 15 RPM, 1M TPM, 1500 req/day

**Usage estimate:** 8 cycles/day × ~10-15 requests = 80-120 req/day (well within limits)

**Stage 0 — Importance filtering:**
- Input: all new article titles + summaries
- Output: importance score 1-10 per article
- Threshold: 7+ shown by default

**Stage 1 — Clustering:**
- Input: important articles (title + summary + source)
- Output: [{event_title, event_summary, article_ids}, ...]

**Stage 2 — Analysis per cluster (2+ sources):**
- Input: full article texts for one event
- Output: coverage_analysis, credibility_score, credibility_reasoning

**Rate limiting:** 4-5 second pause between requests.

## Frontend

Static HTML/CSS/JS hosted on Vercel. No framework.

**Features:**
- Category tabs: World, AI
- Day pagination: arrows to navigate history
- Credibility filter: confirmed / likely / unverified / all
- Importance toggle: TOP ONLY (7+) / ALL
- Event cards: color indicator, title, source count, brief comparison
- Expandable: full analysis + links to original articles

**Data:** Supabase JS client with anon key, direct queries.

## Project Structure

```
news-lens/
├── config.yaml
├── main.py
├── collector.py
├── analyzer.py
├── db.py
├── frontend/
│   ├── index.html
│   ├── style.css
│   └── app.js
├── requirements.txt
├── .github/workflows/collect.yml
└── .env
```

## Stack

- **Backend:** Python (feedparser, google-generativeai, supabase-py)
- **Database:** Supabase (PostgreSQL, free tier: 500MB, 50K rows)
- **AI:** Gemini 2.0 Flash (free via AI Studio)
- **Frontend:** HTML/CSS/JS, Supabase JS client
- **Hosting:** Vercel (free tier)
- **Scheduling:** GitHub Actions cron (every 3-4 hours)
- **Cost:** $0
