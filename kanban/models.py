"""Domain models for the Kanban application."""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import List, Dict, Optional
import uuid

TIMESTAMP_FORMAT = "%Y-%m-%dT%H:%M:%S%z"

def current_timestamp() -> str:
    """Return a timestamp string in UTC using the application format."""
    return datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")


def generate_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex}"


@dataclass
class Comment:
    id: str
    task_id: str
    timestamp: str
    author: str
    body: str
    edited_history: List[Dict[str, str]] = field(default_factory=list)

    def to_dict(self) -> Dict:
        return asdict(self)


@dataclass
class HistoryEntry:
    id: str
    task_id: str
    timestamp: str
    event_type: str
    payload: Dict[str, str]

    def to_dict(self) -> Dict:
        return asdict(self)


@dataclass
class Task:
    id: str
    board_id: str
    column_id: str
    story_id: str
    title: str
    description: str = ""
    priority: str = ""
    estimate: str = ""
    due_date: Optional[str] = None
    tags: List[str] = field(default_factory=list)
    archived: bool = False
    history: List[HistoryEntry] = field(default_factory=list)

    def to_dict(self) -> Dict:
        data = asdict(self)
        data["history"] = [h.to_dict() for h in self.history]
        return data


@dataclass
class Column:
    id: str
    name: str

    def to_dict(self) -> Dict:
        return asdict(self)


@dataclass
class BoardSettings:
    default_columns: List[str] = field(default_factory=lambda: ["Backlog", "In Progress", "Done"])
    wip_help_text: str = ""
    show_color_legend: bool = True

    def to_dict(self) -> Dict:
        return asdict(self)


@dataclass
class Board:
    id: str
    name: str
    columns: List[Column] = field(default_factory=list)
    archived: bool = False
    settings: BoardSettings = field(default_factory=BoardSettings)

    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "name": self.name,
            "columns": [c.to_dict() for c in self.columns],
            "archived": self.archived,
            "settings": self.settings.to_dict(),
        }


@dataclass
class Story:
    id: str
    code: str
    title: str
    description: str = ""
    color: str = "#007ACC"
    tags: List[str] = field(default_factory=list)
    status: str = "Planned"
    archived: bool = False

    def to_dict(self) -> Dict:
        return asdict(self)


@dataclass
class WeeklyReview:
    id: str
    board_ids: List[str]
    story_ids: List[str]
    start_date: str
    end_date: str
    summary_markdown: str
    evidence: List[Dict[str, str]] = field(default_factory=list)

    def to_dict(self) -> Dict:
        return asdict(self)
