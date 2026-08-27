"""Rebuildable structured and SQLite FTS5 indexes for canonical knowledge packs."""

from __future__ import annotations

import json
import os
from pathlib import Path
import re
import sqlite3
import tempfile
from dataclasses import dataclass
from typing import Iterable

from .canonical import KnowledgePack, KnowledgePackIntegrityError, KnowledgeRecord, canonical_json
from .models import KnowledgeType


INDEX_SCHEMA_VERSION = "i8-1"
_TOKEN = re.compile(r"[A-Za-z0-9_:.+-]+")


class KnowledgeIndexError(ValueError):
    """Raised when a derived index cannot be trusted or queried."""


@dataclass(frozen=True, slots=True)
class KnowledgeIndexMetadata:
    schema_version: str
    pack_identity: str
    record_count: int


class KnowledgePackIndex:
    """Non-authoritative index whose results are resolved through canonical records."""

    def __init__(self, pack: KnowledgePack, path: str | os.PathLike[str], connection: sqlite3.Connection) -> None:
        self.pack = pack
        self.path = Path(path)
        self._connection = connection

    @classmethod
    def build(cls, pack: KnowledgePack, path: str | os.PathLike[str]) -> "KnowledgePackIndex":
        try:
            pack.assert_servable()
        except KnowledgePackIntegrityError as exc:
            raise KnowledgeIndexError(str(exc)) from exc
        destination = Path(path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(prefix=f".{destination.name}.", suffix=".tmp", dir=destination.parent)
        os.close(descriptor)
        temporary = Path(temporary_name)
        try:
            connection = sqlite3.connect(str(temporary))
            try:
                cls._create_schema(connection)
                cls._insert_pack(connection, pack)
                connection.commit()
                cls._validate_database(connection, pack)
            finally:
                connection.close()
            os.replace(temporary, destination)
        except Exception:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass
            raise
        return cls.open(pack, destination)

    @classmethod
    def open(cls, pack: KnowledgePack, path: str | os.PathLike[str]) -> "KnowledgePackIndex":
        pack.assert_servable()
        database = Path(path)
        if not database.exists():
            raise KnowledgeIndexError("index database is missing")
        try:
            connection = sqlite3.connect(str(database))
            cls._validate_database(connection, pack)
        except (sqlite3.Error, KnowledgeIndexError) as exc:
            try:
                connection.close()
            except UnboundLocalError:
                pass
            raise KnowledgeIndexError(str(exc)) from exc
        return cls(pack, database, connection)

    @staticmethod
    def fts5_available() -> bool:
        connection = sqlite3.connect(":memory:")
        try:
            connection.execute("CREATE VIRTUAL TABLE probe USING fts5(value)")
            return True
        except sqlite3.Error:
            return False
        finally:
            connection.close()

    @property
    def metadata(self) -> KnowledgeIndexMetadata:
        values = dict(self._connection.execute("SELECT key, value FROM index_meta"))
        return KnowledgeIndexMetadata(values["schema_version"], values["pack_identity"], int(values["record_count"]))

    def lookup_record(self, record_id: str) -> KnowledgeRecord | None:
        row = self._connection.execute("SELECT record_id FROM records WHERE record_id = ?", (record_id,)).fetchone()
        if row is None:
            return None
        return self._canonical_record(row[0])

    def lookup_by_type(self, kind: KnowledgeType | str) -> tuple[KnowledgeRecord, ...]:
        value = kind.value if isinstance(kind, KnowledgeType) else str(kind)
        return self._records_from_query("SELECT record_id FROM records WHERE kind = ? ORDER BY record_id", (value,))

    def lookup_by_capability(self, capability: str) -> tuple[KnowledgeRecord, ...]:
        return self._records_from_query("SELECT record_id FROM records WHERE capability = ? ORDER BY record_id", (capability,))

    def lookup_by_symbol(self, symbol: str) -> tuple[KnowledgeRecord, ...]:
        return self._records_from_query("SELECT record_id FROM records WHERE symbols LIKE ? ESCAPE '\\' ORDER BY record_id", (f"%{self._like_escape(symbol)}%",))

    def lookup_by_api(self, api_name: str) -> tuple[KnowledgeRecord, ...]:
        return self._records_from_query("SELECT record_id FROM records WHERE api_names LIKE ? ESCAPE '\\' ORDER BY record_id", (f"%{self._like_escape(api_name)}%",))

    def lexical_search(self, query: str, limit: int = 10) -> tuple[KnowledgeRecord, ...]:
        if limit <= 0:
            return ()
        tokens = _TOKEN.findall(query)
        if not tokens:
            return ()
        fts_query = " AND ".join('"' + token.replace('"', '""') + '"' for token in tokens)
        rows = self._connection.execute(
            "SELECT record_id FROM records_fts WHERE records_fts MATCH ? ORDER BY record_id LIMIT ?",
            (fts_query, int(limit)),
        ).fetchall()
        return tuple(self._canonical_record(row[0]) for row in rows)

    def verify(self) -> bool:
        try:
            self._validate_database(self._connection, self.pack)
            return True
        except (sqlite3.Error, KnowledgeIndexError):
            return False

    def delete(self) -> None:
        self._connection.close()
        self.path.unlink(missing_ok=True)

    def close(self) -> None:
        self._connection.close()

    def _canonical_record(self, record_id: str) -> KnowledgeRecord:
        for record in self.pack.records:
            if record.record_id == record_id:
                return record
        raise KnowledgeIndexError(f"index references missing canonical record: {record_id}")

    def _records_from_query(self, sql: str, parameters: Iterable[object]) -> tuple[KnowledgeRecord, ...]:
        rows = self._connection.execute(sql, tuple(parameters)).fetchall()
        return tuple(self._canonical_record(row[0]) for row in rows)

    @staticmethod
    def _create_schema(connection: sqlite3.Connection) -> None:
        if not KnowledgePackIndex.fts5_available():
            raise KnowledgeIndexError("SQLite FTS5 is unavailable")
        connection.executescript(
            """
            CREATE TABLE index_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE records (
                record_id TEXT PRIMARY KEY,
                record_identity TEXT NOT NULL UNIQUE,
                kind TEXT NOT NULL,
                capability TEXT,
                symbols TEXT NOT NULL,
                api_names TEXT NOT NULL,
                source_id TEXT NOT NULL,
                authority TEXT NOT NULL,
                minecraft_version TEXT,
                loader_version TEXT,
                mappings_version TEXT,
                fabric_api_version TEXT
            );
            CREATE VIRTUAL TABLE records_fts USING fts5(record_id UNINDEXED, title, summary, symbols, api_names, capability, content);
            """
        )

    @staticmethod
    def _insert_pack(connection: sqlite3.Connection, pack: KnowledgePack) -> None:
        connection.executemany(
            "INSERT INTO index_meta(key, value) VALUES (?, ?)",
            (("schema_version", INDEX_SCHEMA_VERSION), ("pack_identity", pack.manifest.pack_id or ""), ("record_count", str(len(pack.records)))),
        )
        for record in sorted(pack.records, key=lambda item: item.record_id):
            content = record.content if isinstance(record.content, dict) else {"content": record.content}
            title = str(content.get("title", content.get("class", content.get("qualified_name", record.record_id))))
            summary = str(content.get("summary", content.get("text", content.get("description", ""))))
            symbols = " ".join(str(item) for item in record.related_symbols) + " " + str(content.get("qualified_name", content.get("key", "")))
            api_names = str(content.get("module", content.get("related_api", "")))
            source_id = record.provenance.source_id
            env = record.environment
            connection.execute(
                "INSERT INTO records VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (record.record_id, record.identity(), record.kind.value, record.capability, symbols, api_names,
                 source_id, record.authority.value, env.minecraft_version, env.loader_version,
                 env.mappings_version, env.fabric_api_version),
            )
            connection.execute(
                "INSERT INTO records_fts(record_id, title, summary, symbols, api_names, capability, content) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (record.record_id, title, summary, symbols, api_names, record.capability or "", canonical_json(content)),
            )

    @staticmethod
    def _validate_database(connection: sqlite3.Connection, pack: KnowledgePack) -> None:
        try:
            tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type IN ('table', 'shadow')")}
            required = {"index_meta", "records", "records_fts"}
            if not required.issubset(tables):
                raise KnowledgeIndexError("index schema is incomplete")
            values = dict(connection.execute("SELECT key, value FROM index_meta"))
            if values.get("schema_version") != INDEX_SCHEMA_VERSION:
                raise KnowledgeIndexError("index schema version mismatch")
            if values.get("pack_identity") != pack.manifest.pack_id:
                raise KnowledgeIndexError("index pack identity mismatch")
            if int(values.get("record_count", "-1")) != len(pack.records):
                raise KnowledgeIndexError("index record count mismatch")
            indexed = {row[0]: row[1] for row in connection.execute("SELECT record_id, record_identity FROM records")}
            expected = {record.record_id: record.identity() for record in pack.records}
            if indexed != expected:
                raise KnowledgeIndexError("index canonical record identities mismatch")
        except (sqlite3.Error, KeyError, TypeError, ValueError) as exc:
            raise KnowledgeIndexError(f"invalid index database: {exc}") from exc

    @staticmethod
    def _like_escape(value: str) -> str:
        return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
