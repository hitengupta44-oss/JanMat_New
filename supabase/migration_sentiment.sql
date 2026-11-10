-- ============================================================================
-- JanMat migration: sentiment analysis, summaries and word cloud
-- (SIH 2025, PS SIH25035 - "Sentiment analysis of comments received through
-- E-consultation module").
--
-- Run AFTER schema.sql and migration_public_comments.sql. Safe to re-run.
-- ============================================================================

-- 1. Per-comment analysis, written only by the backend (service_role key).
--    Visitors can't fake a sentiment label: there is no UPDATE policy for
--    the anon or authenticated roles on `comments`.
alter table comments add column if not exists sentiment        text;
alter table comments add column if not exists sentiment_score  real;   -- model confidence, 0..1
alter table comments add column if not exists summary          text;   -- one-line summary of the comment
alter table comments add column if not exists analyzed_at      timestamptz;

do $$
begin
    if not exists (select 1 from pg_constraint where conname = 'comments_sentiment_check') then
        alter table comments add constraint comments_sentiment_check
            check (sentiment is null or sentiment in ('positive', 'negative', 'neutral'));
    end if;
end $$;

create index if not exists idx_comments_sentiment on comments(topic_key, sentiment);

-- 2. Overall summary of all comments on one bill (or 'janmat:all' for every bill).
create table if not exists topic_insights (
    topic_key        text primary key,
    topic_title      text,
    overall_summary  text,
    key_points       jsonb not null default '[]'::jsonb,
    comment_count    int not null default 0,
    updated_at       timestamptz not null default now()
);
alter table topic_insights enable row level security;

create or replace view public_topic_insights as
select topic_key, topic_title, overall_summary, key_points, comment_count, updated_at
from topic_insights;
grant select on public_topic_insights to anon, authenticated;

-- 3. Rebuild the public comments view so it also exposes the analysis.
--    (Drop first: CREATE OR REPLACE VIEW can't add columns in the middle.)
drop view if exists public_comments;
create view public_comments as
select id,
       topic_key,
       topic_title,
       body,
       created_at,
       sentiment,
       sentiment_score,
       summary,
       case when position('@' in author_email) > 2
            then left(author_email, 2) || '***@' || split_part(author_email, '@', 2)
            else '***@' || split_part(author_email, '@', 2)
       end as author_label
from comments;
grant select on public_comments to anon, authenticated;
