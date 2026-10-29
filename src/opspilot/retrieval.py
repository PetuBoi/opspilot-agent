"""Persistent, bounded lexical retrieval with source-preserving content IDs."""

import hashlib
import re
from pathlib import Path

from opspilot.domain import Evidence
from opspilot.store import Store


class KnowledgeBase:
    def __init__(self, store: Store):
        self.store = store
        with store.connect() as db:
            db.execute("""CREATE VIRTUAL TABLE IF NOT EXISTS chunks USING fts5(
                document_id UNINDEXED, chunk_id UNINDEXED, source UNINDEXED,
                service UNINDEXED, text, tokenize='unicode61')""")

    def index(self, directory: Path, chunk_size: int = 900) -> dict:
        if not directory.is_dir():
            raise ValueError("Knowledge directory does not exist; run seed-demo first")
        if chunk_size < 100:
            raise ValueError("Chunk size must be at least 100 characters")
        chunks, seen = [], set()
        for source in sorted(directory.rglob("*")):
            if source.suffix.lower() not in {".md", ".txt"} or source.is_symlink():
                continue
            text = source.read_text(encoding="utf-8")
            digest = hashlib.sha256(text.encode()).hexdigest()
            if digest in seen:
                continue
            seen.add(digest)
            name = source.relative_to(directory).as_posix()
            match = re.search(r"^Document-ID:\s*(\S+)", text, re.MULTILINE)
            doc_id = match[1] if match else hashlib.sha256(name.encode()).hexdigest()[:16]
            match = re.search(r"^Service:\s*(\S+)", text, re.MULTILINE)
            service = match[1] if match else "unknown"
            for offset in range(0, len(text), chunk_size):
                part = text[offset : offset + chunk_size]
                chunk_id = hashlib.sha256(f"{doc_id}:{offset}:{part}".encode()).hexdigest()[:24]
                chunks.append((doc_id, chunk_id, name, service, part))
        # Atomic full replacement makes reindexing include deletions, with no stale rows.
        with self.store.connect() as db:
            db.execute("DELETE FROM chunks")
            db.executemany("INSERT INTO chunks VALUES(?,?,?,?,?)", chunks)
        return {"documents": len(seen), "chunks": len(chunks)}

    def search(self, query: str, top_k: int = 5) -> list[Evidence]:
        if not 1 <= top_k <= 20:
            raise ValueError("top_k must be between 1 and 20")
        tokens = list(dict.fromkeys(re.findall(r"\w+", query.lower(), flags=re.UNICODE)))[:40]
        if not tokens:
            return []
        # Only tokens enter FTS MATCH. Caller-supplied operators and SQL are never interpreted.
        expression = " OR ".join(f'"{token}"' for token in tokens)
        with self.store.connect() as db:
            rows = db.execute(
                "SELECT document_id,chunk_id,source,service,text,bm25(chunks) AS rank "
                "FROM chunks WHERE chunks MATCH ? ORDER BY rank,chunk_id LIMIT ?",
                (expression, top_k * 8),
            ).fetchall()
        found, documents = [], set()
        for row in rows:
            if row[0] in documents:
                continue
            documents.add(row[0])
            found.append(
                Evidence(
                    document_id=row[0],
                    chunk_id=row[1],
                    source=row[2],
                    text=row[4],
                    score=-row[5],
                    metadata={"service": row[3], "trust": "untrusted"},
                )
            )
            if len(found) == top_k:
                break
        return found

    def valid_citations(self, chunk_ids: list[str]) -> bool:
        with self.store.connect() as db:
            return all(
                db.execute("SELECT 1 FROM chunks WHERE chunk_id=?", (cid,)).fetchone() is not None
                for cid in chunk_ids
            )
