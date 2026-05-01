# Promptee TUI Design

## Overview

Promptee is a terminal-based intelligent prompt recommendation engine. The default experience is an interactive TUI inspired by Claude Code's UX. Agent mode and direct subcommands are available for scripting.

## Entry Modes

| Invocation | Mode | Behavior |
|---|---|---|
| `./promptee` | TUI | Launch Bubble Tea interface, interactive session |
| `./promptee -agent "query"` | Agent | No TUI, single string flag argument, stdout in tabwriter format, scriptable. Add `--json` for JSON output. |
| `./promptee recommend "query"` | Direct | Single Cobra subcommand execution, no TUI |

The root command with no args/flags launches the TUI. The `-agent` flag suppresses the TUI and processes a single query. Existing Cobra subcommands (`health`, `recommend`, `ingest`, `telemetry`, `feedback`, `daemon`) remain available for direct execution.

## Architecture

```
cmd/promptee/main.go          — entry point, mode routing
internal/tui/
  model.go                    — Bubble Tea Model (root state machine)
  view.go                     — layout rendering (header + transcript + status + input)
  update.go                   — message handling (key, tick, API result, command dispatch)
  commands.go                 — /command dispatch, API command wrappers
  transcript.go               — ordered segment buffer (ThinkingSegment, TextSegment, etc.)
  spinner.go                  — cogitating messages, event-to-emoji mapping
  styles.go                   — lipgloss style definitions
  keys.go                     — key bindings
```

All TUI code lives in `internal/tui/`. The existing Cobra subcommands in `main.go` remain untouched; the root command's `Run` function dispatches to TUI, agent, or subcommand based on flags.

## Cogitating Status System

Rotating playful messages during API calls, drawn from Claude Code's event-driven status pattern.

**Messages (rotate on spinner tick):**
- Cogitating...
- Pontificating...
- Ruminating...
- Deliberating...
- Pondering...
- Meditating...
- Percolating...
- Marinating...

**Event-to-emoji+label mapping:**

| Event | Emoji | Label |
|---|---|---|
| API call in flight | spinner | Rotating cogitating message |
| Tool call detected | 🛠 | Tool call: {name} |
| Recommendations arriving | 💡 | Recommending... |
| Ingest running | 📥 | Ingesting... |
| Error | ⚠️ | Error: {message} |
| Complete | ✅ | Done |

The status bar displays the current emoji + label, updating in real-time as events stream.

## Transcript Model

Ordered, append-only segments that render progressively in the viewport. Mirrors the TranscriptBuffer pattern from free-claude-code.

**Segment types:**

| Type | Render |
|---|---|
| `ThinkingSegment` | 💭 **Thinking** (truncated tail) |
| `TextSegment` | Markdown rendered text |
| `ToolCallSegment` | 🛠 **Tool call:** `name` |
| `ToolResultSegment` | 📤 **Tool result/error:** `name` + code block |
| `RecommendSegment` | 💡 Ranked list with scores, variables, AddOns |
| `ErrorSegment` | ⚠️ **Error:** `message` |

Segments are appended as API events arrive. The viewport auto-scrolls to the latest content. Older segments are truncated from the top when content exceeds the character limit.

## Throttled Updates

UI re-renders are throttled to 1-second intervals using Bubble Tea's `Tick` command. Rapid API response events are batched and flushed on tick, preventing flicker on fast streams.

## Slash Commands

Dispatched from the input zone. Plain text without `/` prefix sends as a recommend query.

| Command | Action |
|---|---|
| `/ingest <path>` | Ingest file/directory into vector store |
| `/telemetry` | Show telemetry stats for last session |
| `/feedback <text>` | Submit feedback |
| `/daemon start/stop/status` | Manage backend daemon |
| `/health` | Check backend health |
| `/clear` | Clear transcript viewport |
| `/help` | Show available commands |
| `/quit` or Ctrl+C | Exit TUI |

## Layout

Three zones rendered top-to-bottom:

```
┌─────────────────────────────────────────┐
│ Promptee v0.1 [🟢 Online]              │  header
├─────────────────────────────────────────┤
│ 💭 Thinking...                          │
│ 🛠 Tool call: recommend                │  transcript viewport
│ 💡 Top 5 recommendations:              │  (auto-scrolling,
│  1. [0.92] "Write a REST API"          │   segments grow)
│    Variables: [LANGUAGE], [FRAMEWORK]  │
│  2. [0.87] "Debug error in..."         │
│                                         │
│ ✅ Cogitating... Pontificating...       │  status bar
├─────────────────────────────────────────┤
│ > type query or /command...             │  input (textarea)
│                                         │
└─────────────────────────────────────────┘
```

**Header:** App name, version, backend status indicator (🟢 Online / 🔴 Offline). If backend is offline when a query is submitted, an ErrorSegment displays in the transcript with guidance to run `/daemon start`.
**Transcript:** Scrollable viewport showing all segments. Auto-scrolls to bottom on new content. User can scroll up with mouse or Page Up.
**Status bar:** Current cogitating message + emoji, or final status (✅ Done, ⚠️ Error).
**Input:** Bubbles textarea component. Enter submits. Up/Down navigate history.

## Interaction Flows

### Recommend Flow
1. User types query in input zone → Enter
2. Status bar: spinner + "Cogitating..."
3. Transcript: 🛠 Tool call: recommend segment appended
4. API returns → RecommendSegment appended with ranked results
5. User selects result (number key or click) → variables highlighted
6. Input zone switches to variable-fill mode: "Fill [LANGUAGE]:"
7. Each variable filled advances to the next
8. Final assembled prompt displayed in transcript
9. Status: "📋 Copied to clipboard"
10. Telemetry recorded automatically

### Ingest Flow
1. User types `/ingest ./prompts` → Enter
2. Status bar: "📥 Ingesting..."
3. Progress segments append as files are processed
4. Transcript: "✅ Ingested 42 prompts"

### Agent Flow
1. `./promptee -agent "write a REST API in Go"`
2. No TUI launches
3. Query sent to API, results printed to stdout in tabwriter table format (same as existing `recommend` subcommand). Add `--json` flag for machine-readable JSON output.
4. Exit code 0 on success, non-zero on error

## Variable Filling

After selecting a recommendation, the TUI enters variable-fill mode:
- `[VARIABLE]` placeholders are extracted from the prompt template
- Input zone prompts for each variable sequentially
- Tab advances to next variable
- Enter confirms all and assembles the final prompt
- Assembled prompt is copied to clipboard

## Styling

Lipgloss styling inspired by Claude Code's terminal aesthetic:
- Dark background optimized (respects terminal theme)
- Bold headings for segment types
- Muted colors for meta info (scores, IDs)
- Accent color for interactive elements (selected item, cursor)
- Code-block rendering for tool results
- Consistent emoji prefix per segment type

## Key Bindings

| Key | Action |
|---|---|
| Enter | Submit query or command |
| Ctrl+C / `/quit` | Exit TUI |
| Up/Down | Scroll transcript / navigate history |
| Tab | In variable-fill mode: advance to next variable |
| Esc | Cancel current input / exit variable-fill mode |
| Page Up/Down | Scroll transcript viewport |
| 1-9 | Select recommendation by number |

## Technical Stack

- **bubbletea** — core TUI framework (elm architecture: model/view/update)
- **lipgloss** — terminal styling and layout
- **bubbles/textarea** — multi-line input component
- **bubbles/viewport** — scrollable transcript display
- **bubbles/spinner** — animated cogitating indicator
- **bubbles/table** — recommendation result table (optional)

## Dependencies to Add

```
github.com/charmbracelet/bubbletea
github.com/charmbracelet/lipgloss
github.com/charmbracelet/bubbles
```
