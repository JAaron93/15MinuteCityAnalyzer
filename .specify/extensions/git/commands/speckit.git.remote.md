---
description: "Detect Git remote URL for GitHub integration"
---

# Detect Git Remote URL

Detect the Git remote URL for integration with GitHub services (e.g., issue creation).

## Prerequisites

- Distinguish between three cases for Git availability:
  1. **Git binary missing**: Detect via `command -v git` or `git --version`. If missing, return empty and output:
     `[specify] Warning: Git not installed; cannot determine remote URL`
  2. **Git present but not in a work tree**: Call `git rev-parse --is-inside-work-tree 2>/dev/null`. Inspect both its exit code and its stdout. If it fails or outputs the literal string `false`, return empty and output:
     `[specify] Warning: Not in a Git repository; cannot determine remote URL`
  3. **Git present and in a work tree**: Proceed with execution when the command exits successfully and prints the literal string `true`.

## Execution

Run the following command to get the remote URL:

```bash
git config --get remote.origin.url
```

## Output

Parse the remote URL and determine:

1. **Repository owner**: Extract from the URL (e.g., `github` from `https://github.com/github/spec-kit.git`)
2. **Repository name**: Extract from the URL (e.g., `spec-kit` from `https://github.com/github/spec-kit.git`)
3. **Is GitHub**: Whether the remote points to a GitHub repository

Supported URL formats:
- HTTPS: `https://github.com/<owner>/<repo>.git`
- HTTPS (without `.git`): `https://github.com/<owner>/<repo>`
- SSH: `git@github.com:<owner>/<repo>.git`
- SSH (without `.git`): `git@github.com:<owner>/<repo>`

The trailing `.git` suffix is optional; both variants are fully supported by the speckit remote handling.

> [!CAUTION]
> ONLY report a GitHub repository if the remote URL actually points to github.com.
> Do NOT assume the remote is GitHub if the URL format doesn't match.

## Graceful Degradation

If Git is not installed, the directory is not a Git repository, or no remote is configured:
- Output a warning (consistent with the Prerequisites section)
- Return an empty result
- Do NOT error — other workflows should continue without Git remote information
