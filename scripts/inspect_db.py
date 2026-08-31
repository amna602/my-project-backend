import sqlite3
from pathlib import Path

db = Path(__file__).resolve().parent.parent / "mathvox.db"
c = sqlite3.connect(db)
tables = [
    r[0]
    for r in c.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    )
]
for t in tables:
    cols = [r[1] for r in c.execute(f"PRAGMA table_info({t})")]
    print(f"{t}: {cols}")
