# AI Code Editor

A local-first desktop code editor with built-in AI assistant, powered by Cloudflare Workers AI.

## Features

- **Code Editor** — Syntax highlighting for Python / C++, line numbers, current line highlight, tabbed multi-file editing
- **AI Chat** — Streamed chat with context-aware AI (auto-includes current open file), powered by Cloudflare Workers AI
- **Run Code** — Execute Python (`.py`) and C++ (`.cpp` / `.c`) locally, output captured in real-time
- **Undo** — Full local history of every file create / modify / delete / rename. One-click undo the last action
- **No Cloud Storage** — Everything (files, history, undo) lives on your local disk. No KV, no R2, no database needed
- **Cloudflare Backend** — Lightweight Workers AI proxy backend, zero-dependency single route

## Project Structure

```
.
├── main.py                 # Entry point & main window (PySide6)
├── requirements.txt
├── app/
│   ├── editor.py           # Code editor widget (QSyntaxHighlighter)
│   ├── file_manager.py     # Left-side file tree
│   ├── history.py          # Local JSON snapshot history & undo
│   ├── runner.py           # subprocess code execution
│   ├── ai_client.py        # httpx SSE streaming to Cloudflare backend
│   └── icons/              # SVG icons
├── editor/                 # Cloudflare Workers backend (TypeScript)
│   ├── src/
│   │   ├── index.ts        # /api/chat route, SSE streaming
│   │   └── types.ts
│   └── package.json
└── History/                # Auto-generated local history snapshots
```

## Quick Start

### 1. Backend (Cloudflare Worker)

```bash
cd editor
npm install
npm run deploy
```

Set a `CF_API` environment variable in the Python app pointing to your Worker URL:

```bash
# Default: https://editor.zztxer.dpdns.org
export CF_API="https://your-worker.example.com"
```

### 2. Desktop App

```bash
pip install -r requirements.txt
python main.py
```

## Usage

- **AI Chat** — Type a message in the right panel → Enter or Send. The AI automatically sees your currently open file.
- **Apply Changes** — Ask the AI to create or modify files, then click Apply Changes to execute all operations.
- **Run** — Open a `.py` or `.cpp` file, press `Ctrl+R` or Edit → Run. Output appears in the bottom panel.
- **Undo** — `Ctrl+Z` (Edit → Undo Last Action) reverts the single most recent file operation tracked by history.

## Tech Stack

| Layer | Technology |
|---|---|
| Desktop GUI | PySide6 (Qt for Python) |
| HTTP Client | httpx (sync, SSE stream) |
| Code Execution | subprocess + threading |
| AI Backend | Cloudflare Workers AI (`@cf/meta/llama-3.1-8b-instruct-fp8`) |
| History | Local JSON snapshots on disk |

## Requirements

- Python 3.10+
- Node.js 18+ (for deploying the Worker backend)
- A Cloudflare account with Workers AI enabled