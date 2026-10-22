-- ============================================================================
-- JanMat migration: show every bill's comments to everyone, safely.
-- Safe to re-run. Paste into the Supabase SQL editor and run once.
-- ============================================================================

-- 1. LOCK DOWN THE KNOWLEDGE-BASE TABLES --------------------------------------
-- schema.sql only enabled Row Level Security on `comments`. Tables created in
-- the SQL editor are readable/writable with the public anon key unless RLS is
-- on, so chat history and the knowledge base were exposed. The Space uses the
-- service_role key, which bypasses RLS, so enabling it breaks nothing there.
alter table documents      enable row level security;
alter table chunks         enable row level security;
alter table chat_sessions  enable row level security;
alter table chat_messages  enable row level security;
alter table ingestion_runs enable row level security;

-- 2. PUBLIC LIST OF BILLS (title, link, status only) -------------------------
create or replace view public_bills as
select id,
       title,
       url,
       metadata->>'bill_status' as status,
       fetched_at
from documents
where kind = 'bill_page' and status = 'ingested';

grant select on public_bills to anon, authenticated;

-- 3. PUBLIC COMMENTS WITHOUT EMAIL ADDRESSES ---------------------------------
-- Everyone can read comments through this view. The raw table (with full
-- emails) is no longer readable by visitors.
drop policy if exists "comments are publicly readable" on comments;
drop policy if exists "users can read their own comments" on comments;

create policy "users can read their own comments"
    on comments for select
    to authenticated
    using (auth.uid() = user_id);

create or replace view public_comments as
select id,
       topic_key,
       topic_title,
       body,
       created_at,
       case when position('@' in author_email) > 2
            then left(author_email, 2) || '***@' || split_part(author_email, '@', 2)
            else '***@' || split_part(author_email, '@', 2)
       end as author_label
from comments;

grant select on public_comments to anon, authenticated;
