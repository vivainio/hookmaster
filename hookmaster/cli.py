import re
import stat
import subprocess
import sys
from argparse import ArgumentParser
from fnmatch import fnmatch
from pathlib import Path

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib


# these hooks are always installed
always_install_hook_files = {"prepare-commit-msg": 'hookmaster prepare-commit-msg "$@"'}


def render_hooks(hooks_dict: dict[str, str], hooks_dir: Path) -> None:
    """Write hook scripts to the given directory."""
    hooks_dir.mkdir(parents=True, exist_ok=True)
    for hook_name, cont in hooks_dict.items():
        target_hook_file = hooks_dir / hook_name
        print(">", target_hook_file)
        target_hook_file.write_text(f"#!/bin/sh\n{cont}\n", newline="\n")
        target_hook_file.chmod(
            target_hook_file.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH
        )


def ensure_gitignore_entry(repo_root: Path, entry: str) -> None:
    """Add an entry to .gitignore if not already present."""
    gitignore = repo_root / ".gitignore"
    if gitignore.exists():
        content = gitignore.read_text()
        if entry in content.splitlines():
            return
        if not content.endswith("\n"):
            content += "\n"
    else:
        content = ""
    gitignore.write_text(content + entry + "\n")


def setup_hooks_dir(repo_root: Path) -> Path:
    """Set up .githooks/ dir and core.hooksPath for a repo."""
    hooks_dir = repo_root / ".githooks"
    hooks_dir.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["git", "-C", str(repo_root), "config", "core.hooksPath", ".githooks"],
        check=True,
    )
    ensure_gitignore_entry(repo_root, ".githooks/")
    return hooks_dir


def add_hooks_to_project(path: Path):
    target_paths = (p.parent for p in path.glob("**/.git"))
    for t in target_paths:
        print("Hooking directory:", t)
        hooks_dir = setup_hooks_dir(t)
        render_hooks(always_install_hook_files, hooks_dir)

    target_paths = (p.parent for p in path.glob("**/githooks.toml"))
    for t in target_paths:
        print("Hooking config file:", t)
        config_file_parsed = parse_config_file(t)
        if config_file_parsed:
            to_add = {
                k: f"hookmaster run {k}"
                for k, v in config_file_parsed.items()
                if isinstance(v, str)
            }
            hooks_dir = setup_hooks_dir(t)
            render_hooks(to_add, hooks_dir)


def summary_line_for_branch(branch: str) -> str:
    if branch in ["HEAD", "master", "main", "dev"]:
        return "Commit to: " + branch
    ticket = re.search(r"[A-Z]+-\d+", branch)
    if not ticket:
        return branch
    ticket = ticket.group(0)
    head, tail = branch.split(ticket)
    if len(tail) == 0:
        return ticket

    return f"{ticket}: {tail.strip().strip('-').replace('-', ' ').capitalize()}"


def prepare_commit_msg(current_message_file: Path):
    with open(current_message_file, "r") as f:
        message = f.read()

    branch = subprocess.run(
        ["git", "symbolic-ref", "--short", "HEAD"], capture_output=True, text=True
    ).stdout.strip()
    summary = summary_line_for_branch(branch)
    if not summary in message:
        message = f"{message}\n{summary}"

    with open(current_message_file, "w") as f:
        f.write(message)


def discover_repo_root(start: Path | None) -> Path | None:
    if start is None:
        start = Path.cwd()
    if start == start.parent:
        return None
    if (start / ".git").exists():
        return start
    return discover_repo_root(start.parent)


def parse_config_file(root_path: Path | None) -> dict[str, str] | None:
    if root_path is None:
        root_path = discover_repo_root(None)
    if root_path is None:
        return None
    config_file = root_path / "githooks.toml"
    if not config_file.exists():
        return None
    return tomllib.loads(config_file.read_text())


def _get_staged_files(repo_root: Path) -> list[str]:
    """Return list of staged file paths (excluding deleted)."""
    result = subprocess.run(
        [
            "git",
            "-C",
            str(repo_root),
            "diff",
            "--cached",
            "--name-only",
            "--diff-filter=d",
        ],
        capture_output=True,
        text=True,
    )
    return [f for f in result.stdout.strip().splitlines() if f]


def _get_tracked_files(repo_root: Path) -> list[str]:
    """Return list of all tracked file paths."""
    result = subprocess.run(
        ["git", "-C", str(repo_root), "ls-files"],
        capture_output=True,
        text=True,
    )
    return [f for f in result.stdout.strip().splitlines() if f]


def _read_staged(repo_root: Path, filepath: str) -> str:
    """Read a file's staged (index) content."""
    result = subprocess.run(
        ["git", "-C", str(repo_root), "show", f":{filepath}"],
        capture_output=True,
        text=True,
    )
    return result.stdout


def _read_worktree(repo_root: Path, filepath: str) -> str:
    """Read a file's working tree content."""
    return (repo_root / filepath).read_text()


def check_forbidden_strings(
    repo_root: Path,
    forbidden: dict[str, str | list[str]],
    *,
    staged_only: bool = True,
) -> bool:
    """Check files for forbidden strings. Returns True if violations found."""
    files = (
        _get_staged_files(repo_root) if staged_only else _get_tracked_files(repo_root)
    )
    if not files:
        return False
    read_fn = _read_staged if staged_only else _read_worktree

    violations = []
    for pattern_str, globs in forbidden.items():
        if isinstance(globs, str):
            globs = [globs]
        matching_files = [
            f
            for f in files
            if f != "githooks.toml" and any(fnmatch(f, g) for g in globs)
        ]
        for filepath in matching_files:
            content = read_fn(repo_root, filepath)
            for line_no, line in enumerate(content.splitlines(), 1):
                if pattern_str in line:
                    violations.append((filepath, line_no, pattern_str))

    if violations:
        print("Forbidden strings found:")
        for filepath, line_no, matched in violations:
            print(f"  {filepath}:{line_no} — {matched!r}")
        return True
    return False


def check_ascii_only(
    repo_root: Path,
    ascii_only_config: dict,
    *,
    staged_only: bool = True,
) -> bool:
    """Check files for non-ASCII characters. Returns True if violations found.

    ascii_only_config is the [ascii-only] table with keys:
        files    - glob patterns to check
        exclude  - glob patterns to skip
        allow    - individual characters to permit (e.g. ["→", "—"])
    """
    globs = ascii_only_config.get("files", [])
    if isinstance(globs, str):
        globs = [globs]
    if not globs:
        return False
    exclude = ascii_only_config.get("exclude", [])
    if isinstance(exclude, str):
        exclude = [exclude]
    exclude.append("githooks.toml")
    allowed = set(ascii_only_config.get("allow", []))
    files = (
        _get_staged_files(repo_root) if staged_only else _get_tracked_files(repo_root)
    )
    if not files:
        return False
    read_fn = _read_staged if staged_only else _read_worktree

    matching_files = [
        f
        for f in files
        if any(fnmatch(f, g) for g in globs) and not any(fnmatch(f, e) for e in exclude)
    ]
    violations = []
    for filepath in matching_files:
        content = read_fn(repo_root, filepath)
        for line_no, line in enumerate(content.splitlines(), 1):
            for col, ch in enumerate(line, 1):
                if ord(ch) > 127 and ch not in allowed:
                    violations.append((filepath, line_no, col, ch))

    if violations:
        print("Non-ASCII characters found:")
        for filepath, line_no, col, ch in violations:
            print(f"  {filepath}:{line_no}:{col} — {ch!r} (U+{ord(ch):04X})")
        return True
    return False


def _parse_size(size_str: str) -> int:
    """Parse a human-readable size string (e.g. '5MB', '500KB') into bytes."""
    size_str = size_str.strip().upper()
    units = {"B": 1, "KB": 1024, "MB": 1024**2, "GB": 1024**3}
    for suffix, multiplier in sorted(units.items(), key=lambda x: -len(x[0])):
        if size_str.endswith(suffix):
            number = size_str[: -len(suffix)].strip()
            return int(float(number) * multiplier)
    return int(size_str)


def _format_size(size_bytes: int) -> str:
    """Format bytes into a human-readable string."""
    if size_bytes >= 1024**3:
        return f"{size_bytes / 1024**3:.1f}GB"
    if size_bytes >= 1024**2:
        return f"{size_bytes / 1024**2:.1f}MB"
    if size_bytes >= 1024:
        return f"{size_bytes / 1024:.1f}KB"
    return f"{size_bytes}B"


def check_max_file_size(
    repo_root: Path,
    limit: str | int,
    *,
    staged_only: bool = True,
) -> bool:
    """Check files against a maximum size limit. Returns True if violations found."""
    if isinstance(limit, str):
        limit_bytes = _parse_size(limit)
    else:
        limit_bytes = int(limit)

    files = (
        _get_staged_files(repo_root) if staged_only else _get_tracked_files(repo_root)
    )
    if not files:
        return False

    violations = []
    for filepath in files:
        if staged_only:
            result = subprocess.run(
                ["git", "-C", str(repo_root), "cat-file", "-s", f":{filepath}"],
                capture_output=True,
                text=True,
            )
            size = int(result.stdout.strip()) if result.stdout.strip() else 0
        else:
            size = (repo_root / filepath).stat().st_size
        if size > limit_bytes:
            violations.append((filepath, size))

    if violations:
        print(f"Files exceed max size ({_format_size(limit_bytes)}):")
        for filepath, size in violations:
            print(f"  {filepath} — {_format_size(size)}")
        print("Use git commit --no-verify to bypass.")
        return True
    return False


def check_do_not_modify(
    repo_root: Path,
    globs: str | list[str],
    *,
    staged_only: bool = True,
) -> bool:
    """Check that protected files are not being modified. Returns True if violations found."""
    if isinstance(globs, str):
        globs = [globs]
    if not globs:
        return False

    files = (
        _get_staged_files(repo_root) if staged_only else _get_tracked_files(repo_root)
    )
    if not files:
        return False

    violations = [f for f in files if any(fnmatch(f, g) for g in globs)]

    if violations:
        print("Protected files modified:")
        for filepath in violations:
            print(f"  {filepath}")
        print("Use git commit --no-verify to bypass.")
        return True
    return False


def run_hook_from_config(hook_name: str):
    repo_root = discover_repo_root(None)
    commands = parse_config_file(repo_root)
    if not commands:
        print(f"No githooks.toml file found, nothing to do for hook: {hook_name}.")
        return

    if hook_name == "pre-commit" and "forbidden-strings" in commands:
        if check_forbidden_strings(repo_root, commands["forbidden-strings"]):
            sys.exit(1)

    if hook_name == "pre-commit" and "ascii-only" in commands:
        if check_ascii_only(repo_root, commands["ascii-only"]):
            sys.exit(1)

    if hook_name == "pre-commit" and "max-file-size" in commands:
        if check_max_file_size(repo_root, commands["max-file-size"]):
            sys.exit(1)

    if hook_name == "pre-commit" and "do-not-modify" in commands:
        if check_do_not_modify(repo_root, commands["do-not-modify"]):
            sys.exit(1)

    command = commands.get(hook_name)
    if command is None or not isinstance(command, str):
        if command is None:
            print(f"Hook {hook_name} not found in config.")
        return
    if command == "":
        print(f"Hook {hook_name} is empty, nothing to do.")
        return

    ret = subprocess.run(command, shell=True, check=False, cwd=repo_root)
    if ret.returncode != 0:
        print(f"Hook {hook_name} failed with code {ret.returncode}.")
        sys.exit(ret.returncode)


def check_working_tree():
    """Run all checks against the working tree (not just staged files)."""
    repo_root = discover_repo_root(None)
    commands = parse_config_file(repo_root)
    if not commands:
        print("No githooks.toml file found.")
        return

    failed = False
    if "forbidden-strings" in commands:
        if check_forbidden_strings(
            repo_root, commands["forbidden-strings"], staged_only=False
        ):
            failed = True

    if "ascii-only" in commands:
        if check_ascii_only(repo_root, commands["ascii-only"], staged_only=False):
            failed = True

    if "max-file-size" in commands:
        if check_max_file_size(repo_root, commands["max-file-size"], staged_only=False):
            failed = True

    if "do-not-modify" in commands:
        if check_do_not_modify(repo_root, commands["do-not-modify"], staged_only=False):
            failed = True

    if failed:
        sys.exit(1)
    else:
        print("All checks passed.")


def get_hooks_dir(repo_root: Path) -> Path:
    """Get the hooks directory, checking core.hooksPath first."""
    result = subprocess.run(
        ["git", "-C", str(repo_root), "config", "core.hooksPath"],
        capture_output=True,
        text=True,
    )
    if result.returncode == 0 and result.stdout.strip():
        hooks_path = Path(result.stdout.strip())
        if not hooks_path.is_absolute():
            hooks_path = repo_root / hooks_path
        return hooks_path
    return repo_root / ".git" / "hooks"


def list_hooks():
    repo_root = discover_repo_root(None)
    hooks_dir = get_hooks_dir(repo_root)
    for hook in hooks_dir.glob("*"):
        print(">", hook.name)
        with open(hook, "r") as f:
            content = f.read()
        print(content.strip())
        print()


def remove_hooks():
    repo_root = discover_repo_root(None)
    hooks_dir = get_hooks_dir(repo_root)
    for hook in hooks_dir.glob("*"):
        print("Removing hook:", hook.name)
        hook.unlink()
    subprocess.run(
        ["git", "-C", str(repo_root), "config", "--unset", "core.hooksPath"],
        capture_output=True,
    )
    print(f"All hooks removed. Run `hookmaster add {repo_root}` to re-add them.")


def generate_config(repo_root: Path) -> str:
    """Generate a githooks.toml tailored to the repo contents."""
    tracked = subprocess.run(
        ["git", "-C", str(repo_root), "ls-files"],
        capture_output=True,
        text=True,
    )
    tracked_files = [f for f in tracked.stdout.strip().splitlines() if f]

    def _has_ext(*exts: str) -> bool:
        return any(any(f.endswith(ext) for ext in exts) for f in tracked_files)

    has_python = _has_ext(".py")
    has_js = _has_ext(".js")
    has_ts = _has_ext(".ts", ".tsx")
    has_ruby = _has_ext(".rb")
    has_go = _has_ext(".go")
    has_rust = _has_ext(".rs")
    has_shell = _has_ext(".sh")

    # --- pre-commit ---
    if has_python:
        pre_commit = "ruff format --check ."
    elif has_js or has_ts:
        pre_commit = "npx prettier --check ."
    elif has_go:
        pre_commit = "gofmt -l ."
    elif has_rust:
        pre_commit = "cargo fmt --check"
    else:
        pre_commit = ""

    # --- pre-push ---
    if has_python:
        pre_push = "pytest"
    elif has_js or has_ts:
        pre_push = "npm test"
    elif has_go:
        pre_push = "go test ./..."
    elif has_rust:
        pre_push = "cargo test"
    else:
        pre_push = ""

    # --- ascii-only (must be before any [section] headers) ---
    ascii_globs = ["*.toml", "*.yml", "*.yaml", "*.json"]
    if has_shell:
        ascii_globs.append("*.sh")
    if has_python:
        ascii_globs.append("*.py")
    if has_js:
        ascii_globs.append("*.js")
    if has_ts:
        ascii_globs.extend(["*.ts", "*.tsx"])
    if has_ruby:
        ascii_globs.append("*.rb")
    if has_go:
        ascii_globs.append("*.go")
    if has_rust:
        ascii_globs.append("*.rs")

    lines = []
    lines.append(f'pre-commit = "{pre_commit}"')
    lines.append(f'pre-push = "{pre_push}"')

    # --- max-file-size ---
    lines.append('max-file-size = "1MB"')

    # --- ascii-only ---
    # scan git-tracked files for non-ASCII characters already in use
    # track which chars appear only in test dirs vs source
    test_dir_prefixes = ("test/", "tests/", "test_", "spec/", "specs/")
    source_chars = set()
    test_chars = set()
    test_dirs_with_unicode = set()
    for filepath in tracked_files:
        if filepath == "githooks.toml":
            continue
        if not any(fnmatch(filepath, g) for g in ascii_globs):
            continue
        try:
            text = (repo_root / filepath).read_text()
        except (UnicodeDecodeError, OSError):
            continue
        file_chars = {ch for ch in text if ord(ch) > 127}
        if not file_chars:
            continue
        is_test = filepath.startswith(test_dir_prefixes) or Path(
            filepath
        ).name.startswith("test_")
        if is_test:
            test_chars.update(file_chars)
            # extract the top-level test directory
            parts = Path(filepath).parts
            if len(parts) > 1 and parts[0] in ("test", "tests", "spec", "specs"):
                test_dirs_with_unicode.add(parts[0] + "/*")
        else:
            source_chars.update(file_chars)

    ascii_globs_str = "[" + ", ".join(f'"{g}"' for g in ascii_globs) + "]"
    lines.append("")
    lines.append("[ascii-only]")
    lines.append(f"files = {ascii_globs_str}")

    # suggest exclude if test dirs contain unicode not in source
    test_only_chars = test_chars - source_chars
    if test_only_chars and test_dirs_with_unicode:
        exclude_str = (
            "[" + ", ".join(f'"{d}"' for d in sorted(test_dirs_with_unicode)) + "]"
        )
        lines.append(f"exclude = {exclude_str}")
    else:
        lines.append('# exclude = ["tests/*"]')

    if source_chars:
        sorted_chars = sorted(source_chars)
        allow_str = "[" + ", ".join(f'"{ch}"' for ch in sorted_chars) + "]"
        lines.append(f"allow = {allow_str}")
    else:
        lines.append('# allow = ["\u2192", "\u2014"]')

    # --- forbidden-strings ---
    forbidden = {}
    forbidden["<<<<<<< "] = "*"
    if has_python:
        forbidden["breakpoint()"] = "*.py"
    if has_js or has_ts:
        js_globs = [g for flag, g in [(has_js, "*.js"), (has_ts, "*.ts")] if flag]
        forbidden["console.log"] = js_globs
        forbidden["debugger"] = js_globs
    if has_ruby:
        forbidden["binding.pry"] = "*.rb"

    # --- forbidden-strings ---
    lines.append("")
    lines.append("[forbidden-strings]")
    for pattern_str, globs in forbidden.items():
        if isinstance(globs, list) and len(globs) == 1:
            globs = globs[0]
        if isinstance(globs, list):
            globs_str = "[" + ", ".join(f'"{g}"' for g in globs) + "]"
        else:
            globs_str = f'"{globs}"'
        lines.append(f'"{pattern_str}" = {globs_str}')
    lines.append("")

    return "\n".join(lines)


def init_hookmaster(roots: list[Path] | None = None) -> None:
    if roots is None:
        roots = [Path.cwd()]
    for root in roots:
        if not root.exists():
            print(f"Path {root} does not exist.")
            continue
        repo_root = discover_repo_root(root)
        if repo_root is None:
            print(f"No git repo found in {root}.")
            continue
        toml_file = repo_root / "githooks.toml"
        if toml_file.exists():
            print(f"githooks.toml already exists in {repo_root}.")
            continue
        config = generate_config(repo_root)
        with toml_file.open("w") as f:
            f.write(config)

        print(f"Generated {toml_file}:")
        print(config)
        add_hooks_to_project(root)


def main():
    parser = ArgumentParser(description="Hookmaster CLI")
    subparsers = parser.add_subparsers(dest="command")
    subparsers.required = True
    add_cmd = subparsers.add_parser("add", help="Add hooks to a project")
    add_cmd.add_argument("path", help="Project path or directory")

    prep_commit_msg = subparsers.add_parser(
        "prepare-commit-msg", help="Prepare commit message"
    )
    prep_commit_msg.add_argument("current_message_file", help="Current commit message")
    # you can ignore these arguments for most handlers
    prep_commit_msg.add_argument(
        "source",
        nargs="?",
        help="Source of the commit message: 'commit', 'merge' or 'squash'",
    )
    prep_commit_msg.add_argument("commit_object", nargs="?", help="Sha or whatever")

    run_cmd = subparsers.add_parser("run", help="Run a hook from githooks.toml")
    run_cmd.add_argument("hook_name", help="Name of the hook to run")

    check_cmd = subparsers.add_parser(
        "check", help="Run checks against the working tree"
    )
    ls_cmd = subparsers.add_parser("ls", help="List hooks")
    remove_cmd = subparsers.add_parser("remove", help="Remove hooks")
    init_cmd = subparsers.add_parser(
        "init",
        help="Initialize hookmaster for a repo - create sample githooks.toml and register the hooks",
    )
    init_cmd.add_argument("path", nargs="?", help="Project path or directory")

    parsed = parser.parse_args()

    if parsed.command == "add":
        path = Path(parsed.path).absolute().resolve()
        if not path.exists():
            print(f"Path {path} does not exist.")
            return
        add_hooks_to_project(path)
    elif parsed.command == "prepare-commit-msg":
        prepare_commit_msg(Path(parsed.current_message_file))
    elif parsed.command == "run":
        run_hook_from_config(parsed.hook_name)
    elif parsed.command == "check":
        check_working_tree()
    elif parsed.command == "ls":
        list_hooks()
    elif parsed.command == "remove":
        remove_hooks()
    elif parsed.command == "init":
        init_hookmaster(
            [Path(parsed.path).absolute().resolve()] if parsed.path else None
        )
    else:
        parser.print_help()
