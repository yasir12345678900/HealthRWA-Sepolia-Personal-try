"""SQLite persistence for HALAH (consents + audit). Path: env HALAH_DB_PATH or data/halah.db."""
import json, os, sqlite3, threading
_LOCK = threading.Lock()
def db_path():
    return os.environ.get("HALAH_DB_PATH", os.path.join("data", "halah.db"))
def _conn():
    p = db_path(); d = os.path.dirname(p)
    if d: os.makedirs(d, exist_ok=True)
    c = sqlite3.connect(p, check_same_thread=False)
    c.execute("CREATE TABLE IF NOT EXISTS consents (consent_id TEXT PRIMARY KEY, body TEXT NOT NULL)")
    c.execute("CREATE TABLE IF NOT EXISTS audit (event_id TEXT PRIMARY KEY, ts TEXT, body TEXT NOT NULL)")
    return c
def put(table, key_col, key, obj):
    with _LOCK, _conn() as c:
        if table == "audit":
            c.execute("INSERT OR REPLACE INTO audit (event_id, ts, body) VALUES (?,?,?)", (key, obj.get("timestamp", ""), json.dumps(obj, default=str)))
        else:
            c.execute(f"INSERT OR REPLACE INTO {table} ({key_col}, body) VALUES (?,?)", (key, json.dumps(obj, default=str)))
def all_rows(table, order_col=None):
    with _LOCK, _conn() as c:
        q = f"SELECT body FROM {table}" + (f" ORDER BY {order_col}" if order_col else "")
        return [json.loads(r[0]) for r in c.execute(q)]
