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

pr
```

The format should be obvious.

The hook created by this will look like:

```sh
#!/bin/sh
hookmaster run pre-commit
```

The command `hookmaster run` will load the `githooks.toml` file, find the hook and run it.
You can use command `hookmaster run pre-commit` to test the hook without actually committing
anything.

Usig `githooks.toml` is optional, if you just want to get the commit message hook.

To easily initalize your repo with githooks.toml, run `hookmaster init`. It creates a sample
githooks.toml and initializes the hooks. Edit the `githooks.toml` file to customize
your hooks.
