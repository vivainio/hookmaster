import re
import subprocess
import sys
from argparse import ArgumentParser
from pathlib import Path

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib


# these hooks are always installed
always_install_hook_files = {"prepare-commit-msg": 'hookmaster prepare-commit-msg "$@"'}


def render_hooks_by_dict_file(hooks_dict: dict[str, str], repo_root: Path) -> None:
    """Render hooks by dict file.

    Args:
        hooks_dict (dict[str,str]): Dictionary of hooks to render.
    """
    for hook_name, cont in hooks_dict.items():
        target_hook_file = repo_root / ".git" / "hooks" / hook_name
        print(">", target_hook_file)
        target_hook_file.write_text(f"#!/bin/sh\n{cont}\n")


def add_hooks_to_project(path: Path):
    target_paths = (p.parent for p in path.glob("**/.git"))
    for t in target_paths:
        print("Hooking directory:", t)
        render_hooks_by_dict_file(always_install_hook_files, t)

    target_paths = (p.parent for p in path.glob("**/githooks.toml"))
    for t in target_paths:
        print("Hooking config file:", t)
        config_file_parsed = parse_config_file(t)
        if config_file_parsed:
            to_add = {k: f"hookmaster run {k}" for k in config_file_parsed}

            render_hooks_by_dict_file(to_add, t)


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

    return f"{ticket}: {tail.strip().strip("-").replace("-", " ").capitalize()}"


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


def run_hook_from_config(hook_name: str):
    repo_root = discover_repo_root(None)
    commands = parse_config_file(repo_root)
    if not commands:
        print(f"No githooks.toml file found, nothing to do for hook: {hook_name}.")
        return

    command = commands.get(hook_name)
    if not command:
        print(f"Hook {hook_name} not found in config.")
        return

    ret = subprocess.run(command, shell=True, check=False, cwd=repo_root)
    if ret.returncode != 0:
        print(f"Hook {hook_name} failed with code {ret.returncode}.")
        sys.exit(ret.returncode)


def list_hooks():
    repo_root = discover_repo_root(None)
    hooks = repo_root.glob(".git/hooks/*")
    for hook in hooks:
        print(">", hook.name)
        with open(hook, "r") as f:
            content = f.read()
        print(content.strip())
        print()


def remove_hooks():
    repo_root = discover_repo_root(None)
    hooks = repo_root.glob(".git/hooks/*")
    for hook in hooks:
        print("Removing hook:", hook.name)
        hook.unlink()
    else:
        print(f"All hooks removed. Run `hookmaster add {repo_root}` to re-add them.")


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

    ls_cmd = subparsers.add_parser("ls", help="List hooks")
    remove_cmd = subparsers.add_parser("remove", help="Remove hooks")

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
    elif parsed.command == "ls":
        list_hooks()
    elif parsed.command == "remove":
        remove_hooks()
