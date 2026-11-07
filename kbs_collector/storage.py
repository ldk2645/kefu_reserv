from contextlib import contextmanager
import json
from pathlib import Path
import sqlite3
from uuid import uuid4

from .extractor import Capture
from .normalizer import digest, markdown, now
from .policy import CollectorError

SCHEMA = """
PRAGMA journal_mode=WAL;
CREATE TABLE IF NOT EXISTS captures (
 id TEXT PRIMARY KEY, product_key TEXT NOT NULL, source_url TEXT NOT NULL,
 content_hash TEXT NOT NULL, captured_at TEXT NOT NULL, payload TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS tasks (
 id TEXT PRIMARY KEY, state TEXT NOT NULL, attempts INTEGER NOT NULL DEFAULT 0,
 error_code TEXT NOT NULL DEFAULT '', capture_id TEXT NOT NULL DEFAULT '',
 updated_at TEXT NOT NULL, spec TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS events (
 id INTEGER PRIMARY KEY, task_id TEXT NOT NULL, outcome TEXT NOT NULL,
 error_code TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL
);
"""


def atomic_write(path, text):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + "." + uuid4().hex + ".tmp")
    try:
        temporary.write_text(text, encoding="utf-8")
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def product_key(product):
    return digest([product.brand,product.model] if product.model else [product.brand,"unknown_model",product.name])


class Storage:
    def __init__(self, root):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.path = self.root / "index.sqlite3"
        with self.connect() as conn:
            conn.executescript(SCHEMA)

    @contextmanager
    def connect(self):
        conn = sqlite3.connect(self.path, timeout=15)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except BaseException:
            conn.rollback()
            raise
        finally:
            conn.close()

    def recover(self):
        # Called once by the single owning GUI process on startup.
        with self.connect() as conn:
            interrupted = conn.execute("SELECT id FROM tasks WHERE state='running'").fetchall()
            for row in interrupted:
                conn.execute("INSERT INTO events(task_id,outcome,error_code,created_at) VALUES (?,?,?,?)",
                             (row["id"], "failed", "INTERRUPTED", now()))
            conn.execute("UPDATE tasks SET state='pending', error_code='INTERRUPTED' WHERE state='running'")
        self.export()

    def begin(self, spec):
        task_id = digest(spec)
        with self.connect() as conn:
            conn.execute("""INSERT INTO tasks(id,state,attempts,updated_at,spec) VALUES (?,'running',1,?,?)
              ON CONFLICT(id) DO UPDATE SET state='running',attempts=attempts+1,error_code='',updated_at=excluded.updated_at""",
                         (task_id, now(), json.dumps(spec, ensure_ascii=False)))
        return task_id

    def fail(self, task_id, code):
        with self.connect() as conn:
            conn.execute("UPDATE tasks SET state='failed',error_code=?,updated_at=? WHERE id=?", (code,now(),task_id))
            conn.execute("INSERT INTO events(task_id,outcome,error_code,created_at) VALUES (?,?,?,?)", (task_id,"failed",code,now()))
        self.export()

    def save(self, capture, task_id):
        key = product_key(capture.product)
        with self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            # An exact page/name/category match may gain an explicit model after
            # a DOM correction. Keep the same pilot identity and original payloads.
            # Never merge two different nonempty models or similar product names.
            lineage = conn.execute("""SELECT product_key,
                json_extract(payload,'$.product.model') model FROM captures
                WHERE json_extract(payload,'$.frame_url')=?
                  AND json_extract(payload,'$.product.name')=?
                  AND json_extract(payload,'$.product.category')=?""",
                (capture.frame_url,capture.product.name,capture.product.category)).fetchall()
            lineage_keys = {r['product_key'] for r in lineage}
            if len(lineage_keys) == 1 and all(not r['model'] or r['model'] == capture.product.model for r in lineage):
                key = next(iter(lineage_keys))
            existing = conn.execute("SELECT id FROM captures WHERE id=?", (capture.id,)).fetchone()
            if existing:
                outcome = "skipped"
            else:
                keys = {r[0] for r in conn.execute("SELECT DISTINCT product_key FROM captures")}
                if key not in keys and len(keys) >= 5:
                    raise CollectorError("PILOT_PRODUCT_LIMIT")
                if conn.execute("SELECT COUNT(*) FROM captures").fetchone()[0] >= 100:
                    raise CollectorError("PILOT_PAGE_LIMIT")
                previous = conn.execute("SELECT id,content_hash FROM captures WHERE product_key=?", (key,)).fetchall()
                if previous:
                    capture.issues = sorted(set(capture.issues + ["RELATED_OR_CHANGED_CONTENT_REVIEW_CONFLICTS"]))
                conn.execute("INSERT INTO captures VALUES (?,?,?,?,?,?)", (capture.id, key,capture.source_url,
                    capture.content_hash,capture.captured_at,capture.model_dump_json()))
                outcome = "success"
            conn.execute("UPDATE tasks SET state='complete',capture_id=?,error_code='',updated_at=? WHERE id=?", (capture.id,now(),task_id))
            conn.execute("INSERT INTO events(task_id,outcome,created_at) VALUES (?,?,?)", (task_id,outcome,now()))
        self.export()
        return outcome

    def captures(self):
        with self.connect() as conn:
            return [Capture.model_validate_json(r[0]) for r in conn.execute("SELECT payload FROM captures ORDER BY captured_at,id")]

    def pending_tasks(self):
        with self.connect() as conn:
            return [dict(r) for r in conn.execute("SELECT * FROM tasks WHERE state != 'complete' ORDER BY updated_at")]

    def summaries(self):
        with self.connect() as conn:
            return [dict(r) for r in conn.execute("""SELECT id,
                json_extract(payload,'$.title') title, json_extract(payload,'$.product.model') model
                FROM captures ORDER BY captured_at,id""")]

    def export(self):
        captures = self.captures()
        with self.connect() as conn:
            stored_keys = dict(conn.execute('SELECT id,product_key FROM captures').fetchall())
        products, articles, faq, videos, reviews = {}, [], [], [], []
        for c in captures:
            key = stored_keys[c.id]
            if key not in products or c.product.model or not products[key]['model']:
                products[key] = {**c.product.model_dump(), "id":key,"status":"pending_review"}
            articles.append(c.model_dump())
            common = {"article_id":c.id,"source_url":c.source_url,"original_model":c.product.model,"captured_at":c.captured_at}
            faq.extend({**f,**common} for f in c.faq)
            videos.extend({**v,**common} for v in c.videos)
            reviews.append({**common,"status":"pending_review","reasons":["HUMAN_REVIEW_REQUIRED"]+c.issues})
            atomic_write(self.root / "markdown" / (c.id + ".md"), markdown(c))
        hashes = {}
        for name, rows in [("products",list(products.values())),("articles",articles),("faq",faq),("videos",videos),("review_queue",reviews)]:
            value = "".join(json.dumps(row,ensure_ascii=False)+"\n" for row in rows)
            atomic_write(self.root/(name+".jsonl"),value)
            hashes[name+".jsonl"] = digest(value)
        with self.connect() as conn:
            counts = {r[0]:r[1] for r in conn.execute("SELECT outcome,COUNT(*) FROM events GROUP BY outcome")}
            tasks = [dict(r) for r in conn.execute("SELECT id,state,attempts,error_code,capture_id,updated_at FROM tasks")]
        report = {"version":1,"generated_at":now(),"source_of_truth":"index.sqlite3",
                  "success":counts.get("success",0),"failed":counts.get("failed",0),"skipped":counts.get("skipped",0),
                  "pending_review":len(reviews),"products":len(products),"tasks":tasks,"export_hashes":hashes,
                  "real_site_verified":False,"verification_note":"需人工核对真实站点的试采集结果；程序测试不代表真实页面验收"}
        # Manifest is written last. A crash is repaired by rebuilding exports from SQLite.
        atomic_write(self.root/"crawl_manifest.json",json.dumps(report,ensure_ascii=False,indent=2))
        return report
