"""
Wipe the database and recreate an empty schema.

    python scripts/reset_database.py

- DESTRUCTIVE: drops every table the app defines (all trainee, training,
  outcome, follow-up, wage, verification and notification data) and the
  ID sequences, so numbering starts again at TRN000001, OUT000001, ...
- Then runs the same init_db() as application startup, so the result is
  exactly what a first start of the app on an empty database creates.
- Works on the database in DATABASE_URL (.env). It prints which one and
  only continues if you type "yes".
- Tables that are not part of database/models.py are left alone.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text  # noqa: E402

from database import models  # noqa: E402,F401  (registers every table on Base)
from database.connection import ID_SEQUENCES, Base, engine, init_db  # noqa: E402


def main() -> int:
    url = engine.url
    tables = sorted(Base.metadata.tables)
    print("This will PERMANENTLY DELETE all data in:")
    print(f"    database: {url.database}")
    print(f"    host:     {url.host or '(local)'}")
    print(f"    tables:   {len(tables)} ({', '.join(tables)})")
    print(f"    sequences: {len(ID_SEQUENCES)} (public IDs restart at 1)")
    print()
    try:
        answer = input('Type "yes" to drop everything and recreate an empty schema: ')
    except (EOFError, KeyboardInterrupt):
        answer = ""
    if answer.strip() != "yes":
        print("Aborted. Nothing was changed.")
        return 1

    Base.metadata.drop_all(bind=engine)
    with engine.begin() as conn:
        for sequence in ID_SEQUENCES:
            conn.execute(text(f"DROP SEQUENCE IF EXISTS {sequence}"))
    print(f"Dropped {len(tables)} tables and {len(ID_SEQUENCES)} sequences.")

    init_db()
    print("Recreated an empty schema (same as application startup). Done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
