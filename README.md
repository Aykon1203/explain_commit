# 🔍 `git-explain` / `explain-commit`

An ultra-fast, intelligent CLI tool that explains code changes using AI in real time. Run a single simple command and get an instant, clear breakdown of:
- **Commits about to be pushed** (local commits ahead of origin/upstream)
- **Uncommitted changes** in your working directory (staged, unstaged, and untracked files)
- **The latest pushed or HEAD commit**
- **Any specific commit hash, tag, or branch range**

---

## ⚡ Speed & Performance Highlights

- ⚡ **Real-time Token Streaming**: Output streams live onto your terminal chunk-by-chunk. You see words appearing within seconds rather than waiting for the whole prompt to finish.
- ⚡ **Fast Low-Latency Model by Default**: Runs on `gemini-3.8-flash-low` with low reasoning effort for maximum speed and minimal token bloat.
- ⚡ **Instant Caching**: Once an explanation is generated for a commit/diff, subsequent runs on the same state return in **0.01 seconds** (`⚡ CACHED`).
- ⚡ **Smart Noise Filtering**: Automatically omits lockfiles (`package-lock.json`, `pnpm-lock.yaml`, `yarn.lock`, `Cargo.lock`, etc.) and truncates huge diffs to keep time-to-first-token ultra fast.

---

## ⚡ Quick Start

From **any** Git repository on your machine:

```bash
git explain
# or
explain-commit
```

### 🧠 Smart Auto-Detection

When run without flags, `git explain` automatically detects your repository's state:

| Repository State | Action Taken |
| :--- | :--- |
| **Uncommitted changes present** | Explains modified files in your working directory (staged + unstaged) |
| **Working tree clean + unpushed commits** | Explains the commit(s) you are about to push to remote |
| **Working tree clean + all commits pushed** | Explains the most recent commit (`HEAD`) |

---

## 🚀 Common Commands

### 1. Explain Changes You Haven't Committed Yet
```bash
git explain --uncommitted    # or: git explain -u
git explain --staged         # or: git explain -s (only staged changes)
```

### 2. Explain Commit(s) About To Be Pushed
```bash
git explain --push           # or: git explain -p
```
*Analyzes all commits on your current branch that haven't been pushed to the remote branch yet.*

### 3. Explain the Latest Commit
```bash
git explain --latest         # or: git explain -l
```

### 4. Interactive Target Picker
```bash
git explain -i               # or: git explain --interactive
```
Displays an interactive menu with change counts:
```
? What would you like to explain?

  [1] Uncommitted changes (2 staged, 1 unstaged, 0 untracked)
  [2] Staged changes only (2 files ready to commit)
  [3] Commit(s) about to be pushed (1 commit ahead of origin/main)
  [4] Latest commit (HEAD: a1b2c3d 'feat: add auth')
  [5] Select from recent commit history
```

### 5. Explain Any Specific Commit or Branch Diff
```bash
git explain a1b2c3d          # Explain a specific commit
git explain HEAD~1           # Explain the previous commit
git explain main..feature    # Explain all changes between two branches
```

### 6. Copy Explanation to Clipboard
```bash
git explain --copy           # or: git explain -c
```
Automatically copies the AI explanation to your system clipboard (`pbcopy` on macOS).

### 7. Choose Speed / Depth
```bash
git explain --brief          # or: -b (ultra-fast 2-sentence summary)
git explain                  # (Default: fast, high-signal 3-point breakdown)
git explain --detailed       # or: -d (in-depth walkthrough with test recommendations)
git explain --deep           # Enables high-effort reasoning model for complex architectural reviews
git explain --no-cache       # Bypasses local cache to force a fresh AI analysis
```

---

## 🛠️ Options & Flags Reference

```
usage: git explain [-h] [-u] [-s] [-p] [-l] [-i] [-b] [-d] [--deep] [--no-cache]
                   [-c] [--raw] [-e {agy,gemini,openai,ollama,offline}] [target]

Target Selection:
  -u, --uncommitted     Explain uncommitted changes in working tree
  -s, --staged          Explain only staged changes
  -p, --push, --unpushed
                        Explain commit(s) about to be pushed
  -l, --latest, --head  Explain latest commit (HEAD)
  -i, --interactive     Interactively choose what to explain
  [target]              Positional target: 'uncommitted', 'staged', 'push', 'latest',
                        or commit ref (e.g. HEAD~1, a1b2c3d, main..feature)

Performance & Detail:
  -b, --brief           Ultra-fast 2-sentence summary
  -d, --detailed        Detailed walkthrough with testing suggestions
  --deep                Enable high-effort reasoning model (takes longer)
  --no-cache            Bypass local cache and regenerate fresh explanation

Options:
  -c, --copy            Copy the generated explanation to clipboard
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
