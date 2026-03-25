# Hookmaster

Some nice git hooks for your pleasure. 

Problem: 

- You have a policy where every commit message should mention the jira ticket it applies to. You 
have them in the branch name, and can't be arsed to type them manually to each commit message.
Hookmaster provides you with a nice "default" commit message formatter in prepare-commit-msg hook.
- You want to specify commands to run as different git hooks, in a file you share with 
your team in git.

## Installation

```sh
uv tool install hookmaster
```

## Usage

To add 'hookmaster' hooks to all projects under /my/path

```sh
hookmaster add /my/path
```

Now, you get a nice commit message hook that maps branch

`/bugfixes/SOMETICKET-123-do-stuff`

to 

`SOMETICKET-123: Do stuff`

The hooks themselves relay the call to hookmaster, e.g. prepare-commit-msg hooks created by hookmaster looks like this:

```sh
#!/bin/sh
hookmaster prepare-commit-msg "$@"
```

This delegates the message creation to globally installed hookmaster application. This means fixes to hookmaster benefit all your repositories at once.

## githooks.toml

You can specify commands to run as git hooks in `githooks.toml` at the repo root:

```toml
# Top-level keys are git hook names, values are shell commands
pre-commit = "ruff format --check ."
pre-push = "pytest"

# empty string does nothing in the hook
commit-msg = ""

# Optional: block commits with oversized files (accepts KB, MB, GB or plain bytes)
max-file-size = "1MB"

# Optional: block modifications to specific files or paths
# do-not-modify = ["package-lock.json", "vendor/*"]

# Optional: block commits containing literal strings in matching files
[forbidden-strings]
"<<<<<<< " = "*"                    # all files
"console.log" = ["*.py", "*.ts"]    # multiple globs
"binding.pry" = "*.rb"              # single glob
```

Top-level keys are standard [git hook names](https://git-scm.com/docs/githooks). The value is a shell command run from the repo root. An empty string is ignored. `max-file-size` rejects staged files exceeding the given limit. `do-not-modify` rejects changes to matching paths. Both can be bypassed with `git commit --no-verify`. The `[forbidden-strings]` table is special — keys are literal strings to search for, values are glob pattern(s) to match against staged file paths.

The hook created by this will look like:

```sh
#!/bin/sh
hookmaster run pre-commit
```

The command `hookmaster run` will load the `githooks.toml` file, find the hook and run it.
You can use command `hookmaster run pre-commit` to test the hook without actually committing
anything.

Using `githooks.toml` is optional, if you just want to get the commit message hook.

To easily initialize your repo with githooks.toml, run `hookmaster init`. It creates a sample
githooks.toml and initializes the hooks. Edit the `githooks.toml` file to customize
your hooks.

## Forbidden strings

The `[forbidden-strings]` section is checked automatically during `pre-commit` against staged files only. This is a cheap way to prevent AI coding agents from accidentally committing things like merge conflict markers, debug statements, or private URLs — the kind of mistakes that slip through when an agent is committing on your behalf.

Example: prevent a private PyPI mirror URL from leaking into `uv.lock`:

```toml
[forbidden-strings]
"jfrog.io" = "uv.lock"
```

## How hooks are installed

Hookmaster uses `.githooks/` with `core.hooksPath` instead of writing directly to `.git/hooks/`. This means the hook scripts live in `.githooks/` at the repo root, and git is configured to look there via `git config core.hooksPath .githooks`. The `.githooks/` directory is added to `.gitignore` since the scripts are just thin wrappers that call `hookmaster`. This approach is used instead of `.git/hooks/` because it needs to support git worktrees across the WSL boundary, where `.git/hooks/` may not resolve correctly.
