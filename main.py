"""Entry point for the Kanban board application."""
from __future__ import annotations

import logging
from datetime import date
from pathlib import Path
from typing import Dict, List, Optional

from PyQt6.QtCore import QDate, Qt, QTimer
from PyQt6.QtGui import QColor, QPalette
from PyQt6.QtWidgets import (
    QApplication,
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QColorDialog,
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QTabWidget,
    QTextEdit,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from kanban.logging_utils import configure_logging
from kanban.models import Comment, HistoryEntry, Story, Task
from kanban.plugins.base import PluginLoader, SummaryContext, SummaryPlugin
from kanban.storage import KanbanDataStore

APP_AUTHOR = "Local User"
DATA_PATH = Path.home() / ".local_share" / "kanban_data.json"
LOG_PATH = Path.home() / ".local_share" / "kanban_app.log"
PLUGINS_PATH = Path(Path.cwd(), "kanban", "plugins")


def create_application() -> QApplication:
    app = QApplication([])
    app.setApplicationName("Kanban Board")
    palette = app.palette()
    palette.setColor(QPalette.ColorRole.Window, QColor("#1e1e1e"))
    palette.setColor(QPalette.ColorRole.WindowText, QColor("#f0f0f0"))
    palette.setColor(QPalette.ColorRole.Base, QColor("#252526"))
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor("#2d2d30"))
    palette.setColor(QPalette.ColorRole.ToolTipBase, QColor("#ffffff"))
    palette.setColor(QPalette.ColorRole.ToolTipText, QColor("#000000"))
    palette.setColor(QPalette.ColorRole.Text, QColor("#f0f0f0"))
    palette.setColor(QPalette.ColorRole.Button, QColor("#3c3c3c"))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor("#f0f0f0"))
    palette.setColor(QPalette.ColorRole.Highlight, QColor("#007acc"))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor("#ffffff"))
    app.setPalette(palette)
    return app


class StoryBadge(QLabel):
    def __init__(self, story: Story, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.story = story
        self.setText(f"{story.code}: {story.title}")
        self.setStyleSheet(
            f"padding: 4px; border-radius: 4px; background-color: {story.color};"
        )


class TaskListWidget(QListWidget):
    def __init__(self, board_view: "BoardView") -> None:
        super().__init__()
        self.board_view = board_view
        self.setAcceptDrops(True)
        self.setDragEnabled(True)
        self.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.setDropIndicatorShown(True)
        self.setDragDropMode(QAbstractItemView.DragDropMode.DragDrop)
        self.itemDoubleClicked.connect(self._open_task_detail)

    def _open_task_detail(self, item: QListWidgetItem) -> None:
        task_id = item.data(Qt.ItemDataRole.UserRole)
        dialog = TaskDetailDialog(self.board_view.window(), self.board_view.store, task_id)
        dialog.exec()
        self.board_view.refresh()

    def dragEnterEvent(self, event) -> None:  # type: ignore[override]
        if event.mimeData().hasFormat("application/x-qabstractitemmodeldatalist"):
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event) -> None:  # type: ignore[override]
        if event.mimeData().hasFormat("application/x-qabstractitemmodeldatalist"):
            event.acceptProposedAction()
        else:
            super().dragMoveEvent(event)

    def dropEvent(self, event) -> None:  # type: ignore[override]
        source = event.source()
        moved_task_ids = []
        if isinstance(source, TaskListWidget):
            moved_task_ids = [
                source.item(i).data(Qt.ItemDataRole.UserRole)
                for i in range(source.count())
                if source.item(i) and source.item(i).isSelected()
            ]
        super().dropEvent(event)
        if not moved_task_ids:
            item = self.itemAt(event.position().toPoint())
            if item:
                moved_task_ids = [item.data(Qt.ItemDataRole.UserRole)]
        moved = False
        for task_id in moved_task_ids:
            task = self.board_view.store.tasks.get(task_id)
            if task and task.column_id != self.objectName():
                self.board_view.move_task(task_id, self.objectName(), refresh=False)
                moved = True
        if moved:
            QTimer.singleShot(0, self.board_view.refresh)


class BoardView(QWidget):
    def __init__(self, store: KanbanDataStore, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.store = store
        self.current_board_id: Optional[str] = None
        self.columns: Dict[str, TaskListWidget] = {}
        self.search_text = ""
        self.story_filter: Optional[str] = None
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        controls = QHBoxLayout()
        self.board_selector = QComboBox()
        self.board_selector.currentIndexChanged.connect(self._board_selected)
        controls.addWidget(QLabel("Board:"))
        controls.addWidget(self.board_selector)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search tasks...")
        self.search_input.textChanged.connect(self._on_search_changed)
        controls.addWidget(self.search_input)

        self.story_filter_box = QComboBox()
        self.story_filter_box.addItem("All Stories", None)
        self.story_filter_box.currentIndexChanged.connect(self._on_story_filter)
        controls.addWidget(self.story_filter_box)

        new_board_button = QPushButton("New Board")
        new_board_button.clicked.connect(self._create_board)
        controls.addWidget(new_board_button)

        layout.addLayout(controls)

        self.columns_container = QWidget()
        self.columns_layout = QHBoxLayout(self.columns_container)
        self.columns_layout.setContentsMargins(0, 0, 0, 0)
        self.columns_layout.setSpacing(12)
        layout.addWidget(self.columns_container)

        self.empty_state = QLabel(
            "Create a board to get started, then add tasks to see them here."
        )
        self.empty_state.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_state.setWordWrap(True)
        layout.addWidget(self.empty_state)

        actions_layout = QHBoxLayout()
        new_story_button = QPushButton("New Story")
        new_story_button.clicked.connect(self._create_story)
        actions_layout.addWidget(new_story_button)

        new_task_button = QPushButton("New Task")
        new_task_button.clicked.connect(self._create_task)
        actions_layout.addWidget(new_task_button)

        layout.addLayout(actions_layout)

        self.refresh_boards()

    def refresh_boards(self) -> None:
        self.board_selector.blockSignals(True)
        self.board_selector.clear()
        boards = [b for b in self.store.boards.values() if not b.archived]
        for board in boards:
            self.board_selector.addItem(board.name, board.id)
        self.board_selector.blockSignals(False)
        if boards:
            self.board_selector.setCurrentIndex(0)
            self._board_selected(0)
        else:
            self.current_board_id = None
            self.columns_container.hide()
            self.empty_state.setText(
                "No boards available. Click 'New Board' to create your first board."
            )
            self.empty_state.show()
        self._notify_weekly_view()
        self._refresh_story_filter()

    def _refresh_story_filter(self) -> None:
        self.story_filter_box.blockSignals(True)
        self.story_filter_box.clear()
        self.story_filter_box.addItem("All Stories", None)
        for story in self.store.stories.values():
            if not story.archived:
                self.story_filter_box.addItem(f"{story.code} - {story.title}", story.id)
        self.story_filter_box.blockSignals(False)
        if self.story_filter:
            index = self.story_filter_box.findData(self.story_filter)
            if index != -1:
                self.story_filter_box.setCurrentIndex(index)
                return
        self.story_filter = None
        if self.story_filter_box.count():
            self.story_filter_box.setCurrentIndex(0)

    def _board_selected(self, index: int) -> None:
        board_id = self.board_selector.itemData(index)
        if not board_id:
            return
        self.current_board_id = board_id
        self.refresh()

    def refresh(self) -> None:
        for i in reversed(range(self.columns_layout.count())):
            item = self.columns_layout.takeAt(i)
            widget = item.widget()
            if widget:
                widget.setParent(None)
        self.columns.clear()
        if not self.current_board_id:
            self.columns_container.hide()
            self.empty_state.setText(
                "Create or select a board to get started."
            )
            self.empty_state.show()
            return
        board = self.store.boards[self.current_board_id]
        if not board.columns:
            self.columns_container.hide()
            self.empty_state.setText(
                "This board has no columns yet. Add columns in the configuration to start tracking tasks."
            )
            self.empty_state.show()
            return
        self.empty_state.hide()
        self.columns_container.show()
        for column in board.columns:
            group = QGroupBox(column.name)
            group_layout = QVBoxLayout(group)
            task_list = TaskListWidget(self)
            task_list.setObjectName(column.id)
            group_layout.addWidget(task_list)
            self.columns_layout.addWidget(group)
            self.columns[column.id] = task_list
        self._populate_tasks()

    def _populate_tasks(self) -> None:
        if not self.current_board_id:
            return
        tasks = self.store.tasks_for_board(self.current_board_id)
        for column_id, widget in self.columns.items():
            widget.clear()
            for task in tasks:
                if task.column_id != column_id:
                    continue
                if self.search_text and self.search_text.lower() not in (
                    task.title.lower() + task.description.lower()
                ):
                    continue
                if self.story_filter and task.story_id != self.story_filter:
                    continue
                item = QListWidgetItem(task.title)
                item.setData(Qt.ItemDataRole.UserRole, task.id)
                story = self.store.stories.get(task.story_id)
                if story:
                    item.setBackground(QColor(story.color))
                widget.addItem(item)

    def _create_board(self) -> None:
        dialog = TextInputDialog("Create Board", "Board name:")
        if dialog.exec() == QDialog.DialogCode.Accepted:
            name = dialog.text_value
            if name:
                self.store.create_board(name)
                self.refresh_boards()

    def _create_story(self) -> None:
        dialog = StoryDialog(self.store)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.refresh()
            self._refresh_story_filter()
            self._notify_story_change()

    def _create_task(self) -> None:
        if not self.current_board_id:
            return
        dialog = TaskDialog(self.store, self.current_board_id)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.refresh()

    def move_task(self, task_id: str, column_id: str, *, refresh: bool = True) -> None:
        self.store.move_task(task_id, column_id)
        if refresh:
            self.refresh()

    def _notify_weekly_view(self) -> None:
        window = self.window()
        if hasattr(window, "weekly_view"):
            window.weekly_view.refresh_sources()

    def _notify_story_change(self) -> None:
        window = self.window()
        if hasattr(window, "story_view"):
            window.story_view.refresh()

    def _on_search_changed(self, text: str) -> None:
        self.search_text = text
        self._populate_tasks()

    def _on_story_filter(self, index: int) -> None:
        self.story_filter = self.story_filter_box.itemData(index)
        self._populate_tasks()


class StoryView(QWidget):
    def __init__(self, store: KanbanDataStore, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.store = store
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        header = QHBoxLayout()
        header.addWidget(QLabel("Stories"))
        new_button = QPushButton("New Story")
        new_button.clicked.connect(self._new_story)
        header.addWidget(new_button)
        delete_button = QPushButton("Delete Story")
        delete_button.clicked.connect(self._delete_story)
        header.addWidget(delete_button)
        header.addStretch()
        layout.addLayout(header)

        self.story_list = QListWidget()
        self.story_list.itemDoubleClicked.connect(self._edit_story)
        layout.addWidget(self.story_list)
        self.refresh()

    def refresh(self) -> None:
        self.story_list.clear()
        for story in self.store.stories.values():
            item = QListWidgetItem(f"{story.code} — {story.title}")
            item.setData(Qt.ItemDataRole.UserRole, story.id)
            item.setToolTip(story.description)
            color = QColor(story.color)
            item.setBackground(color)
            self.story_list.addItem(item)

    def _new_story(self) -> None:
        dialog = StoryDialog(self.store)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.refresh()
            self._notify_board_view()

    def _edit_story(self, item: QListWidgetItem) -> None:
        story_id = item.data(Qt.ItemDataRole.UserRole)
        dialog = StoryDialog(self.store, story_id)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.refresh()
            self._notify_board_view()

    def _delete_story(self) -> None:
        item = self.story_list.currentItem()
        if not item:
            QMessageBox.information(self, "Delete Story", "Select a story to delete.")
            return
        story_id = item.data(Qt.ItemDataRole.UserRole)
        story = self.store.stories.get(story_id)
        prompt = (
            f"Delete story '{story.code}: {story.title}' and all of its tasks?"
            if story
            else "Delete the selected story?"
        )
        confirm = QMessageBox.question(
            self,
            "Delete Story",
            prompt,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if confirm == QMessageBox.StandardButton.Yes:
            self.store.delete_story(story_id)
            self.refresh()
            self._notify_board_view()

    def _notify_board_view(self) -> None:
        window = self.window()
        if hasattr(window, "board_view"):
            window.board_view._refresh_story_filter()
            window.board_view.refresh()


class WeeklyReviewView(QWidget):
    def __init__(self, store: KanbanDataStore, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.store = store
        self.plugins = PluginLoader(PLUGINS_PATH).discover()
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.start_date = QDateEdit()
        self.start_date.setDate(date.today())
        self.start_date.setCalendarPopup(True)
        form.addRow("Start date", self.start_date)
        self.end_date = QDateEdit()
        self.end_date.setDate(date.today())
        self.end_date.setCalendarPopup(True)
        form.addRow("End date", self.end_date)

        self.board_selector = QComboBox()
        for board in self.store.boards.values():
            if not board.archived:
                self.board_selector.addItem(board.name, board.id)
        self.board_selector.setEditable(True)
        form.addRow("Board", self.board_selector)

        self.plugin_selector = QComboBox()
        for plugin in self.plugins:
            self.plugin_selector.addItem(plugin.name, plugin)
        form.addRow("Plugin", self.plugin_selector)

        layout.addLayout(form)

        generate_button = QPushButton("Generate Summary")
        generate_button.clicked.connect(self._generate_summary)
        layout.addWidget(generate_button)

        self.summary_output = QTextEdit()
        layout.addWidget(self.summary_output)

    def refresh_sources(self) -> None:
        current_board = self.board_selector.currentData()
        self.board_selector.blockSignals(True)
        self.board_selector.clear()
        for board in self.store.boards.values():
            if not board.archived:
                self.board_selector.addItem(board.name, board.id)
        self.board_selector.blockSignals(False)
        if current_board:
            index = self.board_selector.findData(current_board)
            if index != -1:
                self.board_selector.setCurrentIndex(index)
                return
        if self.board_selector.count():
            self.board_selector.setCurrentIndex(0)

    def _generate_summary(self) -> None:
        board_id = self.board_selector.currentData()
        if not board_id:
            QMessageBox.warning(self, "Weekly Summary", "Please select a board.")
            return
        plugin: SummaryPlugin = self.plugin_selector.currentData()  # type: ignore[assignment]
        start = self.start_date.date().toString("yyyy-MM-dd")
        end = self.end_date.date().toString("yyyy-MM-dd")
        tasks = [
            task
            for task in self.store.tasks_for_board(board_id, include_archived=True)
            if any(
                start <= history.timestamp[:10] <= end
                for history in task.history
            )
        ]
        history_entries: List[HistoryEntry] = []
        comments: List[Comment] = []
        for task in tasks:
            for entry in task.history:
                if start <= entry.timestamp[:10] <= end:
                    history_entries.append(entry)
            for comment in self.store.comments_for_task(task.id):
                if start <= comment.timestamp[:10] <= end:
                    comments.append(comment)
        context = SummaryContext(
            start_date=start,
            end_date=end,
            tasks=tasks,
            comments=comments,
            history=history_entries,
        )
        markdown = plugin.summarize(context)
        self.summary_output.setPlainText(markdown)
        self.store.create_weekly_review(
            [board_id],
            list({task.story_id for task in tasks}),
            start,
            end,
            markdown,
            [entry.to_dict() for entry in history_entries]
            + [comment.to_dict() for comment in comments],
        )


class TextInputDialog(QDialog):
    def __init__(self, title: str, label: str, default: str = "") -> None:
        super().__init__()
        self.setWindowTitle(title)
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.input = QLineEdit(default)
        form.addRow(label, self.input)
        layout.addLayout(form)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    @property
    def text_value(self) -> str:
        return self.input.text().strip()


class StoryDialog(QDialog):
    def __init__(self, store: KanbanDataStore, story_id: Optional[str] = None) -> None:
        super().__init__()
        self.store = store
        self.story_id = story_id
        self.setWindowTitle("Story")
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.code_input = QLineEdit()
        self.code_input.setPlaceholderText("e.g., PROJ-101")
        self.title_input = QLineEdit()
        self.title_input.setPlaceholderText("Short summary")
        self.desc_input = QTextEdit()
        self.desc_input.setPlaceholderText("Describe the story context and goals...")
        color_row = QHBoxLayout()
        color_row.setContentsMargins(0, 0, 0, 0)
        self.color_input = QLineEdit("#007acc")
        self.color_input.setPlaceholderText("#RRGGBB")
        color_row.addWidget(self.color_input)
        self.color_button = QPushButton("Pick…")
        self.color_button.clicked.connect(self._pick_color)
        color_row.addWidget(self.color_button)
        self.color_input.textChanged.connect(self._update_color_preview)
        color_widget = QWidget()
        color_widget.setLayout(color_row)
        self.tags_input = QLineEdit()
        self.tags_input.setPlaceholderText("release, backend")
        self.status_box = QComboBox()
        self.status_box.addItems(["Planned", "Active", "Blocked", "Done"])
        self.archive_box = QComboBox()
        self.archive_box.addItems(["Active", "Archived"])
        form.addRow("Code", self.code_input)
        form.addRow("Title", self.title_input)
        form.addRow("Description", self.desc_input)
        form.addRow("Color", color_widget)
        form.addRow("Tags (comma separated)", self.tags_input)
        form.addRow("Status", self.status_box)
        form.addRow("Archive", self.archive_box)
        layout.addLayout(form)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        if story_id:
            self._load_story()
        else:
            self._update_color_preview()

    def _load_story(self) -> None:
        story = self.store.stories[self.story_id]  # type: ignore[index]
        self.code_input.setText(story.code)
        self.title_input.setText(story.title)
        self.desc_input.setPlainText(story.description)
        self.color_input.setText(story.color)
        self.tags_input.setText(", ".join(story.tags))
        self.status_box.setCurrentText(story.status)
        self.archive_box.setCurrentIndex(1 if story.archived else 0)
        self._update_color_preview()

    def _save(self) -> None:
        code = self.code_input.text().strip()
        title = self.title_input.text().strip()
        if not code or not title:
            QMessageBox.warning(self, "Story", "Code and title are required.")
            return
        data = {
            "description": self.desc_input.toPlainText().strip(),
            "color": self.color_input.text().strip(),
            "tags": [tag.strip() for tag in self.tags_input.text().split(",") if tag.strip()],
            "status": self.status_box.currentText(),
            "archived": self.archive_box.currentIndex() == 1,
        }
        if self.story_id:
            self.store.update_story(self.story_id, code=code, title=title, **data)
        else:
            self.store.create_story(code=code, title=title, **data)
        self.accept()

    def _pick_color(self) -> None:
        current = QColor(self.color_input.text())
        color = QColorDialog.getColor(
            current if current.isValid() else QColor("#007acc"), self
        )
        if color.isValid():
            self.color_input.setText(color.name())

    def _update_color_preview(self) -> None:
        color = QColor(self.color_input.text())
        if color.isValid():
            self.color_button.setStyleSheet(
                f"QPushButton {{ background-color: {color.name()}; color: white; }}"
            )
        else:
            self.color_button.setStyleSheet("")


class TaskDialog(QDialog):
    def __init__(self, store: KanbanDataStore, board_id: str, task_id: Optional[str] = None) -> None:
        super().__init__()
        self.store = store
        self.board_id = board_id
        self.task_id = task_id
        self.setWindowTitle("Task")
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.story_box = QComboBox()
        for story in self.store.stories.values():
            self.story_box.addItem(f"{story.code} — {story.title}", story.id)
        form.addRow("Story", self.story_box)
        self.title_input = QLineEdit()
        self.title_input.setPlaceholderText("Task title")
        form.addRow("Title", self.title_input)
        self.desc_input = QTextEdit()
        self.desc_input.setPlaceholderText(
            "Provide details, acceptance criteria, or links..."
        )
        form.addRow("Description", self.desc_input)
        self.priority_box = QComboBox()
        self.priority_box.setEditable(True)
        self.priority_box.addItems(["", "Low", "Medium", "High", "Critical"])
        form.addRow("Priority", self.priority_box)
        self.estimate_input = QLineEdit()
        self.estimate_input.setPlaceholderText("e.g., 3d, 8h")
        form.addRow("Estimate", self.estimate_input)
        self.due_checkbox = QCheckBox("Set due date")
        self.due_input = QDateEdit()
        self.due_input.setCalendarPopup(True)
        self.due_input.setDisplayFormat("yyyy-MM-dd")
        self.due_input.setDate(QDate.currentDate())
        self.due_input.setEnabled(False)
        self.due_checkbox.toggled.connect(self.due_input.setEnabled)
        due_row = QHBoxLayout()
        due_row.setContentsMargins(0, 0, 0, 0)
        due_row.addWidget(self.due_checkbox)
        due_row.addWidget(self.due_input)
        due_widget = QWidget()
        due_widget.setLayout(due_row)
        form.addRow("Due date", due_widget)
        self.tags_input = QLineEdit()
        self.tags_input.setPlaceholderText("frontend, urgent")
        form.addRow("Tags", self.tags_input)
        self.column_box = QComboBox()
        board = self.store.boards[self.board_id]
        for column in board.columns:
            self.column_box.addItem(column.name, column.id)
        form.addRow("Column", self.column_box)
        layout.addLayout(form)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        if task_id:
            self._load_task()

    def _load_task(self) -> None:
        task = self.store.tasks[self.task_id]  # type: ignore[index]
        self.story_box.setCurrentIndex(
            self.story_box.findData(task.story_id)
        )
        self.title_input.setText(task.title)
        self.desc_input.setPlainText(task.description)
        self.priority_box.setCurrentText(task.priority)
        self.estimate_input.setText(task.estimate)
        if task.due_date:
            parsed_date = QDate.fromString(task.due_date, "yyyy-MM-dd")
            if parsed_date.isValid():
                self.due_input.setDate(parsed_date)
                self.due_checkbox.setChecked(True)
            else:
                self.due_checkbox.setChecked(False)
                self.due_input.setDate(QDate.currentDate())
        else:
            self.due_checkbox.setChecked(False)
            self.due_input.setDate(QDate.currentDate())
        self.tags_input.setText(", ".join(task.tags))
        self.column_box.setCurrentIndex(self.column_box.findData(task.column_id))

    def _save(self) -> None:
        story_id = self.story_box.currentData()
        title = self.title_input.text().strip()
        column_id = self.column_box.currentData()
        if not story_id or not title:
            QMessageBox.warning(self, "Task", "Story and title are required.")
            return
        data = {
            "description": self.desc_input.toPlainText().strip(),
            "priority": self.priority_box.currentText().strip(),
            "estimate": self.estimate_input.text().strip(),
            "due_date": (
                self.due_input.date().toString("yyyy-MM-dd")
                if self.due_checkbox.isChecked()
                else None
            ),
            "tags": [tag.strip() for tag in self.tags_input.text().split(",") if tag.strip()],
        }
        if self.task_id:
            task = self.store.tasks[self.task_id]
            if task.story_id != story_id:
                task = self.store.rehome_task(task.id, story_id)
                self.task_id = task.id
            self.store.update_task(task.id, column_id=column_id, title=title, **data)
        else:
            self.store.create_task(
                board_id=self.board_id,
                column_id=column_id,
                story_id=story_id,
                title=title,
                **data,
            )
        self.accept()


class TaskDetailDialog(QDialog):
    def __init__(self, parent: QWidget, store: KanbanDataStore, task_id: str) -> None:
        super().__init__(parent)
        self.store = store
        self.task_id = task_id
        self.setWindowTitle("Task Detail")
        layout = QVBoxLayout(self)
        self.summary_label = QLabel()
        layout.addWidget(self.summary_label)

        self.comment_list = QListWidget()
        layout.addWidget(self.comment_list)

        comment_form = QHBoxLayout()
        self.comment_input = QLineEdit()
        self.comment_input.setPlaceholderText("Add a comment and press Enter")
        self.comment_input.returnPressed.connect(self._add_comment)
        comment_form.addWidget(self.comment_input)
        add_button = QPushButton("Add Comment")
        add_button.clicked.connect(self._add_comment)
        comment_form.addWidget(add_button)
        layout.addLayout(comment_form)

        self.history_box = QTextEdit()
        self.history_box.setReadOnly(True)
        layout.addWidget(self.history_box)

        self._refresh()

    def _refresh(self) -> None:
        task = self.store.tasks[self.task_id]
        story = self.store.stories.get(task.story_id)
        story_text = f"{story.code} ({story.color})" if story else "Unknown"
        due_text = f"<br/>Due: {task.due_date}" if task.due_date else ""
        self.summary_label.setText(
            f"<b>{task.id}</b> — {task.title}<br/>Story: {story_text}<br/>"
            f"Priority: {task.priority or 'Unspecified'}{due_text}"
        )
        self.comment_list.clear()
        for comment in self.store.comments_for_task(task.id):
            item = QListWidgetItem(f"[{comment.timestamp}] {comment.author}: {comment.body}")
            item.setData(Qt.ItemDataRole.UserRole, comment.id)
            self.comment_list.addItem(item)
        self.history_box.clear()
        for entry in task.history:
            self.history_box.append(
                f"[{entry.timestamp}] {entry.event_type}: {entry.payload}"
            )

    def _add_comment(self) -> None:
        text = self.comment_input.text().strip()
        if not text:
            return
        self.store.add_comment(self.task_id, APP_AUTHOR, text)
        self.comment_input.clear()
        self._refresh()


class MainWindow(QMainWindow):
    def __init__(self, store: KanbanDataStore) -> None:
        super().__init__()
        self.store = store
        self.setWindowTitle("Kanban Board")
        self.resize(1200, 800)
        self._init_ui()
        self._create_menus()

    def _init_ui(self) -> None:
        tabs = QTabWidget()
        self.board_view = BoardView(self.store)
        self.story_view = StoryView(self.store)
        self.weekly_view = WeeklyReviewView(self.store)
        tabs.addTab(self.board_view, "Kanban")
        tabs.addTab(self.story_view, "Stories")
        tabs.addTab(self.weekly_view, "Weekly Review")
        self.setCentralWidget(tabs)

    def _create_menus(self) -> None:
        toolbar = QToolBar("Main Toolbar")
        self.addToolBar(toolbar)
        import_action = toolbar.addAction("Import")
        import_action.triggered.connect(self._import_data)
        export_action = toolbar.addAction("Export")
        export_action.triggered.connect(self._export_data)
        toolbar.addSeparator()
        save_action = toolbar.addAction("Save")
        save_action.triggered.connect(self.store.save)

    def _import_data(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Import data", str(Path.home()), "Kanban export (*.json)"
        )
        if path:
            try:
                self.store.import_from(Path(path), merge=True)
            except ValueError as exc:
                QMessageBox.critical(self, "Import failed", str(exc))
            self.board_view.refresh_boards()
            self.story_view.refresh()

    def _export_data(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "Export data", str(Path.home() / "kanban_export.json"), "*.json"
        )
        if path:
            self.store.export_to(Path(path))
            QMessageBox.information(
                self, "Export", "Export completed successfully."
            )


def main() -> None:
    configure_logging(LOG_PATH)
    logging.info("Starting Kanban application")
    store = KanbanDataStore(DATA_PATH)
    app = create_application()
    window = MainWindow(store)
    window.show()
    app.exec()


if __name__ == "__main__":
    main()
