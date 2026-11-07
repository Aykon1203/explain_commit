# 🔍 `git-explain` / `explain-commit`

An ultra-fast, intelligent CLI tool that explains code changes and source files using AI in real time. Run a single simple command and get an instant, clear breakdown of:
- **Files in your codebase** (`--file` / `-f`): explains how the file, its classes, and functions work
- **Commits about to be pushed** (local commits ahead of origin/upstream)
- **Uncommitted changes** in your working directory (staged, unstaged, and untracked files)
- **The latest pushed or HEAD commit**
- **Any specific commit hash, tag, or branch range**

---

## ⚡ Speed & Formatting Highlights

- ⚡ **Real-time Token Streaming**: Words stream onto your terminal live as they are generated.
- 🎨 **Native Terminal Formatting**: Asterisks are stripped and rendered in real **bold text** (`\033[1m`), `code` in cyan highlights, headers in styled titles, and clean bullet lists.
- ⚡ **Instant Caching**: Once an explanation is generated for a file or commit, repeat runs return in **0.01 seconds** (`⚡ CACHED`).
- ⚡ **Fast Low-Latency Model by Default**: Runs on `gemini-3.8-flash-low` with low reasoning effort for maximum speed.
- ⚡ **Smart Noise Filtering**: Automatically omits lockfiles (`package-lock.json`, `pnpm-lock.yaml`, `yarn.lock`, etc.) to keep token overhead minimal.

---

## ⚡ Quick Start

From **any** Git repository on your machine:

```bash
git explain
# or
explain-commit
```

---

## 🚀 Common Commands

### 1. Explain a File and Its Functions (NEW ✨)
Explain how the code, classes, and functions in a specific codebase file work:
```bash
git explain -f src/auth.py
# or with --file:
git explain --file src/auth.py
# or simply pass the file path directly:
git explain src/auth.py
```

### 2. Explain Changes You Haven't Committed Yet
```bash
git explain --uncommitted    # or: git explain -u
git explain --staged         # or: git explain -s (only staged changes)
```

### 3. Explain Commit(s) About To Be Pushed
```bash
git explain --push           # or: git explain -p
```
*Analyzes all commits on your current branch that haven't been pushed to the remote branch yet.*

### 4. Explain the Latest Commit
```bash
git explain --latest         # or: git explain -l
```

### 5. Interactive Target Picker
```bash
git explain -i               # or: git explain --interactive
```
Displays an interactive menu with change counts and file selection:
```
? What would you like to explain?

  [1] Uncommitted changes (2 staged, 1 unstaged, 0 untracked)
  [2] Staged changes only (2 files ready to commit)
  [3] Commit(s) about to be pushed (1 commit ahead of origin/main)
  [4] Latest commit (HEAD: a1b2c3d 'feat: add auth')
  [5] Select from recent commit history
  [6] Explain a specific file and its functions
```

### 6. Explain Any Specific Commit or Branch Diff
```bash
git explain a1b2c3d          # Explain a specific commit
git explain HEAD~1           # Explain the previous commit
git explain main..feature    # Explain all changes between two branches
```

### 7. Copy Explanation to Clipboard
```bash
git explain --copy           # or: git explain -c
```
Automatically copies clean raw Markdown to your system clipboard (`pbcopy` on macOS). Perfect for pasting into GitHub PRs, Notion, or Slack.

### 8. Choose Speed / Depth
```bash
git explain --brief          # or: -b (ultra-fast 2-sentence summary)
git explain                  # (Default: fast, high-signal structured breakdown)
git explain --detailed       # or: -d (in-depth walkthrough with testing recommendations)
git explain --deep           # Enables high-effort reasoning model for complex codebases
git explain --no-cache       # Bypasses local cache to force a fresh AI analysis
```

---

## 🛠️ Options & Flags Reference

```
usage: git explain [-h] [-u] [-s] [-p] [-l] [-f FILE] [-i] [-b] [-d] [--deep]
                   [--no-cache] [-c] [--raw] [-e {agy,gemini,openai,ollama,offline}]
                   [target]

Target Selection:
  -f, --file FILE       Explain code, classes, and functions inside a specific file
  -u, --uncommitted     Explain uncommitted changes in working tree
  -s, --staged          Explain only staged changes
  -p, --push, --unpushed
                        Explain commit(s) about to be pushed
  -l, --latest, --head  Explain latest commit (HEAD)
  -i, --interactive     Interactively choose what to explain
  [target]              Positional target: file path, 'uncommitted', 'staged',
                        'push', 'latest', or commit ref (e.g. HEAD~1, a1b2c3d)

Performance & Detail:
  -b, --brief           Ultra-fast 2-sentence summary
  -d, --detailed        Detailed walkthrough with testing suggestions
  --deep                Enable high-effort reasoning model (takes longer)
  --no-cache            Bypass local cache and regenerate fresh explanation

Options:
  -c, --copy            Copy the generated clean markdown explanation to clipboard
  --raw                 Output raw markdown (no ANSI colors)
  -e, --backend         AI backend: agy (default), gemini, openai, ollama, offline
```

---

## 📦 Installation & Symlinks

The script is already symlinked to your PATH:
- `~/.local/bin/git-explain` (invoked via `git explain`)
- `~/.local/bin/explain-commit` (invoked via `explain-commit`)

To reinstall at any time:
```bash
cd /Users/Aykon/Documents/WERK/EIGEN/explain_commit
./install.sh
```
