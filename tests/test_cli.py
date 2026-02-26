import os
import stat
import subprocess

import pytest

from hookmaster.cli import (
    add_hooks_to_project,
    check_forbidden_strings,
    ensure_gitignore_entry,
    get_hooks_dir,
    render_hooks,
    summary_line_for_branch,
)


class TestSummaryLineForBranch:
    def test_main_branch(self):
        assert summary_line_for_branch("main") == "Commit to: main"

    def test_master_branch(self):
        assert summary_line_for_branch("master") == "Commit to: master"

    def test_dev_branch(self):
        assert summary_line_for_branch("dev") == "Commit to: dev"

    def test_head(self):
        assert summary_line_for_branch("HEAD") == "Commit to: HEAD"

    def test_ticket_with_description(self):
        assert (
            summary_line_for_branch("bugfixes/PROJ-123-fix-the-thing")
            == "PROJ-123: Fix the thing"
        )

    def test_ticket_only(self):
        assert summary_line_for_branch("PROJ-456") == "PROJ-456"

    def test_ticket_with_prefix(self):
        assert (
            summary_line_for_branch("feature/PROJ-789-add-stuff")
            == "PROJ-789: Add stuff"
        )

    def test_no_ticket(self):
        assert summary_line_for_branch("some-feature-branch") == "some-feature-branch"


class TestEnsureGitignoreEntry:
    def test_creates_gitignore(self, tmp_path):
        ensure_gitignore_entry(tmp_path, ".githooks/")
        assert (tmp_path / ".gitignore").read_text() == ".githooks/\n"

    def test_appends_to_existing(self, tmp_path):
        (tmp_path / ".gitignore").write_text("__pycache__/\n")
        ensure_gitignore_entry(tmp_path, ".githooks/")
        assert (tmp_path / ".gitignore").read_text() == "__pycache__/\n.githooks/\n"

    def test_no_duplicate(self, tmp_path):
        (tmp_path / ".gitignore").write_text("__pycache__/\n.githooks/\n")
        ensure_gitignore_entry(tmp_path, ".githooks/")
        assert (tmp_path / ".gitignore").read_text() == "__pycache__/\n.githooks/\n"

    def test_adds_newline_if_missing(self, tmp_path):
        (tmp_path / ".gitignore").write_text("__pycache__/")
        ensure_gitignore_entry(tmp_path, ".githooks/")
        assert (tmp_path / ".gitignore").read_text() == "__pycache__/\n.githooks/\n"


class TestRenderHooks:
    def test_creates_hook_files(self, tmp_path):
        hooks_dir = tmp_path / ".githooks"
        render_hooks({"pre-commit": "echo hello"}, hooks_dir)

        hook_file = hooks_dir / "pre-commit"
        assert hook_file.exists()
        assert hook_file.read_text() == "#!/bin/sh\necho hello\n"

    def test_hook_is_executable(self, tmp_path):
        hooks_dir = tmp_path / ".githooks"
        render_hooks({"pre-commit": "echo hello"}, hooks_dir)

        hook_file = hooks_dir / "pre-commit"
        mode = hook_file.stat().st_mode
        assert mode & stat.S_IXUSR
        assert mode & stat.S_IXGRP
        assert mode & stat.S_IXOTH

    def test_lf_line_endings(self, tmp_path):
        hooks_dir = tmp_path / ".githooks"
        render_hooks({"pre-commit": "echo hello"}, hooks_dir)

        raw = (hooks_dir / "pre-commit").read_bytes()
        assert b"\r\n" not in raw
        assert b"\n" in raw


def _init_git_repo(path):
    """Initialize a git repo and return the path."""
    subprocess.run(["git", "init", str(path)], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(path), "config", "user.email", "test@test.com"],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "-C", str(path), "config", "user.name", "Test"],
        check=True,
        capture_output=True,
    )
    return path


class TestAddHooksToProject:
    def test_installs_prepare_commit_msg(self, tmp_path):
        repo = _init_git_repo(tmp_path / "myrepo")
        add_hooks_to_project(tmp_path)

        hook = repo / ".githooks" / "prepare-commit-msg"
        assert hook.exists()
        assert "hookmaster prepare-commit-msg" in hook.read_text()

    def test_sets_core_hooks_path(self, tmp_path):
        repo = _init_git_repo(tmp_path / "myrepo")
        add_hooks_to_project(tmp_path)

        result = subprocess.run(
            ["git", "-C", str(repo), "config", "core.hooksPath"],
            capture_output=True,
            text=True,
        )
        assert result.stdout.strip() == ".githooks"

    def test_adds_gitignore_entry(self, tmp_path):
        _init_git_repo(tmp_path / "myrepo")
        add_hooks_to_project(tmp_path)

        gitignore = (tmp_path / "myrepo" / ".gitignore").read_text()
        assert ".githooks/" in gitignore

    def test_installs_config_hooks(self, tmp_path):
        repo = _init_git_repo(tmp_path / "myrepo")
        (repo / "githooks.toml").write_text('pre-commit = "ruff format --check ."\n')
        add_hooks_to_project(tmp_path)

        hook = repo / ".githooks" / "pre-commit"
        assert hook.exists()
        assert "hookmaster run pre-commit" in hook.read_text()


def _stage_file(repo, filename, content):
    """Write a file and stage it."""
    filepath = repo / filename
    filepath.parent.mkdir(parents=True, exist_ok=True)
    filepath.write_text(content)
    subprocess.run(
        ["git", "-C", str(repo), "add", filename], check=True, capture_output=True
    )


class TestCheckForbiddenStrings:
    def test_matches_forbidden_string(self, tmp_path):
        repo = _init_git_repo(tmp_path / "repo")
        _stage_file(repo, "main.py", "x = 1\n<<<<<<< HEAD\ny = 2\n")
        assert check_forbidden_strings(repo, {"<<<<<<< ": "*"}) is True

    def test_glob_filters_files(self, tmp_path):
        repo = _init_git_repo(tmp_path / "repo")
        _stage_file(repo, "script.js", "console.log('hi')\n")
        # glob only matches *.py, so script.js should be skipped
        assert check_forbidden_strings(repo, {"console.log": "*.py"}) is False

    def test_multi_glob(self, tmp_path):
        repo = _init_git_repo(tmp_path / "repo")
        _stage_file(repo, "app.ts", "console.log('debug')\n")
        _stage_file(repo, "main.py", "print('ok')\n")
        assert check_forbidden_strings(repo, {"console.log": ["*.py", "*.ts"]}) is True

    def test_star_matches_all(self, tmp_path):
        repo = _init_git_repo(tmp_path / "repo")
        _stage_file(repo, "notes.txt", "<<<<<<< HEAD\n")
        assert check_forbidden_strings(repo, {"<<<<<<< ": "*"}) is True

    def test_no_violations(self, tmp_path):
        repo = _init_git_repo(tmp_path / "repo")
        _stage_file(repo, "clean.py", "x = 1\ny = 2\n")
        assert check_forbidden_strings(repo, {"<<<<<<< ": "*"}) is False

    def test_non_matching_glob_skips(self, tmp_path):
        repo = _init_git_repo(tmp_path / "repo")
        _stage_file(repo, "app.rb", "binding.pry\n")
        assert check_forbidden_strings(repo, {"binding.pry": "*.py"}) is False


class TestGetHooksDir:
    def test_returns_githooks_when_configured(self, tmp_path):
        repo = _init_git_repo(tmp_path / "myrepo")
        subprocess.run(
            ["git", "-C", str(repo), "config", "core.hooksPath", ".githooks"],
            check=True,
            capture_output=True,
        )
        assert get_hooks_dir(repo) == repo / ".githooks"

    def test_falls_back_to_git_hooks(self, tmp_path):
        repo = _init_git_repo(tmp_path / "myrepo")
        assert get_hooks_dir(repo) == repo / ".git" / "hooks"
