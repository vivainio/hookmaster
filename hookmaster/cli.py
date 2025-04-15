from argparse import ArgumentParser
from pathlib import Path
import shutil
import subprocess
import re
import sys

ROOT = Path(__file__).parent

simple_hooks = list(ROOT.glob("hooks/*"))

def add_hooks_to_project(path: Path):
    target_paths = path.glob("**/.git/hooks")

    for t in target_paths:
        print("Hooking directory:", t)

        for hook in simple_hooks:
            print(">", t)
            shutil.copy(hook, t)


def summary_line_for_branch(branch: str) -> str:
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

    branch = subprocess.run(["git", "symbolic-ref", "--short", "HEAD"], capture_output=True, text=True).stdout.strip()

    summary = summary_line_for_branch(branch)
    if not summary in message:
        message = f"\n{summary}\n{message}"

    with open(current_message_file, "w") as f:
        f.write(message)

def main():
    parser = ArgumentParser(description="Hookmaster CLI")
    subparsers = parser.add_subparsers(dest="command")
    subparsers.required = True
    add_cmd = subparsers.add_parser("add", help="Add hooks to a project")
    add_cmd.add_argument("path", help="Project path or directory")

    prep_commit_msg = subparsers.add_parser("prepare-commit-msg", help="Prepare commit message")
    prep_commit_msg.add_argument("current_message_file", help="Current commit message")
    # you can ignore these arguments for most handlers
    prep_commit_msg.add_argument("source", nargs='?', help="Source of the commit message: 'commit', 'merge' or 'squash'")
    prep_commit_msg.add_argument("commit_object", nargs='?', help="Sha or whatever")

    parsed = parser.parse_args()

    if parsed.command == "add":
        path = Path(parsed.path).absolute().resolve()
        if not path.exists():
            print(f"Path {path} does not exist.")
            return
        add_hooks_to_project(path)
    elif parsed.command == "prepare-commit-msg":
        prepare_commit_msg(Path(parsed.current_message_file))

