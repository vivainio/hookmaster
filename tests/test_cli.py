import os
import stat
import subprocess
import sys

import pytest

from hookmaster.cli import (
    _parse_size,
    add_hooks_to_project,
    check_ascii_only,
    check_do_not_modify,
    check_forbidden_strings,
    check_max_file_size,
    ensure_gitignore_entry,
    generate_config,
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

    def test_githooks_toml_always_excluded(self, tmp_path):
        repo = _init_git_repo(tmp_path / "repo")
        _stage_file(repo, "githooks.toml", '"<<<<<<< " = "*"\n')
        assert check_forbidden_strings(repo, {"<<<<<<< ": "*"}) is False


class TestCheckAsciiOnly:
    def test_detects_emoji(self, tmp_path):
        repo = _init_git_repo(tmp_path / "repo")
        _stage_file(repo, "config.toml", 'name = "hello 🎉"\n')
        assert check_ascii_only(repo, {"files": ["*.toml"]}) is True

    def test_detects_smart_quotes(self, tmp_path):
        repo = _init_git_repo(tmp_path / "repo")
        _stage_file(repo, "config.yml", "msg: \u201chello\u201d\n")
        assert check_ascii_only(repo, {"files": ["*.yml", "*.toml"]}) is True

    def test_passes_clean_ascii(self, tmp_path):
        repo = _init_git_repo(tmp_path / "repo")
        _stage_file(repo, "config.toml", 'name = "hello"\n')
        assert check_ascii_only(repo, {"files": ["*.toml"]}) is False

    def test_glob_filters_files(self, tmp_path):
        repo = _init_git_repo(tmp_path / "repo")
        _stage_file(repo, "notes.md", "caf\u00e9\n")
        # glob only matches *.toml, so notes.md should be skipped
        assert check_ascii_only(repo, {"files": ["*.toml"]}) is False

    def test_multi_glob(self, tmp_path):
        repo = _init_git_repo(tmp_path / "repo")
        _stage_file(repo, "run.sh", "echo '\u00e9'\n")
        assert check_ascii_only(repo, {"files": ["*.sh", "*.toml"]}) is True

    def test_no_staged_files(self, tmp_path):
        repo = _init_git_repo(tmp_path / "repo")
        assert check_ascii_only(repo, {"files": ["*"]}) is False

    def test_exclude_skips_files(self, tmp_path):
        repo = _init_git_repo(tmp_path / "repo")
        _stage_file(repo, "tests/test_unicode.py", "emoji = '🎉'\n")
        _stage_file(repo, "main.py", "x = 1\n")
        assert (
            check_ascii_only(repo, {"files": ["*.py"], "exclude": ["tests/*"]}) is False
        )

    def test_exclude_does_not_skip_non_matching(self, tmp_path):
        repo = _init_git_repo(tmp_path / "repo")
        _stage_file(repo, "src/app.py", "emoji = '🎉'\n")
        assert (
            check_ascii_only(repo, {"files": ["*.py"], "exclude": ["tests/*"]}) is True
        )

    def test_allow_whitelists_characters(self, tmp_path):
        repo = _init_git_repo(tmp_path / "repo")
        _stage_file(repo, "main.py", "arrow = '→'\ndash = '—'\n")
        assert check_ascii_only(repo, {"files": ["*.py"], "allow": ["→", "—"]}) is False

    def test_allow_still_catches_non_allowed(self, tmp_path):
        repo = _init_git_repo(tmp_path / "repo")
        _stage_file(repo, "main.py", "arrow = '→'\nemoji = '🎉'\n")
        assert check_ascii_only(repo, {"files": ["*.py"], "allow": ["→"]}) is True

    def test_githooks_toml_always_excluded(self, tmp_path):
        repo = _init_git_repo(tmp_path / "repo")
        _stage_file(repo, "githooks.toml", 'allow = ["→", "—"]\n')
        assert check_ascii_only(repo, {"files": ["*.toml"]}) is False


class TestParseSize:
    def test_bytes(self):
        assert _parse_size("100B") == 100

    def test_kilobytes(self):
        assert _parse_size("500KB") == 500 * 1024

    def test_megabytes(self):
        assert _parse_size("5MB") == 5 * 1024**2

    def test_gigabytes(self):
        assert _parse_size("1GB") == 1024**3

    def test_lowercase(self):
        assert _parse_size("5mb") == 5 * 1024**2

    def test_fractional(self):
        assert _parse_size("1.5MB") == int(1.5 * 1024**2)

    def test_plain_number(self):
        assert _parse_size("1024") == 1024


class TestCheckMaxFileSize:
    def test_detects_oversized_file(self, tmp_path):
        repo = _init_git_repo(tmp_path / "repo")
        _stage_file(repo, "big.bin", "x" * 2000)
        assert check_max_file_size(repo, "1KB") is True

    def test_passes_small_file(self, tmp_path):
        repo = _init_git_repo(tmp_path / "repo")
        _stage_file(repo, "small.txt", "hello\n")
        assert check_max_file_size(repo, "1KB") is False

    def test_no_staged_files(self, tmp_path):
        repo = _init_git_repo(tmp_path / "repo")
        assert check_max_file_size(repo, "1KB") is False

    def test_integer_limit(self, tmp_path):
        repo = _init_git_repo(tmp_path / "repo")
        _stage_file(repo, "big.txt", "x" * 2000)
        assert check_max_file_size(repo, 1000) is True

    def test_worktree_mode(self, tmp_path):
        repo = _init_git_repo(tmp_path / "repo")
        _stage_file(repo, "big.txt", "x" * 2000)
        assert check_max_file_size(repo, "1KB", staged_only=False) is True


class TestCheckDoNotModify:
    def test_blocks_protected_file(self, tmp_path):
        repo = _init_git_repo(tmp_path / "repo")
        _stage_file(repo, "package-lock.json", "{}")
        assert check_do_not_modify(repo, ["package-lock.json"]) is True

    def test_allows_unprotected_file(self, tmp_path):
        repo = _init_git_repo(tmp_path / "repo")
        _stage_file(repo, "main.py", "x = 1\n")
        assert check_do_not_modify(repo, ["package-lock.json"]) is False

    def test_glob_pattern(self, tmp_path):
        repo = _init_git_repo(tmp_path / "repo")
        _stage_file(repo, "vendor/lib.py", "x = 1\n")
        assert check_do_not_modify(repo, ["vendor/*"]) is True

    def test_string_instead_of_list(self, tmp_path):
        repo = _init_git_repo(tmp_path / "repo")
        _stage_file(repo, "go.sum", "hash\n")
        assert check_do_not_modify(repo, "go.sum") is True

    def test_no_staged_files(self, tmp_path):
        repo = _init_git_repo(tmp_path / "repo")
        assert check_do_not_modify(repo, ["*.lock"]) is False

    def test_worktree_mode(self, tmp_path):
        repo = _init_git_repo(tmp_path / "repo")
        _stage_file(repo, "vendor/lib.py", "x = 1\n")
        assert check_do_not_modify(repo, ["vendor/*"], staged_only=False) is True


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


if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib


def _parse_generated(repo_root):
    """Generate config and parse it as TOML to verify validity."""
    raw = generate_config(repo_root)
    return tomllib.loads(raw), raw


class TestGenerateConfig:
    def test_python_repo(self, tmp_path):
        repo = _init_git_repo(tmp_path / "repo")
        _stage_file(repo, "main.py", "print('hi')\n")
        config, _ = _parse_generated(repo)
        assert "ruff" in config["pre-commit"]
        assert "pytest" in config["pre-push"]
        assert "breakpoint()" in config["forbidden-strings"]
        assert "*.py" in config["ascii-only"]["files"]

    def test_js_repo(self, tmp_path):
        repo = _init_git_repo(tmp_path / "repo")
        _stage_file(repo, "index.js", "console.log('hi')\n")
        config, _ = _parse_generated(repo)
        assert "prettier" in config["pre-commit"]
        assert "npm test" in config["pre-push"]
        assert "console.log" in config["forbidden-strings"]
        assert "debugger" in config["forbidden-strings"]
        assert "*.js" in config["ascii-only"]["files"]

    def test_ts_repo(self, tmp_path):
        repo = _init_git_repo(tmp_path / "repo")
        _stage_file(repo, "app.ts", "const x = 1;\n")
        config, _ = _parse_generated(repo)
        assert "prettier" in config["pre-commit"]
        assert "*.ts" in config["ascii-only"]["files"]

    def test_go_repo(self, tmp_path):
        repo = _init_git_repo(tmp_path / "repo")
        _stage_file(repo, "main.go", "package main\n")
        config, _ = _parse_generated(repo)
        assert "gofmt" in config["pre-commit"]
        assert "go test" in config["pre-push"]
        assert "*.go" in config["ascii-only"]["files"]

    def test_rust_repo(self, tmp_path):
        repo = _init_git_repo(tmp_path / "repo")
        _stage_file(repo, "main.rs", "fn main() {}\n")
        config, _ = _parse_generated(repo)
        assert "cargo fmt" in config["pre-commit"]
        assert "cargo test" in config["pre-push"]
        assert "*.rs" in config["ascii-only"]["files"]

    def test_ruby_repo(self, tmp_path):
        repo = _init_git_repo(tmp_path / "repo")
        _stage_file(repo, "app.rb", "puts 'hi'\n")
        config, _ = _parse_generated(repo)
        assert "binding.pry" in config["forbidden-strings"]
        assert "*.rb" in config["ascii-only"]["files"]

    def test_empty_repo(self, tmp_path):
        repo = _init_git_repo(tmp_path / "repo")
        config, _ = _parse_generated(repo)
        assert config["pre-commit"] == ""
        assert config["pre-push"] == ""
        assert "<<<<<<< " in config["forbidden-strings"]
        # config files always get ascii-only
        assert "*.toml" in config["ascii-only"]["files"]
        assert "*.json" in config["ascii-only"]["files"]
        # max-file-size always present
        assert config["max-file-size"] == "1MB"

    def test_shell_gets_ascii_only(self, tmp_path):
        repo = _init_git_repo(tmp_path / "repo")
        _stage_file(repo, "deploy.sh", "#!/bin/sh\n")
        config, _ = _parse_generated(repo)
        assert "*.sh" in config["ascii-only"]["files"]

    def test_merge_conflict_marker_always_present(self, tmp_path):
        repo = _init_git_repo(tmp_path / "repo")
        config, _ = _parse_generated(repo)
        assert config["forbidden-strings"]["<<<<<<< "] == "*"

    def test_generated_config_is_valid_toml(self, tmp_path):
        repo = _init_git_repo(tmp_path / "repo")
        _stage_file(repo, "main.py", "")
        _stage_file(repo, "index.js", "")
        _stage_file(repo, "app.rb", "")
        _stage_file(repo, "run.sh", "")
        # should not raise
        config, raw = _parse_generated(repo)
        assert isinstance(config, dict)

    def test_allow_populated_from_existing_chars(self, tmp_path):
        repo = _init_git_repo(tmp_path / "repo")
        _stage_file(repo, "main.py", "arrow = '→'\ndash = '—'\n")
        config, _ = _parse_generated(repo)
        assert "→" in config["ascii-only"]["allow"]
        assert "—" in config["ascii-only"]["allow"]

    def test_allow_omitted_when_no_non_ascii(self, tmp_path):
        repo = _init_git_repo(tmp_path / "repo")
        _stage_file(repo, "main.py", "x = 1\n")
        config, _ = _parse_generated(repo)
        assert "allow" not in config["ascii-only"]

    def test_allow_skips_githooks_toml(self, tmp_path):
        repo = _init_git_repo(tmp_path / "repo")
        _stage_file(repo, "main.py", "x = 1\n")
        _stage_file(repo, "githooks.toml", 'allow = ["→", "—", "🎉"]\n')
        config, _ = _parse_generated(repo)
        assert "allow" not in config["ascii-only"]

    def test_exclude_suggested_when_unicode_only_in_tests(self, tmp_path):
        repo = _init_git_repo(tmp_path / "repo")
        _stage_file(repo, "main.py", "x = 1\n")
        _stage_file(repo, "tests/test_unicode.py", "emoji = '🎉'\ncafe = 'café'\n")
        config, _ = _parse_generated(repo)
        assert "tests/*" in config["ascii-only"]["exclude"]
        assert "allow" not in config["ascii-only"]

    def test_no_exclude_when_unicode_in_source_too(self, tmp_path):
        repo = _init_git_repo(tmp_path / "repo")
        _stage_file(repo, "main.py", "arrow = '→'\n")
        _stage_file(repo, "tests/test_unicode.py", "emoji = '🎉'\narrow = '→'\n")
        config, _ = _parse_generated(repo)
        # source has unicode too, so only source chars in allow
        assert "→" in config["ascii-only"]["allow"]
        # emoji only in tests, not in allow
        assert "🎉" not in config["ascii-only"]["allow"]

    def test_exclude_suggested_with_source_allow(self, tmp_path):
        repo = _init_git_repo(tmp_path / "repo")
        _stage_file(repo, "main.py", "dash = '—'\n")
        _stage_file(repo, "tests/test_stuff.py", "emoji = '🎉'\n")
        config, _ = _parse_generated(repo)
        assert "tests/*" in config["ascii-only"]["exclude"]
        assert "—" in config["ascii-only"]["allow"]
        assert "🎉" not in config["ascii-only"]["allow"]
