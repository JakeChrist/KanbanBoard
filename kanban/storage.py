"""Persistence layer for Kanban app."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Optional

from .models import (
    Board,
    BoardSettings,
    Column,
    Comment,
    HistoryEntry,
    Story,
    Task,
    WeeklyReview,
    current_timestamp,
    generate_id,
)


class KanbanDataStore:
    """Manages persistent storage of boards, stories, tasks, and comments."""

    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.boards: Dict[str, Board] = {}
        self.stories: Dict[str, Story] = {}
        self.tasks: Dict[str, Task] = {}
        self.comments: Dict[str, Comment] = {}
        self.reviews: Dict[str, WeeklyReview] = {}
        self.story_sequences: Dict[str, int] = {}
        self._load()

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------
    def _load(self) -> None:
        if not self.path.exists():
            self._save()
            return
        data = json.loads(self.path.read_text())
        for board_data in data.get("boards", []):
            board = Board(
                id=board_data["id"],
                name=board_data["name"],
                columns=[Column(**col) for col in board_data.get("columns", [])],
                archived=board_data.get("archived", False),
                settings=BoardSettings(**board_data.get("settings", {})),
            )
            self.boards[board.id] = board
        for story_data in data.get("stories", []):
            story = Story(**story_data)
            self.stories[story.id] = story
        for task_data in data.get("tasks", []):
            history = [HistoryEntry(**entry) for entry in task_data.get("history", [])]
            task = Task(
                id=task_data["id"],
                board_id=task_data["board_id"],
                column_id=task_data["column_id"],
                story_id=task_data["story_id"],
                title=task_data["title"],
                description=task_data.get("description", ""),
                priority=task_data.get("priority", ""),
                estimate=task_data.get("estimate", ""),
                due_date=task_data.get("due_date"),
                tags=task_data.get("tags", []),
                archived=task_data.get("archived", False),
                history=history,
            )
            self.tasks[task.id] = task
        for comment_data in data.get("comments", []):
            comment = Comment(**comment_data)
            self.comments[comment.id] = comment
        for review_data in data.get("weekly_reviews", []):
            review = WeeklyReview(**review_data)
            self.reviews[review.id] = review
        self.story_sequences = data.get("story_sequences", {})

    def _save(self) -> None:
        data = {
            "boards": [board.to_dict() for board in self.boards.values()],
            "stories": [story.to_dict() for story in self.stories.values()],
            "tasks": [task.to_dict() for task in self.tasks.values()],
            "comments": [comment.to_dict() for comment in self.comments.values()],
            "weekly_reviews": [review.to_dict() for review in self.reviews.values()],
            "story_sequences": self.story_sequences,
            "schema_version": "1.0",
        }
        self.path.write_text(json.dumps(data, indent=2))

    def export_to(self, output_path: Path) -> None:
        self._save()
        output_path.write_text(self.path.read_text())

    def import_from(self, input_path: Path, merge: bool = False) -> None:
        data = json.loads(input_path.read_text())
        version = data.get("schema_version")
        if version != "1.0":
            raise ValueError(f"Unsupported schema version: {version}")
        if not merge:
            self.boards.clear()
            self.stories.clear()
            self.tasks.clear()
            self.comments.clear()
            self.reviews.clear()
            self.story_sequences.clear()
        self._load_from_dict(data)
        self._save()

    def _load_from_dict(self, data: Dict) -> None:
        for board_data in data.get("boards", []):
            if board_data["id"] in self.boards:
                continue
            board = Board(
                id=board_data["id"],
                name=board_data["name"],
                columns=[Column(**col) for col in board_data.get("columns", [])],
                archived=board_data.get("archived", False),
                settings=BoardSettings(**board_data.get("settings", {})),
            )
            self.boards[board.id] = board
        for story_data in data.get("stories", []):
            if story_data["id"] in self.stories:
                continue
            story = Story(**story_data)
            self.stories[story.id] = story
        for task_data in data.get("tasks", []):
            if task_data["id"] in self.tasks:
                continue
            history = [HistoryEntry(**entry) for entry in task_data.get("history", [])]
            task = Task(**{**task_data, "history": history})
            self.tasks[task.id] = task
        for comment_data in data.get("comments", []):
            if comment_data["id"] in self.comments:
                continue
            comment = Comment(**comment_data)
            self.comments[comment.id] = comment
        for review_data in data.get("weekly_reviews", []):
            if review_data["id"] in self.reviews:
                continue
            review = WeeklyReview(**review_data)
            self.reviews[review.id] = review
        for story_code, sequence in data.get("story_sequences", {}).items():
            self.story_sequences[story_code] = max(
                sequence, self.story_sequences.get(story_code, 0)
            )

    # ------------------------------------------------------------------
    # Board management
    # ------------------------------------------------------------------
    def create_board(self, name: str, columns: Optional[List[str]] = None) -> Board:
        board_id = generate_id("board")
        if columns is None:
            columns = ["Backlog", "In Progress", "Done"]
        board_columns = [Column(generate_id("col"), label) for label in columns]
        board = Board(id=board_id, name=name, columns=board_columns)
        self.boards[board_id] = board
        self._save()
        return board

    def rename_board(self, board_id: str, new_name: str) -> None:
        board = self.boards[board_id]
        board.name = new_name
        self._save()

    def archive_board(self, board_id: str, archived: bool = True) -> None:
        board = self.boards[board_id]
        board.archived = archived
        self._save()

    def delete_board(self, board_id: str) -> None:
        for task_id, task in list(self.tasks.items()):
            if task.board_id == board_id:
                self.delete_task(task_id, save=False)
        del self.boards[board_id]
        self._save()

    def add_column(self, board_id: str, name: str) -> Column:
        column = Column(generate_id("col"), name)
        self.boards[board_id].columns.append(column)
        self._save()
        return column

    def remove_column(self, board_id: str, column_id: str) -> None:
        board = self.boards[board_id]
        board.columns = [c for c in board.columns if c.id != column_id]
        for task in self.tasks.values():
            if task.column_id == column_id:
                task.column_id = board.columns[0].id if board.columns else ""
                task.history.append(
                    HistoryEntry(
                        id=generate_id("hist"),
                        task_id=task.id,
                        timestamp=current_timestamp(),
                        event_type="column-removed",
                        payload={"column_id": column_id},
                    )
                )
        self._save()

    def reorder_columns(self, board_id: str, column_ids: List[str]) -> None:
        board = self.boards[board_id]
        id_to_column = {column.id: column for column in board.columns}
        board.columns = [id_to_column[cid] for cid in column_ids if cid in id_to_column]
        self._save()

    # ------------------------------------------------------------------
    # Stories
    # ------------------------------------------------------------------
    def create_story(self, code: str, title: str, **kwargs) -> Story:
        story_id = generate_id("story")
        story = Story(id=story_id, code=code, title=title, **kwargs)
        self.stories[story_id] = story
        self.story_sequences.setdefault(code, 0)
        self._save()
        return story

    def update_story(self, story_id: str, **kwargs) -> None:
        story = self.stories[story_id]
        for field_name, value in kwargs.items():
            setattr(story, field_name, value)
        if "code" in kwargs:
            self.story_sequences.setdefault(story.code, 0)
        self._save()

    def archive_story(self, story_id: str, archived: bool = True) -> None:
        self.stories[story_id].archived = archived
        self._save()

    def delete_story(self, story_id: str) -> None:
        for task_id, task in list(self.tasks.items()):
            if task.story_id == story_id:
                self.delete_task(task_id, save=False)
        del self.stories[story_id]
        self._save()

    # ------------------------------------------------------------------
    # Tasks
    # ------------------------------------------------------------------
    def _next_task_id(self, story_code: str) -> str:
        sequence = self.story_sequences.get(story_code, 0) + 1
        self.story_sequences[story_code] = sequence
        return f"{story_code}-{sequence:03d}"

    def create_task(
        self,
        board_id: str,
        column_id: str,
        story_id: str,
        title: str,
        **kwargs,
    ) -> Task:
        story = self.stories[story_id]
        task_id = self._next_task_id(story.code)
        task = Task(
            id=task_id,
            board_id=board_id,
            column_id=column_id,
            story_id=story_id,
            title=title,
            description=kwargs.get("description", ""),
            priority=kwargs.get("priority", ""),
            estimate=kwargs.get("estimate", ""),
            due_date=kwargs.get("due_date"),
            tags=kwargs.get("tags", []),
        )
        task.history.append(
            HistoryEntry(
                id=generate_id("hist"),
                task_id=task.id,
                timestamp=current_timestamp(),
                event_type="created",
                payload={"board_id": board_id, "column_id": column_id},
            )
        )
        self.tasks[task_id] = task
        self._save()
        return task

    def update_task(self, task_id: str, **kwargs) -> None:
        task = self.tasks[task_id]
        for field_name, value in kwargs.items():
            if hasattr(task, field_name):
                setattr(task, field_name, value)
        self._save()

    def move_task(self, task_id: str, new_column_id: str) -> None:
        task = self.tasks[task_id]
        if task.column_id == new_column_id:
            return
        task.column_id = new_column_id
        task.history.append(
            HistoryEntry(
                id=generate_id("hist"),
                task_id=task_id,
                timestamp=current_timestamp(),
                event_type="column-moved",
                payload={"column_id": new_column_id},
            )
        )
        self._save()

    def rehome_task(self, task_id: str, target_story_id: str) -> Task:
        task = self.tasks[task_id]
        old_story = self.stories[task.story_id]
        new_story = self.stories[target_story_id]
        new_task_id = self._next_task_id(new_story.code)
        task.history.append(
            HistoryEntry(
                id=generate_id("hist"),
                task_id=task.id,
                timestamp=current_timestamp(),
                event_type="rehome",
                payload={"new_task_id": new_task_id},
            )
        )
        new_task = Task(
            id=new_task_id,
            board_id=task.board_id,
            column_id=task.column_id,
            story_id=target_story_id,
            title=task.title,
            description=task.description,
            priority=task.priority,
            estimate=task.estimate,
            due_date=task.due_date,
            tags=list(task.tags),
            archived=task.archived,
            history=list(task.history),
        )
        self.tasks[new_task_id] = new_task
        self.tasks.pop(task_id)
        self._save()
        return new_task

    def archive_task(self, task_id: str, archived: bool = True) -> None:
        task = self.tasks[task_id]
        task.archived = archived
        task.history.append(
            HistoryEntry(
                id=generate_id("hist"),
                task_id=task_id,
                timestamp=current_timestamp(),
                event_type="archived" if archived else "unarchived",
                payload={},
            )
        )
        self._save()

    def delete_task(self, task_id: str, *, save: bool = True) -> None:
        for comment_id, comment in list(self.comments.items()):
            if comment.task_id == task_id:
                del self.comments[comment_id]
        del self.tasks[task_id]
        if save:
            self._save()

    # ------------------------------------------------------------------
    # Comments
    # ------------------------------------------------------------------
    def add_comment(self, task_id: str, author: str, body: str) -> Comment:
        comment_id = generate_id("cmt")
        comment = Comment(
            id=comment_id,
            task_id=task_id,
            timestamp=current_timestamp(),
            author=author,
            body=body,
        )
        self.comments[comment_id] = comment
        self._save()
        return comment

    def edit_comment(self, comment_id: str, new_body: str) -> None:
        comment = self.comments[comment_id]
        comment.edited_history.append(
            {"timestamp": current_timestamp(), "body": comment.body}
        )
        comment.body = new_body
        comment.timestamp = current_timestamp()
        self._save()

    def delete_comment(self, comment_id: str) -> None:
        del self.comments[comment_id]
        self._save()

    # ------------------------------------------------------------------
    # Weekly Reviews
    # ------------------------------------------------------------------
    def create_weekly_review(
        self,
        board_ids: List[str],
        story_ids: List[str],
        start_date: str,
        end_date: str,
        summary_markdown: str,
        evidence: Optional[List[Dict[str, str]]] = None,
    ) -> WeeklyReview:
        review = WeeklyReview(
            id=generate_id("review"),
            board_ids=board_ids,
            story_ids=story_ids,
            start_date=start_date,
            end_date=end_date,
            summary_markdown=summary_markdown,
            evidence=evidence or [],
        )
        self.reviews[review.id] = review
        self._save()
        return review

    # ------------------------------------------------------------------
    # Query helpers
    # ------------------------------------------------------------------
    def tasks_for_board(self, board_id: str, include_archived: bool = False) -> List[Task]:
        return [
            task
            for task in self.tasks.values()
            if task.board_id == board_id and (include_archived or not task.archived)
        ]

    def tasks_for_story(self, story_id: str, include_archived: bool = False) -> List[Task]:
        return [
            task
            for task in self.tasks.values()
            if task.story_id == story_id and (include_archived or not task.archived)
        ]

    def comments_for_task(self, task_id: str) -> List[Comment]:
        comments = [c for c in self.comments.values() if c.task_id == task_id]
        comments.sort(key=lambda c: c.timestamp)
        return comments

    def history_for_task(self, task_id: str) -> List[HistoryEntry]:
        task = self.tasks[task_id]
        return list(task.history)

    def story_by_code(self, code: str) -> Optional[Story]:
        for story in self.stories.values():
            if story.code == code:
                return story
        return None

    def save(self) -> None:
        self._save()
