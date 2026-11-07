#!/usr/bin/env python3
"""
Unit and integration tests for explain_commit.py
"""

import os
import shutil
import subprocess
import tempfile
import unittest

from explain_commit import (
    GitRepo,
    sanitize_and_truncate_diff,
    is_lockfile_or_generated,
    is_binary_file,
    resolve_file_path,
    build_prompt,
    build_file_prompt,
    get_backend,
    OfflineBackend,
    write_cache,
    read_cache,
    MarkdownTerminalRenderer
)

class TestGitExplain(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.remote_dir = os.path.join(self.temp_dir, "remote.git")
        self.local_dir = os.path.join(self.temp_dir, "local")

        subprocess.run(["git", "init", "--bare", self.remote_dir], check=True, capture_output=True)
        subprocess.run(["git", "clone", self.remote_dir, self.local_dir], check=True, capture_output=True)
        subprocess.run(["git", "config", "user.name", "Test User"], cwd=self.local_dir, check=True)
        subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=self.local_dir, check=True)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_repo_initialization_and_empty_state(self):
        repo = GitRepo(self.local_dir)
        self.assertFalse(repo.has_commits())
        status = repo.get_status_summary()
        self.assertFalse(status["has_uncommitted"])

    def test_uncommitted_changes_staged_and_unstaged(self):
        repo = GitRepo(self.local_dir)

        readme_path = os.path.join(self.local_dir, "README.md")
        with open(readme_path, "w") as f:
            f.write("# Project\n")
        subprocess.run(["git", "add", "README.md"], cwd=self.local_dir, check=True)
        subprocess.run(["git", "commit", "-m", "Initial commit"], cwd=self.local_dir, check=True)
        subprocess.run(["git", "push", "-u", "origin", "HEAD:main"], cwd=self.local_dir, check=True)

        with open(readme_path, "a") as f:
            f.write("A new line\n")
        subprocess.run(["git", "add", "README.md"], cwd=self.local_dir, check=True)

        with open(readme_path, "a") as f:
            f.write("Unstaged line\n")

        untracked_path = os.path.join(self.local_dir, "new_file.py")
        with open(untracked_path, "w") as f:
            f.write("print('hello')\n")

        status = repo.get_status_summary()
        self.assertTrue(status["has_uncommitted"])
        self.assertEqual(len(status["staged"]), 1)
        self.assertEqual(len(status["unstaged"]), 1)
        self.assertIn("new_file.py", status["untracked"])

        stat, diff = repo.get_uncommitted_diff()
        self.assertIn("new_file.py", diff)
        self.assertIn("A new line", diff)
        self.assertIn("Unstaged line", diff)

    def test_unpushed_commits_detection(self):
        repo = GitRepo(self.local_dir)

        f1 = os.path.join(self.local_dir, "file1.txt")
        with open(f1, "w") as f:
            f.write("first\n")
        subprocess.run(["git", "add", "file1.txt"], cwd=self.local_dir, check=True)
        subprocess.run(["git", "commit", "-m", "First commit"], cwd=self.local_dir, check=True)
        subprocess.run(["git", "push", "-u", "origin", "HEAD:main"], cwd=self.local_dir, check=True)

        unpushed = repo.get_unpushed_commits()
        self.assertEqual(len(unpushed), 0)

        with open(f1, "a") as f:
            f.write("second line\n")
        subprocess.run(["git", "commit", "-am", "Add second line to file1"], cwd=self.local_dir, check=True)

        unpushed = repo.get_unpushed_commits()
        self.assertEqual(len(unpushed), 1)
        self.assertIn("Add second line to file1", unpushed[0][1])

        desc, stat, diff = repo.get_unpushed_diff()
        self.assertIn("Unpushed", desc)
        self.assertIn("second line", diff)

    def test_latest_commit_detection(self):
        repo = GitRepo(self.local_dir)
        f1 = os.path.join(self.local_dir, "file1.txt")
        with open(f1, "w") as f:
            f.write("version 1\n")
        subprocess.run(["git", "add", "file1.txt"], cwd=self.local_dir, check=True)
        subprocess.run(["git", "commit", "-m", "Commit V1"], cwd=self.local_dir, check=True)

        latest = repo.get_latest_commit()
        self.assertIsNotNone(latest)
        self.assertEqual(latest[1], "Commit V1")

        desc, stat, diff = repo.get_commit_diff("HEAD")
        self.assertIn("Commit V1", desc)
        self.assertIn("version 1", diff)

    def test_diff_sanitizer_excludes_lockfiles(self):
        self.assertTrue(is_lockfile_or_generated("package-lock.json"))
        self.assertTrue(is_lockfile_or_generated("frontend/yarn.lock"))
        self.assertTrue(is_lockfile_or_generated("pnpm-lock.yaml"))
        self.assertTrue(is_lockfile_or_generated("Cargo.lock"))
        self.assertFalse(is_lockfile_or_generated("src/main.py"))

        raw_diff = (
            "diff --git a/package-lock.json b/package-lock.json\n"
            "--- a/package-lock.json\n"
            "+++ b/package-lock.json\n"
            "@@ -1,5 +1,5 @@\n"
            "+lockfile changes\n"
            "diff --git a/src/app.py b/src/app.py\n"
            "--- a/src/app.py\n"
            "+++ b/src/app.py\n"
            "@@ -0,0 +1 @@\n"
            "+def app(): pass\n"
        )

        sanitized = sanitize_and_truncate_diff(raw_diff)
        self.assertIn("Generated lockfile excluded", sanitized)
        self.assertIn("def app(): pass", sanitized)

    def test_prompt_generation(self):
        prompt = build_prompt(
            target_description="Uncommitted changes (1 file)",
            branch="main",
            stat_summary="app.py | 1 +",
            diff_text="+def run(): pass",
            detail_level="brief"
        )
        self.assertIn("Uncommitted changes", prompt)
        self.assertIn("app.py", prompt)
        self.assertIn("def run(): pass", prompt)

    def test_resolve_file_path(self):
        repo = GitRepo(self.local_dir)
        sub_dir = os.path.join(self.local_dir, "src")
        os.makedirs(sub_dir, exist_ok=True)
        test_file = os.path.join(sub_dir, "auth.py")
        with open(test_file, "w") as f:
            f.write("def login(): pass\n")

        # Resolve direct
        resolved = resolve_file_path(test_file, repo)
        self.assertEqual(resolved, os.path.realpath(test_file))

        # Resolve relative to repo root
        resolved_rel = resolve_file_path("src/auth.py", repo)
        self.assertEqual(resolved_rel, os.path.realpath(test_file))

        # Non-existent
        self.assertIsNone(resolve_file_path("non_existent.py", repo))

    def test_build_file_prompt(self):
        code = "def authenticate(user, password):\n    return True\n"
        prompt = build_file_prompt("auth.py", code, detail_level="normal")
        self.assertIn("auth.py", prompt)
        self.assertIn("authenticate", prompt)
        self.assertIn("Functions & Classes", prompt)

    def test_binary_file_check(self):
        text_file = os.path.join(self.temp_dir, "text.txt")
        with open(text_file, "w") as f:
            f.write("hello world\n")
        self.assertFalse(is_binary_file(text_file))

        bin_file = os.path.join(self.temp_dir, "binary.bin")
        with open(bin_file, "wb") as f:
            f.write(b"\x00\x01\x02\x03\xff")
        self.assertTrue(is_binary_file(bin_file))

    def test_caching(self):
        test_key = "test_cache_key_12345"
        test_val = "This is cached content"
        write_cache(test_key, test_val)
        cached = read_cache(test_key)
        self.assertEqual(cached, test_val)

    def test_markdown_renderer_bold_and_code(self):
        renderer = MarkdownTerminalRenderer(raw=False)
        rendered = renderer.render_line("- **cheese** is `good`.")
        self.assertNotIn("**cheese**", rendered)
        self.assertNotIn("`good`", rendered)
        self.assertIn("cheese", rendered)
        self.assertIn("good", rendered)
        self.assertIn("\033[1m", rendered)  # ANSI Bold
        self.assertIn("\033[38;5;51m", rendered)  # ANSI Cyan

    def test_markdown_renderer_links(self):
        renderer = MarkdownTerminalRenderer(raw=False)
        rendered = renderer.render_line("Added [math_calc.py](file:///some/long/path/to/math_calc.py).")
        self.assertNotIn("file://", rendered)
        self.assertIn("math_calc.py", rendered)

    def test_markdown_renderer_raw_mode(self):
        renderer = MarkdownTerminalRenderer(raw=True)
        raw_text = "- **cheese** is `good`."
        rendered = renderer.render_line(raw_text)
        self.assertEqual(rendered, raw_text)

    def test_offline_backend(self):
        backend = get_backend("offline")
        self.assertIsInstance(backend, OfflineBackend)
        chunks = list(backend.explain_stream("test prompt"))
        full = "".join(chunks)
        self.assertIn("Offline", full)

if __name__ == "__main__":
    unittest.main()
