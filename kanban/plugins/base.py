"""Plugin infrastructure for weekly summaries."""
from __future__ import annotations

import importlib.util
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional

from ..models import Comment, HistoryEntry, Task


@dataclass
class SummaryContext:
    start_date: str
    end_date: str
    tasks: List[Task]
    comments: List[Comment]
    history: List[HistoryEntry]


class SummaryPlugin:
    """Interface for summary plugins."""

    name: str = "BaseSummaryPlugin"
    description: str = ""

    def summarize(self, context: SummaryContext) -> str:
        raise NotImplementedError


class DefaultSummaryPlugin(SummaryPlugin):
    name = "Default Markdown Summary"
    description = "Summarize progress using local heuristics."

    def summarize(self, context: SummaryContext) -> str:
        if not context.tasks and not context.comments and not context.history:
            return "# Weekly Summary\n\nNo material changes for the selected period."
        lines = ["# Weekly Summary", "", "## Executive Summary"]
        lines.append(
            f"Reviewed tasks between {context.start_date} and {context.end_date}."
        )
        lines.append("Key updates captured below.")
        lines.append("\n## Highlights by Story")
        tasks_by_story: Dict[str, List[Task]] = {}
        for task in context.tasks:
            tasks_by_story.setdefault(task.story_id, []).append(task)
        for story_id, tasks in tasks_by_story.items():
            lines.append(f"- Story {story_id}: {len(tasks)} task(s) touched.")
        completed = [t.id for t in context.tasks if any(
            h.event_type == "column-moved" and h.payload.get("column_id", "").lower()
            .startswith("done")
            for h in t.history
        )]
        lines.append("\n## Completed Tasks")
        if completed:
            for tid in completed:
                lines.append(f"- {tid}")
        else:
            lines.append("- None in this period.")
        blockers = [c for c in context.comments if "block" in c.body.lower()]
        lines.append("\n## Blockers / Risks")
        if blockers:
            for comment in blockers:
                lines.append(f"- {comment.task_id}: {comment.body}")
        else:
            lines.append("- No blockers recorded.")
        lines.append("\n## Next Likely Steps")
        if context.tasks:
            lines.append("- Continue progressing active tasks toward Done.")
        else:
            lines.append("- Await new activity.")
        lines.append("\n## Evidence Appendix")
        for entry in context.history:
            lines.append(
                f"- {entry.timestamp} {entry.event_type} {entry.payload} (Task {entry.task_id})"
            )
        for comment in context.comments:
            lines.append(
                f"- {comment.timestamp} Comment on {comment.task_id}: {comment.body}"
            )
        return "\n".join(lines)


class PluginLoader:
    """Loads summary plugins from the plugins directory."""

    def __init__(self, directory: Path):
        self.directory = directory
        self.directory.mkdir(parents=True, exist_ok=True)

    def discover(self) -> List[SummaryPlugin]:
        plugins: List[SummaryPlugin] = [DefaultSummaryPlugin()]
        for path in self.directory.glob("*.py"):
            if path.name == "base.py":
                continue
            plugin = self._load_plugin(path)
            if plugin:
                plugins.append(plugin)
        return plugins

    def _load_plugin(self, path: Path) -> Optional[SummaryPlugin]:
        spec = importlib.util.spec_from_file_location(path.stem, path)
        if not spec or not spec.loader:
            return None
        module = importlib.util.module_from_spec(spec)
        try:
            spec.loader.exec_module(module)
        except Exception:
            return None
        for attr in dir(module):
            obj = getattr(module, attr)
            if (
                isinstance(obj, type)
                and issubclass(obj, SummaryPlugin)
                and obj is not SummaryPlugin
            ):
                return obj()
        return None
