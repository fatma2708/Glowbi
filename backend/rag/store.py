"""Knowledge store: SQLite for chunks + hybrid retrieval (BM25 keywords + optional semantic embeddings).

No external vector DB needed — fine up to ~100k chunks. Swap for Chroma/Qdrant/pgvector later if it grows.
"""
import hashlib
import json
import re
import sqlite3
import threading
import time

import numpy as np
from rank_bm25 import BM25Okapi

from backend import config

_TOKEN = re.compile(r"[a-zA-Zà-ÿ0-9]+")
STOPWORDS = set("""a an the and or of to in on for with is are be it this that my your i you me do does how what
which can should use using le la les de des du et ou un une est pour avec mon ma mes je tu quoi comment""".split())


def tokenize(text: str) -> list[str]:
    return [t for t in _TOKEN.findall(text.lower()) if t not in STOPWORDS and len(t) > 1]


class Embedder:
    """Lazy-loaded sentence-transformers model. Returns None if unavailable -> BM25-only mode."""

    def __init__(self):
        self.model = None
        self.tried = False
        self.load_lock = threading.Lock()

    def _load(self):
        if config.USE_EMBEDDINGS == "false":
            return
        try:
            from sentence_transformers import SentenceTransformer
            self.model = SentenceTransformer(config.EMBED_MODEL)
            print(f"[store] semantic embeddings ON ({config.EMBED_MODEL})")
        except Exception as e:  # not installed or no network
            print(f"[store] embeddings unavailable ({e.__class__.__name__}) -> keyword search only")

    def encode(self, texts: list[str]):
        if not self.tried:
            with self.load_lock:  # other threads must wait: chunks stored mid-load would get no embedding
                if not self.tried:
                    self._load()
                    self.tried = True
        if self.model is None:
            return None
        return self.model.encode(texts, normalize_embeddings=True, show_progress_bar=False).astype(np.float32)


class KnowledgeStore:
    def __init__(self, db_path=config.DB_PATH):
        self.db_path = db_path
        self.lock = threading.Lock()
        self.embedder = Embedder()
        self._index = None  # cached (ids, bm25, matrix)
        self._products = None  # cached product rows
        with self._conn() as c:
            c.executescript("""
            CREATE TABLE IF NOT EXISTS documents(
                id TEXT PRIMARY KEY, url TEXT, title TEXT, source TEXT,
                category TEXT, fetched_at REAL);
            CREATE TABLE IF NOT EXISTS chunks(
                id INTEGER PRIMARY KEY AUTOINCREMENT, doc_id TEXT, text TEXT,
                embedding BLOB, FOREIGN KEY(doc_id) REFERENCES documents(id));
            CREATE INDEX IF NOT EXISTS idx_chunks_doc ON chunks(doc_id);
            """)
            if "meta" not in [r[1] for r in c.execute("PRAGMA table_info(documents)")]:
                c.execute("ALTER TABLE documents ADD COLUMN meta TEXT")  # {brand, product_url, image_url, price, source}

    def _conn(self):
        return sqlite3.connect(self.db_path, check_same_thread=False)

    @staticmethod
    def doc_id(url: str) -> str:
        return hashlib.sha1(url.encode()).hexdigest()[:16]

    def has(self, url: str) -> bool:
        with self._conn() as c:
            return c.execute("SELECT 1 FROM documents WHERE id=?", (self.doc_id(url),)).fetchone() is not None

    def add_document(self, url: str, title: str, source: str, category: str, chunks: list[str],
                     meta: dict | None = None) -> int:
        if not chunks or self.has(url):
            return 0
        embs = self.embedder.encode(chunks)
        did = self.doc_id(url)
        with self.lock, self._conn() as c:
            c.execute("INSERT INTO documents(id, url, title, source, category, fetched_at, meta) VALUES(?,?,?,?,?,?,?)",
                      (did, url, title, source, category, time.time(), json.dumps(meta) if meta else None))
            c.executemany(
                "INSERT INTO chunks(doc_id, text, embedding) VALUES(?,?,?)",
                [(did, t, embs[i].tobytes() if embs is not None else None) for i, t in enumerate(chunks)],
            )
            self._index = None
            self._products = None
        return len(chunks)

    def set_meta(self, url: str, meta: dict):
        with self.lock, self._conn() as c:
            c.execute("UPDATE documents SET meta=? WHERE id=?", (json.dumps(meta), self.doc_id(url)))

    def _product_rows(self) -> list[dict]:
        if self._products is None:
            with self._conn() as c:
                rows = c.execute("""SELECT d.url, d.title, d.source, d.category, d.meta, ch.text, ch.embedding
                                    FROM documents d JOIN chunks ch ON ch.doc_id = d.id
                                    WHERE d.category IN ('products', 'makeup') GROUP BY d.id""").fetchall()
            self._products = [{"url": r[0], "title": r[1], "source": r[2], "category": r[3], "meta": json.loads(r[4] or "{}"),
                               "text": r[5], "embedding": np.frombuffer(r[6], dtype=np.float32) if r[6] else None} for r in rows]
        return self._products

    def product_brands(self) -> set[str]:
        return {r["meta"]["brand"].split(",")[0].strip() for r in self._product_rows() if r["meta"].get("brand")}

    def products(self, query: str, keep, k: int = 6) -> list[dict]:
        """Hybrid search over products only: filters first, so a narrow filter can't come back empty by accident."""
        rows = [r for r in self._product_rows() if keep(r)]
        if not rows:
            return []
        scores = BM25Okapi([tokenize(r["title"] + " " + r["text"]) or ["_"] for r in rows]).get_scores(tokenize(query) or ["_"])
        rankings = [np.argsort(-scores)]
        q = self.embedder.encode([query])
        if q is not None and all(r["embedding"] is not None for r in rows):
            rankings.append(np.argsort(-(np.vstack([r["embedding"] for r in rows]) @ q[0])))
        fused: dict[int, float] = {}
        for ranking in rankings:
            for rank, idx in enumerate(ranking):
                fused[int(idx)] = fused.get(int(idx), 0) + 1 / (60 + rank)
        best = sorted(fused, key=fused.get, reverse=True)[:k]
        return [{key: value for key, value in rows[i].items() if key != "embedding"} for i in best]

    def _build_index(self):
        with self._conn() as c:
            rows = c.execute("SELECT id, text, embedding FROM chunks").fetchall()
        if not rows:
            return None
        ids = [r[0] for r in rows]
        bm25 = BM25Okapi([tokenize(r[1]) or ["_"] for r in rows])
        matrix = None
        if all(r[2] is not None for r in rows):
            matrix = np.vstack([np.frombuffer(r[2], dtype=np.float32) for r in rows])
        self._index = (ids, bm25, matrix)
        return self._index

    def search(self, query: str, k: int = 5, category: str | None = None) -> list[dict]:
        index = self._index or self._build_index()
        if index is None:
            return []
        ids, bm25, matrix = index
        rankings = []

        kw_scores = bm25.get_scores(tokenize(query) or ["_"])
        rankings.append(np.argsort(-kw_scores)[:50])

        if matrix is not None:
            q = self.embedder.encode([query])
            if q is not None:
                rankings.append(np.argsort(-(matrix @ q[0]))[:50])

        # Reciprocal Rank Fusion
        fused: dict[int, float] = {}
        for ranking in rankings:
            for rank, idx in enumerate(ranking):
                fused[idx] = fused.get(idx, 0) + 1 / (60 + rank)
        if matrix is None:  # drop zero-score keyword hits
            fused = {i: s for i, s in fused.items() if kw_scores[i] > 0}
        best = sorted(fused, key=fused.get, reverse=True)

        results, seen_docs = [], {}
        with self._conn() as c:
            for idx in best:
                row = c.execute(
                    """SELECT ch.text, d.url, d.title, d.source, d.category FROM chunks ch
                       JOIN documents d ON d.id = ch.doc_id WHERE ch.id=?""", (ids[idx],)).fetchone()
                if not row or (category and row[4] != category):
                    continue
                if seen_docs.get(row[1], 0) >= 2:  # max 2 chunks per article -> diverse sources
                    continue
                seen_docs[row[1]] = seen_docs.get(row[1], 0) + 1
                results.append({"text": row[0], "url": row[1], "title": row[2], "source": row[3],
                                "category": row[4], "score": round(fused[idx], 4)})
                if len(results) >= k:
                    break
        return results

    def stats(self) -> dict:
        with self._conn() as c:
            docs = c.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
            chunks = c.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
            cats = dict(c.execute("SELECT category, COUNT(*) FROM documents GROUP BY category").fetchall())
            last = c.execute("SELECT MAX(fetched_at) FROM documents").fetchone()[0]
        return {"documents": docs, "chunks": chunks, "by_category": cats, "last_fed": last}


store = KnowledgeStore()
