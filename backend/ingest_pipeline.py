"""
Orchestrates one full ingestion run:
  discover URLs -> fetch+extract full text (PDF or HTML) -> chunk -> embed
  -> upsert into Supabase.

Nothing here summarizes. A document that hasn't changed since last run
(same sha256 of its full text) is skipped entirely to save embedding calls.
"""
import logging
from datetime import datetime, timezone
from typing import List

import db
from config import CONFIG
from embeddings import chunk_pages, chunk_text, embed_texts
from pdf_ingest import ingest_source_document
from scraper import PRSDiscovery, DiscoveredDocument, discover_article_seed_urls

logger = logging.getLogger("janmat.ingest_pipeline")


def _ingest_one(doc: DiscoveredDocument) -> dict:
    """Fetch, extract, chunk, embed, and store a single discovered document."""
    result = {"url": doc.url, "status": "skipped", "chunks": 0}
    try:
        extracted = ingest_source_document(doc.url)
        full_text = extracted["full_text"]
        if not full_text.strip():
            result["status"] = "empty"
            return result

        text_hash = db.sha256(full_text)
        existing = db.find_document_by_url(doc.url)
        if existing and existing.get("full_text_sha256") == text_hash:
            result["status"] = "unchanged"
            return result

        title = extracted["title"] or doc.title
        row = db.upsert_document(
            source=doc.source,
            kind=doc.kind,
            title=title,
            url=doc.url,
            full_text_sha256=text_hash,
            metadata=doc.metadata,
        )
        document_id = row["id"]

        if existing:
            db.delete_chunks_for_document(document_id)

        if extracted["kind_hint"] == "pdf":
            chunk_dicts = chunk_pages(extracted["pages"])
        else:
            chunk_dicts = [{"content": c, "page_number": None} for c in chunk_text(full_text)]

        if not chunk_dicts:
            result["status"] = "no_chunks"
            return result

        vectors = embed_texts([c["content"] for c in chunk_dicts])
        rows = [
            {
                "chunk_index": i,
                "content": c["content"],
                "token_count": len(c["content"].split()),
                "page_number": c.get("page_number"),
                "embedding": vec,
            }
            for i, (c, vec) in enumerate(zip(chunk_dicts, vectors))
        ]
        db.insert_chunks(document_id, rows)

        result["status"] = "ingested"
        result["chunks"] = len(rows)
        result["extra_pdf_links"] = extracted.get("pdf_links", [])
        return result

    except Exception as exc:
        logger.exception("Failed ingesting %s", doc.url)
        db.mark_document_failed(doc.url, doc.source, doc.kind, doc.title, str(exc))
        result["status"] = "failed"
        result["error"] = str(exc)
        return result


def run_ingestion() -> dict:
    started_at = datetime.now(timezone.utc).isoformat()
    run_id = db.start_ingestion_run(started_at)

    summary = {"documents_seen": 0, "ingested": 0, "unchanged": 0, "failed": 0, "results": []}

    try:
        # 1. PRS bills: bill pages + any PDFs those pages link to.
        discovery = PRSDiscovery(CONFIG["prs"])
        bill_pages = discovery.discover_bill_pages()

        queue: List[DiscoveredDocument] = list(bill_pages)

        for bill_doc in bill_pages:
            r = _ingest_one(bill_doc)
            summary["documents_seen"] += 1
            summary["results"].append(r)
            if r["status"] == "ingested":
                summary["ingested"] += 1
            elif r["status"] == "unchanged":
                summary["unchanged"] += 1
            elif r["status"] == "failed":
                summary["failed"] += 1

            for pdf_url in r.get("extra_pdf_links", []):
                pdf_doc = discovery.discover_pdfs_from_bill_page(bill_doc, [pdf_url])[0]
                pr = _ingest_one(pdf_doc)
                summary["documents_seen"] += 1
                summary["results"].append(pr)
                if pr["status"] == "ingested":
                    summary["ingested"] += 1
                elif pr["status"] == "unchanged":
                    summary["unchanged"] += 1
                elif pr["status"] == "failed":
                    summary["failed"] += 1

        # 2. Any additional article/opinion seed URLs from config.
        for article_doc in discover_article_seed_urls(CONFIG["article_seed_urls"]):
            r = _ingest_one(article_doc)
            summary["documents_seen"] += 1
            summary["results"].append(r)
            if r["status"] == "ingested":
                summary["ingested"] += 1
            elif r["status"] == "unchanged":
                summary["unchanged"] += 1
            elif r["status"] == "failed":
                summary["failed"] += 1

        db.finish_ingestion_run(run_id, datetime.now(timezone.utc).isoformat(), "success", summary)
    except Exception as exc:
        logger.exception("Ingestion run failed")
        summary["error"] = str(exc)
        db.finish_ingestion_run(run_id, datetime.now(timezone.utc).isoformat(), "failed", summary)

    return summary
