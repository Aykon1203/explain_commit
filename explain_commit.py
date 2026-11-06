#!/usr/bin/env python3
"""
git-explain / explain-commit
A fast, intelligent CLI tool that uses AI to explain code changes in real time:
  - Commits you are about to push (ahead of remote)
  - Changes that haven't been committed yet (staged/unstaged)
  - The latest pushed or HEAD commit
  - Any specific commit hash or branch range
"""

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from typing import Callable, Dict, Generator, List, Optional, Tuple

# ANSI color codes
class Colors:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    ITALIC = "\033[3m"
    UNDERLINE = "\033[4m"
    
    # Colors
    BLUE = "\033[38;5;39m"
    CYAN = "\033[38;5;51m"
    GREEN = "\033[38;5;82m"
    YELLOW = "\033[38;5;220m"
    ORANGE = "\033[38;5;208m"
    RED = "\033[38;5;196m"
    PURPLE = "\033[38;5;141m"
    GRAY = "\033[38;5;244m"
    WHITE = "\033[38;5;255m"

def is_color_enabled(raw: bool = False) -> bool:
    if raw or os.environ.get("NO_COLOR"):
        return False
    return sys.stdout.isatty()

def style(text: str, *styles: str, raw: bool = False) -> str:
    if not is_color_enabled(raw):
        return text
    return "".join(styles) + text + Colors.RESET

# Cache directory
CACHE_DIR = os.path.expanduser("~/.cache/git-explain")

def get_cache_path(cache_key: str) -> str:
    os.makedirs(CACHE_DIR, exist_ok=True)
    return os.path.join(CACHE_DIR, f"{cache_key}.txt")

def read_cache(cache_key: str, max_age_seconds: int = 86400) -> Optional[str]:
    path = get_cache_path(cache_key)
    if os.path.exists(path):
        try:
            mtime = os.path.getmtime(path)
            if time.time() - mtime < max_age_seconds:
                with open(path, "r", encoding="utf-8") as f:
                    return f.read()
        except Exception:
            pass
    return None

def write_cache(cache_key: str, content: str):
    try:
        path = get_cache_path(cache_key)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
    except Exception:
        pass

# Lockfiles and generated files to omit or summarize from prompt
IGNORED_PATTERNS = [
    r"package-lock\.json$",
    r"yarn\.lock$",
    r"pnpm-lock\.yaml$",
    r"poetry\.lock$",
    r"Pipfile\.lock$",
    r"Cargo\.lock$",
    r"composer\.lock$",
    r"go\.sum$",
    r"flake\.lock$",
    r"\.min\.js$",
    r"\.min\.css$",
    r"\.map$",
]

def is_lockfile_or_generated(path: str) -> bool:
    for pattern in IGNORED_PATTERNS:
        if re.search(pattern, path, re.IGNORECASE):
            return True
    return False

# Real-time Stream Spinner
class StreamSpinner:
    FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
    
    def __init__(self, message: str = "Analyzing code with AI...", enabled: bool = True):
        self.message = message
        self.enabled = enabled and sys.stdout.isatty()
        self.running = False
        self.thread = None

    def _spin(self):
        idx = 0
        while self.running:
            frame = self.FRAMES[idx % len(self.FRAMES)]
            idx += 1
            sys.stdout.write(f"\r{Colors.CYAN}{frame}{Colors.RESET} {style(self.message, Colors.DIM)}")
            sys.stdout.flush()
            time.sleep(0.08)
        sys.stdout.write("\r\033[K")  # Clear line
        sys.stdout.flush()

    def start(self):
        if not self.enabled:
            return
        self.running = True
        self.thread = threading.Thread(target=self._spin, daemon=True)
        self.thread.start()

    def stop(self):
        if not self.running:
            return
        self.running = False
        if self.thread:
            self.thread.join(timeout=0.5)
        sys.stdout.write("\r\033[K")
        sys.stdout.flush()

# Git interaction helpers
class GitRepo:
    def __init__(self, cwd: Optional[str] = None):
        self.cwd = cwd or os.getcwd()
        self.root = self._get_repo_root()
        if not self.root:
            raise RuntimeError("Current directory is not inside a Git repository.")

    def _run_git(self, args: List[str], check: bool = False) -> Tuple[int, str, str]:
        p = subprocess.run(
            ["git"] + args,
            cwd=self.cwd,
            capture_output=True,
            text=True
        )
        if check and p.returncode != 0:
            raise RuntimeError(f"Git command failed: git {' '.join(args)}\n{p.stderr.strip()}")
        return p.returncode, p.stdout.strip(), p.stderr.strip()

    def _get_repo_root(self) -> Optional[str]:
        code, out, _ = self._run_git(["rev-parse", "--show-toplevel"])
        return out if code == 0 else None

    def get_current_branch(self) -> str:
        code, out, _ = self._run_git(["rev-parse", "--abbrev-ref", "HEAD"])
        return out if code == 0 else "HEAD"

    def get_upstream_branch(self) -> Optional[str]:
        code, out, _ = self._run_git(["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"])
        if code == 0 and out:
            return out
        branch = self.get_current_branch()
        code, out, _ = self._run_git(["rev-parse", "--verify", f"origin/{branch}"])
        if code == 0:
            return f"origin/{branch}"
        return None

    def has_commits(self) -> bool:
        code, _, _ = self._run_git(["rev-parse", "--verify", "HEAD"])
        return code == 0

    def get_status_summary(self) -> Dict[str, any]:
        code, out, _ = self._run_git(["status", "--porcelain=v1"])
        staged = []
        unstaged = []
        untracked = []

        if code == 0 and out:
            for line in out.splitlines():
                if len(line) < 3:
                    continue
                index_status = line[0]
                worktree_status = line[1]
                path = line[3:].strip()
                if " -> " in path:
                    path = path.split(" -> ")[1].strip()

                if line.startswith("??"):
                    untracked.append(path)
                else:
                    if index_status not in (" ", "?"):
                        staged.append((index_status, path))
                    if worktree_status not in (" ", "?"):
                        unstaged.append((worktree_status, path))

        return {
            "staged": staged,
            "unstaged": unstaged,
            "untracked": untracked,
            "has_uncommitted": bool(staged or unstaged or untracked),
        }

    def get_unpushed_commits(self) -> List[Tuple[str, str]]:
        if not self.has_commits():
            return []

        upstream = self.get_upstream_branch()
        ref_range = None
        if upstream:
            ref_range = f"{upstream}..HEAD"
        else:
            for candidate in ["origin/main", "origin/master", "origin/dev"]:
                code, _, _ = self._run_git(["rev-parse", "--verify", candidate])
                if code == 0:
                    code_mb, mb, _ = self._run_git(["merge-base", "HEAD", candidate])
                    if code_mb == 0 and mb:
                        ref_range = f"{mb}..HEAD"
                        break

        if not ref_range:
            code, count_str, _ = self._run_git(["rev-list", "--count", "HEAD"])
            if code == 0 and count_str.isdigit() and int(count_str) > 0:
                code, out, _ = self._run_git(["log", "-1", "--oneline"])
                if code == 0 and out:
                    parts = out.split(" ", 1)
                    return [(parts[0], parts[1] if len(parts) > 1 else "")]
            return []

        code, out, _ = self._run_git(["log", "--oneline", ref_range])
        if code != 0 or not out:
            return []

        commits = []
        for line in out.splitlines():
            parts = line.split(" ", 1)
            commits.append((parts[0], parts[1] if len(parts) > 1 else ""))
        return commits

    def get_latest_commit(self) -> Optional[Tuple[str, str]]:
        if not self.has_commits():
            return None
        code, out, _ = self._run_git(["log", "-1", "--format=%h %s"])
        if code == 0 and out:
            parts = out.split(" ", 1)
            return (parts[0], parts[1] if len(parts) > 1 else "")
        return None

    def get_recent_commits(self, limit: int = 8) -> List[Tuple[str, str]]:
        if not self.has_commits():
            return []
        code, out, _ = self._run_git(["log", f"-{limit}", "--oneline"])
        commits = []
        if code == 0 and out:
            for line in out.splitlines():
                parts = line.split(" ", 1)
                commits.append((parts[0], parts[1] if len(parts) > 1 else ""))
        return commits

    def get_uncommitted_diff(self, staged_only: bool = False, unstaged_only: bool = False, include_untracked: bool = True) -> Tuple[str, str]:
        if staged_only:
            _, stat, _ = self._run_git(["diff", "--cached", "--stat"])
            _, diff, _ = self._run_git(["diff", "--cached"])
        elif unstaged_only:
            _, stat, _ = self._run_git(["diff", "--stat"])
            _, diff, _ = self._run_git(["diff"])
        else:
            if self.has_commits():
                _, stat, _ = self._run_git(["diff", "HEAD", "--stat"])
                _, diff, _ = self._run_git(["diff", "HEAD"])
            else:
                _, stat, _ = self._run_git(["diff", "--cached", "--stat"])
                _, diff, _ = self._run_git(["diff", "--cached"])

        if include_untracked and not staged_only:
            status = self.get_status_summary()
            untracked = status["untracked"]
            untracked_diffs = []
            for ufile in untracked[:8]:
                full_path = os.path.join(self.root, ufile)
                if os.path.isfile(full_path) and os.path.getsize(full_path) < 25_000:
                    try:
                        with open(full_path, "r", encoding="utf-8", errors="ignore") as f:
                            content = f.read()
                        untracked_diffs.append(
                            f"diff --git a/{ufile} b/{ufile}\nnew file mode 100644\n--- /dev/null\n+++ b/{ufile}\n" +
                            "\n".join("+" + line for line in content.splitlines()[:200])
                        )
                    except Exception:
                        pass
            if untracked_diffs:
                diff = (diff + "\n\n" + "\n\n".join(untracked_diffs)).strip()
                stat = (stat + f"\n + {len(untracked)} untracked file(s)").strip()

        return stat, diff

    def get_unpushed_diff(self) -> Tuple[str, str, str]:
        upstream = self.get_upstream_branch()
        ref_range = None
        desc = ""
        if upstream:
            ref_range = f"{upstream}..HEAD"
            desc = f"Unpushed commit(s) ahead of {upstream}"
        else:
            for candidate in ["origin/main", "origin/master"]:
                code, _, _ = self._run_git(["rev-parse", "--verify", candidate])
                if code == 0:
                    code_mb, mb, _ = self._run_git(["merge-base", "HEAD", candidate])
                    if code_mb == 0 and mb:
                        ref_range = f"{mb}..HEAD"
                        desc = f"Unpushed commit(s) ahead of {candidate}"
                        break

        if not ref_range:
            return self.get_commit_diff("HEAD")

        _, stat, _ = self._run_git(["diff", "--stat", ref_range])
        _, diff, _ = self._run_git(["log", "-p", "--stat", ref_range])
        return desc, stat, diff

    def get_commit_diff(self, ref: str) -> Tuple[str, str, str]:
        if ".." in ref:
            _, stat, _ = self._run_git(["diff", "--stat", ref])
            _, diff, _ = self._run_git(["log", "-p", "--stat", ref])
            return f"Commit range {ref}", stat, diff

        code, header, _ = self._run_git(["log", "-1", "--format=Commit: %h ('%s') by %an on %ad", ref])
        _, stat, _ = self._run_git(["show", "--stat", "--format=", ref])
        _, diff, _ = self._run_git(["show", "--format=fuller", ref])
        desc = header if code == 0 and header else f"Commit {ref}"
        return desc, stat, diff


def sanitize_and_truncate_diff(diff_text: str, max_chars: int = 15_000) -> str:
    """
    Cleans large lockfiles, generated code, and truncates if overly large
    to ensure fast, high-speed LLM processing.
    """
    if not diff_text:
        return ""

    file_chunks = diff_text.split("diff --git ")
    processed_chunks = []
    
    for chunk in file_chunks:
        if not chunk.strip():
            continue
        first_line = chunk.splitlines()[0] if chunk.splitlines() else ""
        match = re.search(r"a/(.*?)\s+b/(.*)", first_line)
        file_path = match.group(2) if match else first_line

        if is_lockfile_or_generated(file_path):
            line_count = len(chunk.splitlines())
            processed_chunks.append(
                f"[File: {file_path} - Generated lockfile excluded ({line_count} lines)]\n"
            )
        else:
            processed_chunks.append("diff --git " + chunk)

    reconstructed = "".join(processed_chunks)

    if len(reconstructed) > max_chars:
        reconstructed = reconstructed[:max_chars] + f"\n\n... [Diff truncated to {max_chars} chars for fast analysis] ..."

    return reconstructed


# LLM Backends with Streaming Support
class BaseBackend:
    def explain_stream(self, prompt: str) -> Generator[str, None, None]:
        raise NotImplementedError

class AgyBackend(BaseBackend):
    def __init__(self, deep_mode: bool = False):
        self.cmd = shutil.which("agy")
        if not self.cmd:
            raise RuntimeError("'agy' CLI tool is not installed or not in PATH.")
        self.deep_mode = deep_mode

    def explain_stream(self, prompt: str) -> Generator[str, None, None]:
        # Fast mode: gemini-3.8-flash-low + low reasoning effort
        # Deep mode: gemini-3.8-flash-high + high reasoning effort
        model = "gemini-3.8-flash-high" if self.deep_mode else "gemini-3.8-flash-low"
        effort = "high" if self.deep_mode else "low"

        args = [
            self.cmd,
            "--model", model,
            "--effort", effort,
            "--dangerously-skip-permissions",
            "--disable-slash-commands",
            "-p", prompt
        ]

        proc = subprocess.Popen(
            args,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )

        fd = proc.stdout.fileno()
        while True:
            try:
                chunk = os.read(fd, 256)
                if not chunk:
                    break
                yield chunk.decode("utf-8", errors="replace")
            except Exception:
                break

        proc.wait()
        if proc.returncode != 0:
            err = proc.stderr.read().decode("utf-8", errors="ignore").strip()
            if err:
                raise RuntimeError(f"agy error: {err}")

class GeminiBackend(BaseBackend):
    def __init__(self, api_key: Optional[str] = None, model: str = "gemini-2.5-flash"):
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY")
        if not self.api_key:
            raise RuntimeError("GEMINI_API_KEY is not set.")
        self.model = model

    def explain_stream(self, prompt: str) -> Generator[str, None, None]:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent?key={self.api_key}"
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.2}
        }
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                res_json = json.loads(resp.read().decode("utf-8"))
                text = res_json["candidates"][0]["content"]["parts"][0]["text"].strip()
                yield text
        except urllib.error.HTTPError as e:
            raise RuntimeError(f"Gemini API HTTP Error {e.code}: {e.read().decode('utf-8')}")

class OpenAIBackend(BaseBackend):
    def __init__(self, api_key: Optional[str] = None, model: str = "gpt-4o-mini"):
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY")
        if not self.api_key:
            raise RuntimeError("OPENAI_API_KEY is not set.")
        self.model = model

    def explain_stream(self, prompt: str) -> Generator[str, None, None]:
        url = "https://api.openai.com/v1/chat/completions"
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": "You are a senior software engineer explaining code changes concisely."},
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.2
        }
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}"
            }
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                res_json = json.loads(resp.read().decode("utf-8"))
                yield res_json["choices"][0]["message"]["content"].strip()
        except urllib.error.HTTPError as e:
            raise RuntimeError(f"OpenAI API HTTP Error {e.code}: {e.read().decode('utf-8')}")

class OllamaBackend(BaseBackend):
    def __init__(self, host: str = "http://localhost:11434", model: str = "llama3"):
        self.host = host.rstrip("/")
        self.model = model

    def explain_stream(self, prompt: str) -> Generator[str, None, None]:
        url = f"{self.host}/api/generate"
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": True
        }
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=40) as resp:
                for line in resp:
                    if line:
                        chunk_obj = json.loads(line.decode("utf-8"))
                        text_part = chunk_obj.get("response", "")
                        if text_part:
                            yield text_part
        except urllib.error.URLError as e:
            raise RuntimeError(f"Ollama connection error: {e}")

class OfflineBackend(BaseBackend):
    def explain_stream(self, prompt: str) -> Generator[str, None, None]:
        yield (
            "### ⚠️ Offline Mode\n"
            "No active AI backend found (agy, Gemini, OpenAI, or Ollama).\n"
            "Changes were detected in your repository. Please configure an AI backend or check network connection."
        )

def get_backend(preferred_backend: Optional[str] = None, deep_mode: bool = False) -> BaseBackend:
    if preferred_backend:
        b = preferred_backend.lower()
        if b == "agy":
            return AgyBackend(deep_mode=deep_mode)
        elif b == "gemini":
            return GeminiBackend()
        elif b == "openai":
            return OpenAIBackend()
        elif b == "ollama":
            return OllamaBackend()
        elif b == "offline":
            return OfflineBackend()
        else:
            raise ValueError(f"Unknown backend requested: {preferred_backend}")

    # Auto-detection priority
    if shutil.which("agy"):
        try:
            return AgyBackend(deep_mode=deep_mode)
        except Exception:
            pass

    if os.environ.get("GEMINI_API_KEY"):
        return GeminiBackend()

    if os.environ.get("OPENAI_API_KEY"):
        return OpenAIBackend()

    return OfflineBackend()


def copy_to_clipboard(text: str) -> bool:
    """Copies text to system clipboard (supports macOS pbcopy, Linux xclip/wl-copy)."""
    if shutil.which("pbcopy"):
        p = subprocess.Popen(["pbcopy"], stdin=subprocess.PIPE)
        p.communicate(text.encode("utf-8"))
        return p.returncode == 0
    elif shutil.which("xclip"):
        p = subprocess.Popen(["xclip", "-selection", "clipboard"], stdin=subprocess.PIPE)
        p.communicate(text.encode("utf-8"))
        return p.returncode == 0
    elif shutil.which("wl-copy"):
        p = subprocess.Popen(["wl-copy"], stdin=subprocess.PIPE)
        p.communicate(text.encode("utf-8"))
        return p.returncode == 0
    return False


def build_prompt(
    target_description: str,
    branch: str,
    stat_summary: str,
    diff_text: str,
    detail_level: str = "normal"
) -> str:
    # Optimized concise prompts to minimize token generation time
    detail_instructions = {
        "brief": (
            "Explain in 2-3 concise sentences total: what is the core intent and what code was changed."
        ),
        "normal": (
            "Provide a fast, high-signal explanation formatted exactly like this:\n"
            "- 🎯 **Purpose**: 1-2 direct sentences stating what this change achieves.\n"
            "- 🔍 **Key Changes**: 3-5 concise bullet points highlighting key functions, logic, or files changed.\n"
            "- ⚠️ **Watch Out For** (only if applicable): Critical breaking changes, concurrency, or performance risks.\n"
            "Be direct, punchy, and avoid unnecessary filler."
        ),
        "detailed": (
            "Provide an in-depth code explanation:\n"
            "- 🎯 **High-Level Purpose & Architectural Context**\n"
            "- 🔍 **File-by-File Breakdown**: Key functions, classes, and logic\n"
            "- 🧪 **Testing & Verification**: Edge cases or test cases to verify\n"
            "- ⚠️ **Risks & Breaking Changes**\n"
            "- 💡 **Summary**"
        )
    }.get(detail_level, "normal")

    return f"""You are a principal software engineer. Explain the following git changes clearly and concisely.

Target: {target_description}
Branch: {branch}

Files modified:
{stat_summary or "(No stat summary)"}

Code Diff:
{diff_text}

Instructions:
{detail_instructions}

Formatting:
- Use Markdown with bullet points.
- Use backticks for code symbols (e.g. `function_name`, `ClassName`).
"""


def display_banner(target_desc: str, branch: str, cached: bool = False, raw: bool = False):
    if not is_color_enabled(raw):
        cache_indicator = " [CACHED]" if cached else ""
        print(f"=== Explaining: {target_desc} (branch: {branch}){cache_indicator} ===")
        return

    cache_badge = f" {style('⚡ CACHED', Colors.GREEN)} " if cached else ""
    banner_text = f" 💡 {target_desc} [{branch}]{cache_badge} "
    box_width = max(len(re.sub(r'\033\[[0-9;]*m', '', banner_text)) + 2, 45)
    border = "═" * box_width
    print(f"\n{Colors.BLUE}╔{border}╗{Colors.RESET}")
    print(f"{Colors.BLUE}║{Colors.RESET}{Colors.BOLD}{Colors.WHITE}{banner_text.center(box_width)}{Colors.RESET}{Colors.BLUE}║{Colors.RESET}")
    print(f"{Colors.BLUE}╚{border}╝{Colors.RESET}\n")


def interactive_menu(repo: GitRepo) -> str:
    status = repo.get_status_summary()
    unpushed = repo.get_unpushed_commits()
    latest = repo.get_latest_commit()

    options = []
    
    if status["has_uncommitted"]:
        n_staged = len(status["staged"])
        n_unstaged = len(status["unstaged"])
        n_untracked = len(status["untracked"])
        desc = f"Uncommitted changes ({n_staged} staged, {n_unstaged} unstaged, {n_untracked} untracked)"
        options.append(("uncommitted", desc))
        if n_staged > 0:
            options.append(("staged", f"Staged changes only ({n_staged} files ready to commit)"))
    else:
        options.append(("uncommitted", "Uncommitted changes (working tree is clean)"))

    if unpushed:
        options.append(("unpushed", f"Commit(s) about to be pushed ({len(unpushed)} commit(s) ahead of remote)"))
    else:
        options.append(("unpushed", "Commit(s) about to be pushed (0 unpushed commits)"))

    if latest:
        options.append(("latest", f"Latest commit (HEAD: {latest[0]} '{latest[1]}')"))

    options.append(("pick", "Select from recent commit history"))

    print(f"\n{style('? What would you like to explain?', Colors.BOLD, Colors.CYAN)}\n")
    for i, (_, label) in enumerate(options, 1):
        print(f"  {style(f'[{i}]', Colors.YELLOW)} {label}")
    print()

    while True:
        try:
            choice = input(f"{style('Enter selection (1-' + str(len(options)) + ') or [q] to quit: ', Colors.BOLD)}").strip()
            if choice.lower() in ("q", "quit", "exit"):
                sys.exit(0)
            idx = int(choice) - 1
            if 0 <= idx < len(options):
                chosen_key = options[idx][0]
                if chosen_key == "pick":
                    recent = repo.get_recent_commits(limit=10)
                    print(f"\n{style('Select a commit from history:', Colors.BOLD, Colors.CYAN)}")
                    for r_idx, (chash, cmsg) in enumerate(recent, 1):
                        print(f"  {style(f'[{r_idx}]', Colors.YELLOW)} {style(chash, Colors.CYAN)} {cmsg}")
                    r_choice = input(f"\n{style('Commit number: ', Colors.BOLD)}").strip()
                    r_i = int(r_choice) - 1
                    if 0 <= r_i < len(recent):
                        return recent[r_i][0]
                return chosen_key
        except (ValueError, IndexError):
            print("Invalid selection. Please enter a valid number.")


def main():
    parser = argparse.ArgumentParser(
        description="Fast AI explanation for git commits, unpushed changes, or uncommitted modifications.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  git explain                  # Fast auto-detect: uncommitted -> unpushed -> latest commit
  git explain --push           # Explain commits you are about to push
  git explain --latest         # Explain the latest commit (HEAD)
  git explain --uncommitted    # Explain uncommitted working directory changes
  git explain -i               # Interactive menu to select what to explain
  git explain --deep           # Deep reasoning mode with high thinking effort
  git explain --copy           # Explain and automatically copy to clipboard
  git explain --brief          # Ultra-fast 2-sentence summary
        """
    )

    # Positional target
    parser.add_argument(
        "target",
        nargs="?",
        default=None,
        help="Optional target: 'uncommitted', 'staged', 'push', 'latest', or a git ref/range"
    )

    # Target flags
    target_group = parser.add_argument_group("Target Selection")
    target_group.add_argument("-u", "--uncommitted", action="store_true", help="Explain uncommitted changes in working tree")
    target_group.add_argument("-s", "--staged", action="store_true", help="Explain only staged (cached) changes")
    target_group.add_argument("-p", "--push", "--unpushed", action="store_true", dest="unpushed", help="Explain commit(s) about to be pushed")
    target_group.add_argument("-l", "--latest", "--last", "--head", action="store_true", help="Explain latest commit (HEAD)")
    target_group.add_argument("-i", "--interactive", action="store_true", help="Interactively choose what to explain")

    # Speed & Depth Options
    speed_group = parser.add_argument_group("Performance & Detail")
    speed_group.add_argument("-b", "--brief", action="store_true", help="Ultra-fast 2-sentence summary")
    speed_group.add_argument("-d", "--detailed", action="store_true", help="Detailed walkthrough with testing suggestions")
    speed_group.add_argument("--deep", action="store_true", help="Enable high-effort reasoning model (takes longer)")
    speed_group.add_argument("--no-cache", action="store_true", help="Bypass local cache and regenerate fresh explanation")

    # Extra Options
    parser.add_argument("-c", "--copy", action="store_true", help="Copy the generated explanation to clipboard")
    parser.add_argument("--raw", action="store_true", help="Output raw markdown without ANSI color formatting")
    parser.add_argument("-e", "--backend", choices=["agy", "gemini", "openai", "ollama", "offline"], help="AI backend to use")

    args = parser.parse_args()

    try:
        repo = GitRepo()
    except Exception as e:
        print(f"{style('Error:', Colors.BOLD, Colors.RED)} {e}", file=sys.stderr)
        sys.exit(1)

    branch = repo.get_current_branch()
    status = repo.get_status_summary()
    unpushed_commits = repo.get_unpushed_commits()

    # Determine target mode
    mode = None
    ref_arg = None

    if args.interactive:
        mode = interactive_menu(repo)
    elif args.staged:
        mode = "staged"
    elif args.uncommitted:
        mode = "uncommitted"
    elif args.unpushed:
        mode = "unpushed"
    elif args.latest:
        mode = "latest"
    elif args.target:
        t = args.target.lower()
        if t in ("uncommitted", "diff", "unstaged"):
            mode = "uncommitted"
        elif t in ("staged", "cached"):
            mode = "staged"
        elif t in ("push", "unpushed", "pushing"):
            mode = "unpushed"
        elif t in ("latest", "last", "head"):
            mode = "latest"
        else:
            mode = "custom_ref"
            ref_arg = args.target
    else:
        # Smart Auto-Detection
        if status["has_uncommitted"]:
            mode = "uncommitted"
        elif unpushed_commits:
            mode = "unpushed"
        elif repo.has_commits():
            mode = "latest"
        else:
            print(f"{style('Info:', Colors.YELLOW)} Repository has no commits or changes to explain.", file=sys.stderr)
            sys.exit(0)

    # Gather diff and metadata
    target_desc = ""
    stat_summary = ""
    diff_text = ""

    if mode == "uncommitted":
        n_staged = len(status["staged"])
        n_unstaged = len(status["unstaged"])
        n_untracked = len(status["untracked"])
        target_desc = f"Uncommitted changes ({n_staged} staged, {n_unstaged} unstaged, {n_untracked} untracked)"
        stat_summary, diff_text = repo.get_uncommitted_diff(staged_only=False)
        if not diff_text.strip():
            print(f"{style('Notice:', Colors.YELLOW)} No uncommitted changes found in working tree.")
            sys.exit(0)

    elif mode == "staged":
        target_desc = f"Staged changes ({len(status['staged'])} files staged)"
        stat_summary, diff_text = repo.get_uncommitted_diff(staged_only=True)
        if not diff_text.strip():
            print(f"{style('Notice:', Colors.YELLOW)} No staged changes found. Use 'git add' or run 'git explain -u' for unstaged changes.")
            sys.exit(0)

    elif mode == "unpushed":
        if not unpushed_commits:
            print(f"{style('Notice:', Colors.YELLOW)} No unpushed commits found ahead of remote. Explaining latest commit instead.\n")
            mode = "latest"
        else:
            first_hash, first_msg = unpushed_commits[0]
            target_desc = f"Commits about to be pushed ({len(unpushed_commits)} commit(s): {first_hash} '{first_msg}')"
            _, stat_summary, diff_text = repo.get_unpushed_diff()

    if mode == "latest":
        latest = repo.get_latest_commit()
        if not latest:
            print(f"{style('Error:', Colors.RED)} No commits exist in this repository.", file=sys.stderr)
            sys.exit(1)
        target_desc = f"Latest commit ({latest[0]}: '{latest[1]}')"
        _, stat_summary, diff_text = repo.get_commit_diff("HEAD")

    elif mode == "custom_ref":
        target_desc, stat_summary, diff_text = repo.get_commit_diff(ref_arg)

    # Sanitize and truncate diff (max 15k chars for fast processing)
    sanitized_diff = sanitize_and_truncate_diff(diff_text, max_chars=20_000 if args.detailed else 12_000)
    if not sanitized_diff.strip():
        print(f"{style('Notice:', Colors.YELLOW)} Diff is empty for the selected target.")
        sys.exit(0)

    detail_level = "brief" if args.brief else ("detailed" if args.detailed else "normal")

    # Cache check for instant response
    cache_seed = f"{target_desc}:{sanitized_diff}:{detail_level}:{args.deep}:{args.backend}"
    cache_key = hashlib.sha256(cache_seed.encode("utf-8")).hexdigest()

    cached_output = None
    if not args.no_cache:
        cached_output = read_cache(cache_key)

    if cached_output:
        display_banner(target_desc, branch, cached=True, raw=args.raw)
        print(cached_output)
        print()
        if args.copy:
            if copy_to_clipboard(cached_output):
                print(f"{style('✓', Colors.GREEN)} {style('Explanation copied to clipboard!', Colors.DIM)}")
        return

    # Build prompt
    prompt = build_prompt(
        target_description=target_desc,
        branch=branch,
        stat_summary=stat_summary,
        diff_text=sanitized_diff,
        detail_level=detail_level
    )

    display_banner(target_desc, branch, cached=False, raw=args.raw)

    try:
        backend = get_backend(args.backend, deep_mode=args.deep)
    except Exception as e:
        print(f"{style('Backend Error:', Colors.RED)} {e}", file=sys.stderr)
        sys.exit(1)

    # Stream output in real-time
    spinner = StreamSpinner("Thinking...", enabled=not args.raw)
    spinner.start()

    accumulated = []
    first_chunk_received = False

    try:
        for chunk in backend.explain_stream(prompt):
            if not first_chunk_received:
                spinner.stop()
                first_chunk_received = True

            accumulated.append(chunk)
            sys.stdout.write(chunk)
            sys.stdout.flush()

        if not first_chunk_received:
            spinner.stop()

    except Exception as e:
        spinner.stop()
        print(f"\n{style('Analysis Error:', Colors.BOLD, Colors.RED)} {e}", file=sys.stderr)
        sys.exit(1)

    full_text = "".join(accumulated).strip()
    print("\n")

    # Save to cache
    if full_text:
        write_cache(cache_key, full_text)

    # Clipboard support
    if args.copy and full_text:
        if copy_to_clipboard(full_text):
            print(f"{style('✓', Colors.GREEN)} {style('Explanation copied to clipboard!', Colors.DIM)}")
        else:
            print(f"{style('!', Colors.YELLOW)} {style('Failed to copy to clipboard.', Colors.DIM)}")

if __name__ == "__main__":
    main()
