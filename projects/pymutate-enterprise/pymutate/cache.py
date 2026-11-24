"""SHA-256 content-addressable SQLite cache of mutant outcomes (``.pymutate_cache.db``).

The key covers everything that can change a mutant's verdict:

- the file path and reported line,
- the full mutated source (so any edit to the target file invalidates it),
- the exact set of covering pytest node IDs,
- a fingerprint of the test files' contents (so editing a test invalidates it).

Only definitive verdicts (KILLED / SURVIVED / TIMEOUT) are stored. The cache is
shared by worker threads, so access is serialized with a lock.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
import time
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from types import TracebackType

from pymutate.models import MutantStatus

SCHEMA_VERSION = 1
CACHEABLE_STATUSES = frozenset({MutantStatus.KILLED, MutantStatus.SURVIVED, MutantStatus.TIMEOUT})


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def tests_hash(covering_tests: Iterable[str], tests_fingerprint: str = "") -> str:
    """Order-independent hash of node IDs plus the test-suite content fingerprint."""
    payload = json.dumps({"tests": sorted(set(covering_tests)), "fingerprint": tests_fingerprint})
    return sha256_text(payload)


def fingerprint_files(paths: Iterable[Path]) -> str:
    """Stable SHA-256 over file names and contents (missing files are skipped)."""
    digest = hashlib.sha256()
    for path in sorted({p.resolve() for p in paths}):
        if not path.is_file():
            continue
        digest.update(path.as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def cache_key(rel_path: str, lineno: int, mutated_source: str, covering_tests_hash: str) -> str:
    payload = json.dumps(
        [rel_path.replace("\\", "/"), int(lineno), sha256_text(mutated_source), covering_tests_hash]
    )
    return sha256_text(payload)


@dataclass(frozen=True)
class CachedOutcome:
    key: str
    status: MutantStatus
    duration_sec: float
    mutant_id: str
    created_at: float

    @property
    def replay_status(self) -> MutantStatus:
        """How a cache hit is reported: TIMEOUT and KILLED both replay as CACHED_KILLED."""
        return MutantStatus.CACHED_KILLED if self.status.is_killed else MutantStatus.CACHED_SURVIVED


@dataclass(frozen=True)
class CacheStats:
    entries: int
    hits: int
    misses: int
    writes: int


class ResultCache:
    def __init__(self, path: Path, *, enabled: bool = True) -> None:
        self.path = path
        self.enabled = enabled
        self._lock = threading.Lock()
        self._hits = 0
        self._misses = 0
        self._writes = 0
        self._connection: sqlite3.Connection | None = None
        if enabled:
            self._connection = self._open()

    def _open(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path, check_same_thread=False, timeout=30.0)
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA synchronous=NORMAL")
        connection.execute("CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        row = connection.execute("SELECT value FROM meta WHERE key = 'schema_version'").fetchone()
        if row is None or int(row[0]) != SCHEMA_VERSION:
            connection.execute("DROP TABLE IF EXISTS results")
            connection.execute(
                "INSERT OR REPLACE INTO meta (key, value) VALUES ('schema_version', ?)",
                (str(SCHEMA_VERSION),),
            )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS results (
                key TEXT PRIMARY KEY,
                status TEXT NOT NULL,
                duration_sec REAL NOT NULL,
                mutant_id TEXT NOT NULL,
                created_at REAL NOT NULL
            )
            """
        )
        connection.commit()
        return connection

    def get(self, key: str) -> CachedOutcome | None:
        if self._connection is None:
            return None
        with self._lock:
            row = self._connection.execute(
                "SELECT key, status, duration_sec, mutant_id, created_at FROM results WHERE key = ?",
                (key,),
            ).fetchone()
            if row is None:
                self._misses += 1
                return None
            self._hits += 1
        return CachedOutcome(
            key=row[0],
            status=MutantStatus(row[1]),
            duration_sec=float(row[2]),
            mutant_id=row[3],
            created_at=float(row[4]),
        )

    def put(self, key: str, status: MutantStatus, duration_sec: float, mutant_id: str) -> bool:
        """Store a definitive verdict. Returns ``False`` (and stores nothing) for other statuses."""
        if self._connection is None or status not in CACHEABLE_STATUSES:
            return False
        with self._lock:
            self._connection.execute(
                "INSERT OR REPLACE INTO results (key, status, duration_sec, mutant_id, created_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (key, status.value, float(duration_sec), mutant_id, time.time()),
            )
            self._connection.commit()
            self._writes += 1
        return True

    def invalidate(self, key: str) -> None:
        if self._connection is None:
            return
        with self._lock:
            self._connection.execute("DELETE FROM results WHERE key = ?", (key,))
            self._connection.commit()

    def clear(self) -> None:
        if self._connection is None:
            return
        with self._lock:
            self._connection.execute("DELETE FROM results")
            self._connection.commit()

    def stats(self) -> CacheStats:
        entries = 0
        if self._connection is not None:
            with self._lock:
                entries = int(self._connection.execute("SELECT COUNT(*) FROM results").fetchone()[0])
        return CacheStats(entries=entries, hits=self._hits, misses=self._misses, writes=self._writes)

    def close(self) -> None:
        if self._connection is not None:
            with self._lock:
                self._connection.close()
                self._connection = None

    def __enter__(self) -> ResultCache:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()
