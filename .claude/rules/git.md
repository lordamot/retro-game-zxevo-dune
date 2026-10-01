# Git Usage

## Branch Model

| Branch | Purpose                                         |
|--------|-------------------------------------------------|
| `main` | ready working solution                          |
| `feat/<name>` | Feature branches (short kebab-case name) |

## Workflow

Work onto mine branch - allowed.
Never push.
Always ask before commit something.

## Commit Messages

Short imperative subject line, no period. Examples:

```
add dsk builder
fix map generation
```

- Keep subject under 72 characters
- No ticket/issue prefix required
- English only

## What Not to Commit

- `/build/` — compilation and transform results
- `/tmp/` — temporary folder for anything
