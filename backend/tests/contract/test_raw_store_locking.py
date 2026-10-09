"""DuckDB lets one process hold its file at a time. The raw store must take turns, not hold on."""

import subprocess
import sys

import duckdb
import pytest

from context_graph.ingest.raw_store import RawStore, RawStoreError

HOLD_LOCK = "import duckdb, sys, time; con = duckdb.connect(sys.argv[1]); print('locked', flush=True); time.sleep(60)"
OPEN = "import duckdb, sys; duckdb.connect(sys.argv[1]).close()"

pytestmark = pytest.mark.contract


@pytest.fixture
def raw_db(tmp_path):
    path = tmp_path / "airbyte.duckdb"
    con = duckdb.connect(str(path))
    con.execute("create schema linear")
    con.execute("create table linear.issues (id varchar, labels json)")
    con.execute("""insert into linear.issues values ('u-1', '["bug"]')""")
    con.close()
    return path


def test_reads_release_the_file_for_other_processes(raw_db):
    assert RawStore(raw_db, raw_db.parent / "airbyte").read("linear", ("issues", "comments")) == {"issues": [{"id": "u-1", "labels": ["bug"]}], "comments": []}
    other_process = subprocess.run([sys.executable, "-c", OPEN, str(raw_db)], capture_output=True, text=True, timeout=60)
    assert other_process.returncode == 0, other_process.stderr


def test_a_file_locked_by_another_process_raises_a_clear_error(raw_db):
    holder = subprocess.Popen([sys.executable, "-c", HOLD_LOCK, str(raw_db)], stdout=subprocess.PIPE, text=True)
    try:
        assert holder.stdout.readline().strip() == "locked"
        with pytest.raises(RawStoreError, match="Could not read airbyte.duckdb"):
            RawStore(raw_db, raw_db.parent / "airbyte").read("linear", ("issues",))
    finally:
        holder.kill()
        holder.wait()
