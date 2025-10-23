# Kanban Board Program — Requirements v0.1

> Purpose: Define clear, implementation‑agnostic requirements for a Python Kanban tool. No code here—just behavior.

---

## 1) Product Vision
A local, lightweight Kanban system where a single user can manage multiple boards, track color‑coded stories, create uniquely‑identified tasks under those stories, and comment on tasks. An optional plugin connects to a local LLM to generate weekly progress summaries from comments. Implemented in Python with a PyQt6 GUI. Python‑only; no npm/Node/JavaScript/TypeScript.

---

## 2) Scope
**In-scope**
- Local desktop usage (single user) with persistent storage.
- Desktop GUI built with **PyQt6** (no web stack).
- Multiple independent Kanban boards.
- Stories (a.k.a. epics) with color labels.
- Tasks (cards) that belong to exactly one story.
- Comments attached to tasks.
- Unique task IDs that encode their parent story.
- Basic filters/search.
- Import/export.
- Optional LLM summary plugin for weekly progress.

**Out-of-scope (v1)**
- Multi-user collaboration, permissions, and sync.
- Real-time networking.
- Complex automations or web integrations.

---

## 3) Core Concepts & Definitions
- **Board**: A workspace with ordered columns representing workflow states (e.g., Backlog, In Progress, Done).
- **Column**: A status lane within a board. Cards can be moved between columns.
- **Story**: A thematic container (epic). Has a short code, title, description, color, and status.
- **Task (Card)**: A unit of work that belongs to one story and appears in a column on a board.
- **Comment**: A timestamped note attached to a task, authored by the user.
- **LLM Weekly Summary**: A generated report of progress for a selected week/time window derived from comments and task state changes.

---

## 4) Functional Requirements

### 4.1 Boards
- Create, rename, archive, and delete boards.
- Each board has an ordered list of columns; user can add, rename, reorder, and remove columns.
- Moving tasks between columns updates their status history with a timestamp.
- Board-level settings: default columns, WIP notes/help text, color legend visibility.

**Acceptance checks**
- Creating a board produces an empty board with default columns.
- Reordering columns persists after app restart.
- Archiving hides the board from primary lists but preserves data.

### 4.2 Stories (Color‑coded)
- Create, edit, archive, and delete stories.
- Required fields: story code, title. Optional: description, color, tags, status.
- Color must appear on story badges and on all tasks belonging to that story (e.g., a colored strip or dot).
- Story status options: Planned, Active, Blocked, Done (configurable set is acceptable if consistent).

**Acceptance checks**
- Changing a story’s color updates all associated tasks’ visual markers.
- Archiving a story hides it in selectors but leaves tasks intact (until explicitly removed).

### 4.3 Unique IDs for Tasks (Story‑based)
- Each task ID must be globally unique and encode its parent story’s code.
- ID format requirement: `<STORY_CODE>-<sequence_number>` where sequence resets per story and is zero‑padded to at least 3 digits.
- IDs are immutable once assigned.

**Acceptance checks**
- Creating three tasks under story `ALPHA` yields `ALPHA-001`, `ALPHA-002`, `ALPHA-003`.
- Moving a task to another story is disallowed unless explicitly supported by a “rehome” action that assigns a **new** ID in the target story and records linkage to the old ID.

### 4.4 Tasks (Cards)
- Create, edit, move, archive, and delete tasks.
- Required fields: parent story, title. Optional: description, priority, estimate, due date, tags.
- Tasks exist on one board at a time; moving across boards is a deliberate action.
- Task history records: creation, column moves (with timestamps), story changes (if allowed), and archival.

**Acceptance checks**
- Dragging a task between columns updates its status history.
- Archiving a task removes it from board view but preserves for search/export.

### 4.5 Comments on Tasks
- Add, edit, and delete comments on tasks.
- Each comment stores: task ID, timestamp, author (default local user), and body.
- Comments are immutable by default; if edits are allowed, retain edit history (timestamp + prior text).

**Acceptance checks**
- Comments display chronologically with timestamps.
- Deleting a comment removes it from task view and future summaries.

### 4.6 Views & Navigation
- **Kanban View**: Board columns with draggable task cards; color markers for stories visible on cards.
- **Story View**: List all stories with counts of tasks by status; click through to story details and related tasks.
- **Task Detail**: Full task metadata + comments + history timeline.
- **Weekly Review View**: Select a date range; see tasks moved/updated in that window and relevant comments.

**Acceptance checks**
- Story color appears consistently in all views where related tasks appear.
- Weekly Review View filters by the chosen date window.

### 4.7 Search, Filter, and Sort
- Search across titles/descriptions for boards, stories, tasks.
- Filters: by story, column/status, tags, date ranges, and text query.
- Sorting options: by priority, due date, last updated.

**Acceptance checks**
- Combined filter + search narrows results correctly.
- Filters persist until cleared or app is closed (choose one behavior and keep it consistent).

### 4.8 Import/Export
- Export boards, stories, tasks, and comments to a portable format (e.g., JSON or CSV for tabular subsets).
- Import supports creating new entities or merging into existing ones with conflict prompts.
- Export should include a minimal schema version header for compatibility checks.

**Acceptance checks**
- Exporting then re‑importing reproduces the same entities and relationships.
- Version mismatch triggers a clear message to the user.

### 4.9 Local LLM Weekly Summary Plugin (Optional)
**Goal**: Generate a weekly summary of progress from comments and task changes, locally.

**Inputs**
- Date range (default: prior Monday–Sunday).
- Board(s) and/or story selection.
- Aggregated comment text and task history entries within the range.

**Processing Requirements**
- Summarize key developments by story, referencing task IDs.
- Highlight tasks started, progressed (column changes), and completed within the period.
- Extract notable blockers and decisions from comments.
- Keep output concise and structured (headings + bullet points), with a short executive summary first.
- All inference occurs locally using a user‑selected model.
- No external network calls without explicit user consent.

**Outputs**
- A markdown summary document with sections: Executive Summary, Highlights by Story, Completed Tasks, Blockers/Risks, Next Likely Steps (inferred).
- Optional attachment of the raw evidence appendix: list of included comments and history entries (with timestamps and IDs).

**Controls**
- Preview before saving.
- Regenerate with different temperature/length settings.
- Save destination: file (markdown) and/or attach to a “Weekly Review” record inside the app.

**Acceptance checks**
- Selecting a week with no activity produces a clear “no material changes” report.
- Summary references task IDs (e.g., `ALPHA-003`) when citing work.

---

## 5) Data & Identity Rules (Implementation‑agnostic)
- All entities (board, column, story, task, comment) have stable unique identifiers.
- Referential integrity: Tasks must reference an existing story and board; comments must reference an existing task.
- Deletions obey safety rules: hard delete is irreversible and must be gated by confirmation; archive preserves linkage.
- Timestamps use a single consistent timezone strategy (document the chosen one and apply everywhere).
- History is append‑only; edits create new history entries rather than overwriting prior state (except hard delete).

---

## 6) Non‑Functional Requirements
- **Performance**: Moving a card or adding a comment should feel instantaneous on typical hardware.
- **Portability**: Runs on Windows/macOS/Linux.
- **Resilience**: App should recover to a consistent state after an abrupt shutdown; no data loss beyond the last confirmed action.
- **Privacy**: All data stored locally by default; no telemetry or network calls without explicit opt‑in.
- **Extensibility**: Clear plugin surface for the LLM summary feature and future plugins (metrics, burndown, etc.).
- **Technology constraints**: Python 3.x; PyQt6 GUI; Python packages via pip only; **no** npm/Node/JavaScript/TypeScript; no browser-dependent frameworks.

---

## 7) Plugin Surface (for LLM & Future Plugins)
- Discoverable via a plugins directory with manifest files describing name, capabilities, input/output contracts, and required settings.
- Standardized I/O contract for summaries: inputs (entity IDs, date range, evidence bundle), outputs (markdown report + metadata).
- Permissions prompt when a plugin requests outside resources (e.g., filesystem paths, models).
- Error reporting: human‑readable messages and a log entry with context.

---

## 8) UX Requirements (Behavioral)
- Drag‑and‑drop tasks between columns with visual feedback.
- Clear color legend for stories, accessible from board and story views.
- Quick create affordances: new story, new task in a column, new comment from task detail.
- Keyboard navigation for common actions (new task, move focus between columns, open detail).
- Undo for last destructive or move action where feasible (e.g., column move).

---

## 9) Telemetry & Logging (Local)
- Local, rotating activity log for debugging (board/story/task IDs, actions, timestamps).
- No data leaves the machine by default.

---

## 10) Acceptance Test Scenarios (High‑level)
1. **Multi‑Board**: Create two boards; ensure tasks from board A never appear on board B unless explicitly moved.
2. **Story Color**: Change a story color; verify all associated tasks reflect the new color in all views.
3. **ID Scheme**: Create tasks under a story; confirm sequential IDs and immutability.
4. **Comments**: Add, edit (if allowed), and delete comments; confirm summary excludes deleted comments.
5. **Weekly Summary**: Generate a summary for a week with varied activity; verify correct inclusion of tasks and comments, proper structure, and references.
6. **Import/Export**: Round‑trip data; verify structural integrity and IDs unchanged.

---

## 11) Roadmap Hints (Optional Next)
- Cross‑board swimlanes by story.
- Simple metrics: throughput, lead time, done per week.
- Calendar view with due dates.
- Basic blockers/dep tracking between tasks.

---

**End of v0.1**
