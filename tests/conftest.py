import os, sys, tempfile
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
os.environ.setdefault("HALAH_DB_PATH", os.path.join(tempfile.mkdtemp(), "halah_test.db"))
