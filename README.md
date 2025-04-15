# Hookmaster

Some nice git hooks for your pleasure. 

Problem: you have a policy where every commit message should mention the jira ticket it applies to. You 
have them in the branch name, and can't be arsed to type them manually to each commit message.

## Installation

```
uv tool install hookmaster
```

## Usage

To add 'hookmaster' hooks to all projects under /my/path

```
hookmaster add /my/path
```

Now, you get a nice commit message hook that maps branch

`/bugfixes/SOMETICKET-123-do-stuff`

to 

`SOMETICKET-123: Do stuff`

The hooks themselves relay the call to hookmaster, e.g. prepare-commit-message hooks created by hookmaster looks like this:

```sh
#!/bin/sh
hookmaster prepare-commit-msg "$@"
```

This delegates the message creation to globally installed hookmaster application. This means fixes to hookmaster benefit all your 
repositories at once.
