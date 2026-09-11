-- ============================================================================
-- JanMat v2 schema — knowledge base (RAG) + public comments on bills/articles,
-- authenticated via Supabase Auth (email magic link).
--
-- Run this once in the Supabase SQL editor on a fresh project.
-- ============================================================================

create extension if not exists vector;
create extension if not exists pg_trgm;

-- ----------------------------------------------------------------------------
-- documents / chunks: the knowledge base. Full text of every PDF page and
-- HTML paragraph is stored — nothing is summarized away before storage.
-- ----------------------------------------------------------------------------
create table if not exists documents (
    id                bigint generated always as identity primary key,
    source            text not null,
    kind              text not null check (kind in ('bill_pdf', 'bill_page', 'article', 'public_opinion')),
    title             text not null,
    url               text not null unique,
    published_at      timestamptz,
    fetched_at        timestamptz not null default now(),
    full_text_sha256  text,
    status            text not null default 'ingested' check (status in ('ingested', 'failed', 'stale')),
    error             text,
    metadata          jsonb not null default '{}'::jsonb
);
create index if not exists idx_documents_source on documents(source);
create index if not exists idx_documents_kind on documents(kind);

create table if not exists chunks (
    id            bigint generated always as identity primary key,
    document_id   bigint not null references documents(id) on delete cascade,
    chunk_index   int not null,
    page_number   int,
    content       text not null,
    token_count   int,
    embedding     vector(384),
    created_at    timestamptz not null default now(),
    unique (document_id, chunk_index)
);
create index if not exists idx_chunks_document on chunks(document_id);
create index if not exists idx_chunks_embedding on chunks
    using ivfflat (embedding vector_cosine_ops) with (lists = 100);
-- Keyword index alongside the vector index — used for the broadened hybrid
-- retrieval in rag.py (vector similarity + keyword match, merged).
create index if not exists idx_chunks_content_trgm on chunks using gin (content gin_trgm_ops);

-- ----------------------------------------------------------------------------
-- chat memory
-- ----------------------------------------------------------------------------
create table if not exists chat_sessions (
    id          uuid primary key default gen_random_uuid(),
    created_at  timestamptz not null default now(),
    label       text
);

create table if not exists chat_messages (
    id             bigint generated always as identity primary key,
    session_id     uuid not null references chat_sessions(id) on delete cascade,
    role           text not null check (role in ('user', 'assistant')),
    content        text not null,
    citations      jsonb not null default '[]'::jsonb,
    input_mode     text not null default 'text' check (input_mode in ('text', 'voice')),
    language_code  text,
    created_at     timestamptz not null default now()
);
create index if not exists idx_chat_messages_session on chat_messages(session_id, created_at);

create table if not exists ingestion_runs (
    id           bigint generated always as identity primary key,
    started_at   timestamptz not null,
    finished_at  timestamptz,
    status       text not null default 'running' check (status in ('running', 'success', 'failed')),
    detail       jsonb
);

-- ----------------------------------------------------------------------------
-- match_chunks: broadened retrieval RPC. Returns more candidates than before
-- (caller controls match_count) and includes a trigram keyword score so the
-- backend can blend vector + keyword ranking instead of vector-only.
-- ----------------------------------------------------------------------------
create or replace function match_chunks(
    query_embedding vector(384),
    query_text text default '',
    match_count int default 20,
    filter_kind text default null
)
returns table (
    chunk_id bigint,
    document_id bigint,
    content text,
    page_number int,
    similarity float,
    keyword_score float,
    title text,
    url text,
    kind text,
    source text
)
language sql stable
as $$
    select
        c.id as chunk_id,
        c.document_id,
        c.content,
        c.page_number,
        1 - (c.embedding <=> query_embedding) as similarity,
        case when query_text = '' then 0
             else similarity(c.content, query_text) end as keyword_score,
        d.title,
        d.url,
        d.kind,
        d.source
    from chunks c
    join documents d on d.id = c.document_id
    where filter_kind is null or d.kind = filter_kind
    order by
        (1 - (c.embedding <=> query_embedding)) * 0.75
        + coalesce(case when query_text = '' then 0 else similarity(c.content, query_text) end, 0) * 0.25
        desc
    limit match_count;
$$;

-- ============================================================================
-- COMMENTS: public discussion on any bill/article, authenticated via
-- Supabase Auth (auth.users — built in, no custom users table needed).
-- topic_key is the bill/article's URL, so comments don't need a hard foreign
-- key into `documents` (a citizen can comment on something not yet ingested).
-- ============================================================================
create table if not exists comments (
    id            bigint generated always as identity primary key,
    topic_key     text not null,
    topic_title   text,
    user_id       uuid not null references auth.users(id) on delete cascade,
    author_email  text not null,
    body          text not null check (char_length(body) between 1 and 3000),
    created_at    timestamptz not null default now()
);
create index if not exists idx_comments_topic on comments(topic_key, created_at desc);

alter table comments enable row level security;

-- Anyone (including anonymous visitors) can read comments.
create policy "comments are publicly readable"
    on comments for select
    using (true);

-- Only a logged-in user can post, and only as themselves.
create policy "authenticated users can insert their own comment"
    on comments for insert
    to authenticated
    with check (auth.uid() = user_id);

-- A user may delete only their own comment.
create policy "users can delete their own comment"
    on comments for delete
    to authenticated
    using (auth.uid() = user_id);
