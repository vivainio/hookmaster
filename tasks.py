"""Simple, fast and fun task runner, not unlike gulp / grunt (but zero dep)"""

import os
from pathlib import Path
import shlex
import subprocess
import sys
import textwrap
from argparse import ArgumentParser, Namespace
import inspect
import shutil
from types import ModuleType
from typing import Callable

# add tasks from other modules by adding modules to TASK_MODULES list
# if you don't need them, just leave this list empty

TASK_MODULES: list[ModuleType] = []


def do_format(_args: list[str]) -> None:
    """Reformat all code"""
    c(["ruff", "format", "."])


def do_formatcheck(_args: list[str]) -> None:
    """Reformat all code"""
    r = c(["ruff", "format", "--check"], check=False)
    if r != 0:
        emit("Code is not formatted, run `python tasks.py format` to fix")
        sys.exit(1)


def do_lint(_args: list[str]) -> None:
    """Check with ruff"""
    c(["ruff", "check"])


def do_test(_args: list[str]) -> None:
    os.chdir("test")
    c("pytest")


def do_publish(args) -> None:
    shutil.rmtree("dist", ignore_errors=True)
    c(["fistbump", "--check"])
    c(["python", "-m", "build"])
    c(["twine", "upload", "dist/*"])


def default() -> None:
    _show_help()


# library functions here (or in own module, whatever, I don't care)

emit = print


def c(
    cmd: list[str | Path] | str, check=True, shell=False, cwd: str | Path | None = None
) -> int | None:
    """Run a shell command"""
    cmdtext = shlex.join(str(s) for s in cmd) if isinstance(cmd, list) else cmd
    cwd_text = f"{cwd} " if cwd else ""
    cmdtext = f"{cwd_text}> {cmdtext}"
    emit(cmdtext)
    r = subprocess.run(cmd, check=check, shell=shell, cwd=cwd)
    if not check:
        return r.returncode
    return None


# scaffolding starts. Do not edit below


def _is_argparse_function(f) -> bool:
    annotations = list(p.annotation for p in inspect.signature(f).parameters.values())
    if len(annotations) == 1 and annotations[0] == Namespace:
        return True
    return False


def _collect_args_from_argparse_function(f) -> ArgumentParser:
    parser = f(None)
    if not isinstance(parser, ArgumentParser):
        raise ValueError(
            "Function taking argparse.Namespace must return ArgumentParser when called with None"
        )
    parser.prog = "python tasks.py " + f.__name__[3:]
    return parser


def _discover_tasks() -> dict[str, Callable]:
    all_tasks_dict = globals().copy()
    for mod in TASK_MODULES:
        all_tasks_dict.update(mod.__dict__)

    return {t[3:]: f for (t, f) in all_tasks_dict.items() if t.startswith("do_")}


def _task_by_index(index: int) -> str:
    task_names = list(_discover_tasks().keys())
    task_names.sort()
    return task_names[index - 1]


def _show_help() -> None:
    tasks = list(_discover_tasks().items())
    tasks.sort()

    for index, (name, func) in enumerate(tasks):
        nametext = f"{index+1:<2} {name}:"

        if _is_argparse_function(func):
            parser = _collect_args_from_argparse_function(func)
            help_text = parser.format_help()
            emit(nametext)
            emit(textwrap.indent(help_text, " " * 4))
        else:
            emit(f"{nametext:<15} {func.__doc__ or ''}")


def main() -> None:
    """Launcher. Do not modify."""
    if len(sys.argv) < 2:
        default()
        return
    task_name = sys.argv[1]
    if task_name.isdigit():
        task_name = _task_by_index(int(task_name))

    task_function = _discover_tasks().get(task_name)
    if task_function:
        if _is_argparse_function(task_function):
            parser = _collect_args_from_argparse_function(task_function)
            args = parser.parse_args(sys.argv[2:])
            task_function(args)
            return
        else:
            task_function(sys.argv[2:])
            return

    if sys.argv[-1] == "-h":
        emit(
            textwrap.dedent(task_function.__doc__).strip()
            if task_function.__doc__
            else "No documentation for this command",
        )
        return
    if not task_function:
        _show_help()
        return


if __name__ == "__main__":
    main()
