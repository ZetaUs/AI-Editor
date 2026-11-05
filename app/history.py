import json
import os
import shutil
import time
from pathlib import Path


HISTORY_DIR = Path(__file__).resolve().parent.parent / "History"
MAX_HISTORY = 100


class HistoryEntry:
    def __init__(self, action: str, path: str, content_before: str | None, content_after: str | None):
        self.action = action
        self.path = path
        self.content_before = content_before
        self.content_after = content_after
        self.timestamp = time.time()

    def to_dict(self) -> dict:
        return {
            "action": self.action,
            "path": self.path,
            "content_before": self.content_before,
            "content_after": self.content_after,
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "HistoryEntry":
        e = cls(d["action"], d["path"], d["content_before"], d["content_after"])
        e.timestamp = d["timestamp"]
        return e


class HistoryManager:
    def __init__(self, base_dir: Path):
        self.base_dir = base_dir
        self.history_dir = HISTORY_DIR
        self.history_dir.mkdir(exist_ok=True)
        self._entries: list[HistoryEntry] = []
        self._load()

    def _load(self):
        self._entries = []
        for f in sorted(self.history_dir.glob("*.json")):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                for item in data:
                    self._entries.append(HistoryEntry.from_dict(item))
            except Exception:
                pass

    def _save(self):
        chunks: list[HistoryEntry] = []
        for entry in self._entries:
            chunks.append(entry)
            if len(chunks) >= 10:
                self._write_chunk(chunks)
                chunks = []
        if chunks:
            self._write_chunk(chunks)

        all_files = sorted(self.history_dir.glob("*.json"))
        total = len(self._entries)
        if total > MAX_HISTORY:
            excess = total - MAX_HISTORY
            self._entries = self._entries[excess:]
            self._rebuild_files()

    def _write_chunk(self, entries: list[HistoryEntry]):
        ts = int(time.time() * 1000)
        f = self.history_dir / f"{ts}_{len(entries)}.json"
        f.write_text(json.dumps([e.to_dict() for e in entries], ensure_ascii=False, indent=2), encoding="utf-8")

    def _rebuild_files(self):
        for f in self.history_dir.glob("*.json"):
            f.unlink()
        self._save()

    def record(self, action: str, path: str, content_before: str | None, content_after: str | None):
        self._entries.append(HistoryEntry(action, path, content_before, content_after))
        self._save()

    def record_create(self, path: str):
        self.record("create", path, None, None)

    def record_delete(self, path: str, content: str | None):
        self.record("delete", path, content, None)

    def record_modify(self, path: str, before: str, after: str):
        self.record("modify", path, before, after)

    def record_rename(self, old_path: str, new_path: str):
        self.record("rename", new_path, old_path, new_path)

    def undo(self) -> HistoryEntry | None:
        if not self._entries:
            return None

        entry = self._entries.pop()
        self._revert(entry)
        self._save()
        return entry

    def _revert(self, entry: HistoryEntry):
        p = self.base_dir / entry.path
        if entry.action == "create":
            if p.exists():
                if p.is_file():
                    p.unlink()
                else:
                    shutil.rmtree(p)
        elif entry.action == "delete":
            if entry.content_before is not None:
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text(entry.content_before, encoding="utf-8")
        elif entry.action == "modify":
            if p.exists() and entry.content_before is not None:
                p.write_text(entry.content_before, encoding="utf-8")
        elif entry.action == "rename":
            old_p = self.base_dir / entry.content_before
            new_p = self.base_dir / entry.path
            if new_p.exists():
                new_p.rename(old_p)

    def list_entries(self) -> list[dict]:
        return [e.to_dict() for e in self._entries[-20:]]

    def clear(self):
        self._entries.clear()
        for f in self.history_dir.glob("*.json"):
            f.unlink()

    @property
    def count(self) -> int:
        return len(self._entries)