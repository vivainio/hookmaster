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

For any other hooks, you can specify them in githooks.toml:

```toml
pre-commit = "python tasks.py format"
pre-post = "pytest"

# empty string does nothing in the hook
commit-msg = ""
```

The format should be obvious. The specified command will always be run in repository root.

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

You can block commits that contain specific literal strings by adding a `[forbidden-strings]` section to `githooks.toml`. This is checked automatically during `pre-commit` against staged files only.

```toml
[forbidden-strings]
"<<<<<<< " = "*"
"console.log" = ["*.py", "*.ts"]
"binding.pry" = "*.rb"
```

- **Key**: literal string to search for
- **Value**: glob pattern(s) — `"*"` for all files, a string for one pattern, or a list for multiple

Example: prevent a private PyPI mirror URL from leaking into `uv.lock`:

```toml
[forbidden-strings]
"internal.artifactory.example.com" = "uv.lock"
```

## How hooks are installed

Hookmaster uses `.githooks/` with `core.hooksPath` instead of writing directly to `.git/hooks/`. This means the hook scripts live in `.githooks/` at the repo root, and git is configured to look there via `git config core.hooksPath .githooks`. The `.githooks/` directory is added to `.gitignore` since the scripts are just thin wrappers that call `hookmaster`. This approach is used instead of `.git/hooks/` because it needs to support git worktrees across the WSL boundary, where `.git/hooks/` may not resolve correctly.
