"""Notes de setup (F26) : notes liées à une voiture et une piste, et éventuellement à une session.

Stockées dans la même base SQLite que l'historique (table `notes`), lues et écrites par l'API `/api/notes`.
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from .history import HistoryStore

SCHEMA = """
CREATE TABLE IF NOT EXISTS notes (
    id INTEGER PRIMARY KEY,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    car TEXT NOT NULL DEFAULT '',
    track TEXT NOT NULL DEFAULT '',
    session_id INTEGER REFERENCES sessions(id) ON DELETE SET NULL,
    title TEXT NOT NULL DEFAULT '',
    text TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS notes_car_track ON notes(car, track);
"""


class NoteIn(BaseModel):
    car: str = Field("", max_length=200)
    track: str = Field("", max_length=200)
    session_id: int | None = None
    title: str = Field("", max_length=200)
    text: str = Field("", max_length=20000)


class NoteStore:
    def __init__(self, history: HistoryStore) -> None:
        self.h = history
        with self.h._lock:
            self.h.db.executescript(SCHEMA)
            self.h.db.commit()

    def list(self, car: str | None = None, track: str | None = None, session_id: int | None = None) -> list[dict]:
        where, args = [], []
        for col, val in (("car", car), ("track", track), ("session_id", session_id)):
            if val is not None:
                where.append(f"{col} = ?")
                args.append(val)
        sql = "SELECT * FROM notes" + (" WHERE " + " AND ".join(where) if where else "") + " ORDER BY updated_at DESC, id DESC"
        with self.h._lock:
            return [dict(r) for r in self.h.db.execute(sql, args).fetchall()]

    def get(self, note_id: int) -> dict | None:
        with self.h._lock:
            row = self.h.db.execute("SELECT * FROM notes WHERE id = ?", (note_id,)).fetchone()
        return dict(row) if row else None

    def add(self, note: NoteIn) -> dict:
        now = datetime.now().astimezone().isoformat(timespec="seconds")
        with self.h._lock:
            cur = self.h.db.execute(
                "INSERT INTO notes (created_at, updated_at, car, track, session_id, title, text) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (now, now, note.car, note.track, note.session_id, note.title, note.text),
            )
            self.h.db.commit()
        return self.get(int(cur.lastrowid))

    def update(self, note_id: int, note: NoteIn) -> dict | None:
        now = datetime.now().astimezone().isoformat(timespec="seconds")
        with self.h._lock:
            cur = self.h.db.execute(
                "UPDATE notes SET updated_at = ?, car = ?, track = ?, session_id = ?, title = ?, text = ? WHERE id = ?",
                (now, note.car, note.track, note.session_id, note.title, note.text, note_id),
            )
            self.h.db.commit()
        return self.get(note_id) if cur.rowcount else None

    def delete(self, note_id: int) -> bool:
        with self.h._lock:
            cur = self.h.db.execute("DELETE FROM notes WHERE id = ?", (note_id,))
            self.h.db.commit()
        return cur.rowcount > 0


def make_notes_router(store: NoteStore) -> APIRouter:
    router = APIRouter(prefix="/api/notes")

    @router.get("")
    def list_notes(car: str | None = None, track: str | None = None, session_id: int | None = None) -> list[dict]:
        return store.list(car, track, session_id)

    @router.post("")
    def add(note: NoteIn) -> dict:
        if note.session_id is not None and store.h.session(note.session_id) is None:
            raise HTTPException(404, "session inconnue")
        return store.add(note)

    @router.put("/{note_id}")
    def update(note_id: int, note: NoteIn) -> dict:
        out = store.update(note_id, note)
        if out is None:
            raise HTTPException(404, "note inconnue")
        return out

    @router.delete("/{note_id}")
    def delete(note_id: int) -> dict:
        if not store.delete(note_id):
            raise HTTPException(404, "note inconnue")
        return {"deleted": note_id}

    return router
