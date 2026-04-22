---
description: Validate current branch follows feature branch naming conventions
---


<!-- Extension: git -->
<!-- Config: .specify/extensions/git/ -->
# Validate Feature Branch

Validate that the current Git branch follows the expected feature branch naming conventions.

## Prerequisites

- Check if Git is available by running `git rev-parse --is-inside-work-tree 2>/dev/null`
- Check the exact command exit code rather than parsing output: treat an exit code of `0` as "inside a work tree" and any non-zero exit code as not present.
- If Git is not available (non-zero exit code), output a warning and skip validation:
  ```
  [specify] Warning: Git repository not detected; skipped branch validation
  ```

## Validation Rules

Get the current branch name:

```bash
git rev-parse --abbrev-ref HEAD
```

> [!NOTE]
> When the repository is in a detached HEAD state, the `git rev-parse --abbrev-ref HEAD` command returns the literal string "HEAD". This will not match the feature-branch patterns below. Callers should treat this condition as a validation failure rather than skipping with a warning.

The branch name must match one of these patterns:

1. **Sequential**: `^[0-9]{3,}-` (e.g., `001-feature-name`, `042-fix-bug`, `1000-big-feature`)
2. **Timestamp**: `^[0-9]{8}-[0-9]{6}-` (e.g., `20260319-143022-feature-name`)

## Execution

If on a feature branch (matches either pattern):
- Output: `✓ On feature branch: <branch-name>`
- Check if the corresponding spec directory exists under `specs/` using a programmatic filesystem glob (not shell commands):
  - For sequential branches, build the glob pattern `specs/<prefix>-*` where prefix matches the numeric portion.
  - For timestamp branches, build the glob pattern `specs/<prefix>-*` where prefix matches the `YYYYMMDD-HHMMSS` portion.
- Collect all matching directories from the glob search and handle the results deterministically:
  - If zero matches: Log `⚠ No spec directory found for prefix <prefix>`
  - If exactly one match: Log `✓ Spec directory found: <path>`
  - If multiple matches: Treat this as ambiguous and log an error listing all matched paths (do not silently pick the first). This ensures callers receive clear status and the full list of matches when there is ambiguity.

If NOT on a feature branch:
- Output: `✗ Not on a feature branch. Current branch: <branch-name>`
- Output: `Feature branches should be named like: 001-feature-name or 20260319-143022-feature-name`

## Graceful Degradation

If Git is not installed or the directory is not a Git repository:
- Check the `SPECIFY_FEATURE` environment variable as a fallback.
- If `SPECIFY_FEATURE` is present and matches naming patterns, emit the same structured success message used by the Execution section:
  - Output: `✓ On feature branch: <SPECIFY_FEATURE>` (validation passed).
  - Proceed with the spec directory existence checks as defined in the Execution section.
- If `SPECIFY_FEATURE` is present but fails validation, emit the structured error/exit message:
  - Output: `✗ Not on a feature branch. Current fallback SPECIFY_FEATURE: <invalid-value>`
  - Output reason/pattern mismatch: `Feature branches should be named like: 001-feature-name or 20260319-143022-feature-name`
  - Output warning: `⚠ Warning: Validation failed for SPECIFY_FEATURE graceful degradation fallback. Process exited or gracefully degraded.`
- If `SPECIFY_FEATURE` is not set, skip validation with a warning.