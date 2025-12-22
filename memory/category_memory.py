import json
from pathlib import Path
from typing import List

MEMORY_PATH = Path("memory/category_memory.json")


class CategoryMemory:
    def __init__(self, max_history: int = 5):
        self.max_history = max_history
        self._ensure_file_exists()

    def _ensure_file_exists(self):
        if not MEMORY_PATH.exists():
            MEMORY_PATH.parent.mkdir(parents=True, exist_ok=True)
            MEMORY_PATH.write_text("[]", encoding="utf-8")

    def load(self) -> List[str]:
        try:
            data = json.loads(MEMORY_PATH.read_text(encoding="utf-8"))
            if isinstance(data, list):
                return data
        except Exception:
            pass

        # Self-heal if corrupted
        MEMORY_PATH.write_text("[]", encoding="utf-8")
        return []

    def save(self, categories: List[str]):
        trimmed = categories[-self.max_history :]
        MEMORY_PATH.write_text(
            json.dumps(trimmed, indent=2),
            encoding="utf-8"
        )

    def record(self, category: str):
        categories = self.load()
        categories.append(category)
        self.save(categories)

    def recent(self) -> List[str]:
        return self.load()
