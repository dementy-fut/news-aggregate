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
