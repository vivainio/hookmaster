from argparse import ArgumentParser
from pathlib import Path
import shutil
ROOT = Path(__file__).parent

simple_hooks = list(ROOT.glob("hooks/*"))
print("Simple hooks:", simple_hooks)
def add_hooks_to_project(path: Path):
    target_paths = path.glob("**/.git/hooks")

    for t in target_paths:
        print("Hooking directory:", t)

        for hook in simple_hooks:
            print(">", t)
            shutil.copy(hook, t)
 

def main():
    parser = ArgumentParser(description="Hookmaster CLI")
    subparsers = parser.add_subparsers(dest="command")
    subparsers.required = True
    add_cmd = subparsers.add_parser("add", help="Add hooks to a project")
    add_cmd.add_argument("path", help="Project path or directory")

    parsed = parser.parse_args()

    if parsed.command == "add":
        path = Path(parsed.path).absolute().resolve()
        if not path.exists():
            print(f"Path {path} does not exist.")
            return

        add_hooks_to_project(path)


