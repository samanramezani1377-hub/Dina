"""Apply Dina SQL migrations in lexical filename order."""
from __future__ import annotations
import os
from pathlib import Path
import psycopg

def main() -> None:
    url = os.environ["DATABASE_URL"].replace("postgresql+psycopg://", "postgresql://", 1)
    root = Path(__file__).resolve().parents[1]
    with psycopg.connect(url) as conn:
        for path in sorted((root / "database" / "migrations").glob("*.sql")):
            print(f"Applying {path.name}")
            conn.execute(path.read_text(encoding="utf-8"))
    print("All migrations applied.")

if __name__ == "__main__":
    main()
