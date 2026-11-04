import argparse
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.data.db import IngestError, ingest_csvs


DEFAULT_SOURCE = Path(
    "/home/diego-maplink/Downloads/Desafio_Técnico_AI_Engineer_2026-20260616T150750Z-3-001/"
    "Desafio Técnico AI Engineer 2026/data"
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate CSV source data and build the local SQLite database.")
    parser.add_argument("--source-dir", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--db-path", type=Path, default=Path("work/app.db"))
    arguments = parser.parse_args()
    try:
        report = ingest_csvs(arguments.source_dir, arguments.db_path)
    except IngestError as error:
        parser.error(str(error))
    print(f"SQLite database ready: {report.database_path}")
    for table, count in report.rows_by_table.items():
        print(f"{table}: {count} rows")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
