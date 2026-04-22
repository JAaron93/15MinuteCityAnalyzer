---
description: Convert existing tasks into actionable, dependency-ordered GitHub issues for the feature based on available design artifacts.
tools: ['github/github-mcp-server/issue_write']
---

## User Input

```text
$ARGUMENTS
```

You **MUST** consider the user input before proceeding (if not empty).

## Pre-Execution Checks

**Check for extension hooks (before tasks-to-issues conversion)**:
- Check if `.specify/extensions.yml` exists in the project root.
- If it exists, read it and look for entries under the `hooks.before_taskstoissues` key
- If the YAML cannot be parsed or is invalid, skip hook checking silently and continue normally
- Filter out hooks where `enabled` is explicitly `false`. Treat hooks without an `enabled` field as enabled by default.
- For each remaining hook, do **not** attempt to interpret or evaluate hook `condition` expressions:
  - If the hook has no `condition` field, or it is null/empty, treat the hook as executable
  - If the hook defines a non-empty `condition`, skip the hook and leave condition evaluation to the HookExecutor implementation
- For each executable hook, output the following based on its `optional` flag:
  - **Optional hook** (`optional: true`):
    ```
    ## Extension Hooks

    **Optional Pre-Hook**: {extension}
    Command: `/{command}`
    Description: {description}

    Prompt: {prompt}
    To execute: `/{command}`
    ```
  - **Mandatory hook** (`optional: false`):
    ```
    ## Extension Hooks

    **Automatic Pre-Hook**: {extension}
    Executing: `/{command}`
    EXECUTE_COMMAND: {command}

    Wait for the result of the hook command before proceeding to the Outline.
    ```
- If no hooks are registered or `.specify/extensions.yml` does not exist, skip silently

## Outline

1. Run `.specify/scripts/bash/check-prerequisites.sh --json --require-tasks --include-tasks` from repo root and parse FEATURE_DIR and AVAILABLE_DOCS list. All paths must be absolute. For single quotes in args like "I'm Groot", use escape syntax: e.g 'I'\''m Groot' (or double-quote if possible: "I'm Groot").
1. From the executed script, extract the path to **tasks**.
1. Get the Git remote by running:

```bash
git config --get remote.origin.url
```

> [!CAUTION]
> **REPOSITORY VALIDATION REQUIRED**
> 1. Verify the Git remote is a valid GitHub URL before proceeding.
> 2. ONLY create issues in the exact repository matching that remote.
> 3. ABORT the process immediately if validation fails or the remote is not a GitHub repository.

1. **Iterative Issue Creation**: For each task in the list, use the GitHub MCP server to create a new issue in the repository corresponding to the Git remote URL.
   - **Do NOT abort on the first failure**. Attempt to create issues for all tasks.
   - **Retry Policy**: Retry transient failures from the GitHub MCP API (e.g., HTTP 5xx errors or rate-limit 429s) using exponential backoff.
     - **Max Retries**: 3 attempts per task
     - **Backoff**: 2-second initial delay, doubling after each failure (2s, 4s, 8s).
   - **Error Classification**:
     - *Transient*: Rate limits, network timeouts, server errors (5xx).
     - *Permanent*: Validation errors (400), authentication failures (401/403), repository not found (404). Do not retry permanent errors.
1. **Execution Report**: After processing all tasks, collect and report the per-task results. Provide a machine-readable summary (structured markdown or JSON) containing:
   - `succeeded`: List of successfully created issues (include task IDs and issue URLs)
   - `failed_retryable`: List of tasks that failed after exhausting retries due to transient errors
   - `failed_permanent`: List of tasks that failed due to permanent errors
   - **Exit Status**: End the workflow with a clear success state if all tasks succeeded. If any task failed, surface a partial-failure or full-failure alert to the caller so they can programmatically detect the outcome.

## Post-Execution Checks

**Check for extension hooks (after tasks-to-issues conversion)**:
Check if `.specify/extensions.yml` exists in the project root.
- If it exists, read it and look for entries under the `hooks.after_taskstoissues` key
- If the YAML cannot be parsed or is invalid, skip hook checking silently and continue normally
- Filter out hooks where `enabled` is explicitly `false`. Treat hooks without an `enabled` field as enabled by default.
- For each remaining hook, do **not** attempt to interpret or evaluate hook `condition` expressions:
  - If the hook has no `condition` field, or it is null/empty, treat the hook as executable
  - If the hook defines a non-empty `condition`, skip the hook and leave condition evaluation to the HookExecutor implementation
- For each executable hook, output the following based on its `optional` flag:
  - **Optional hook** (`optional: true`):
    ```
    ## Extension Hooks

    **Optional Hook**: {extension}
    Command: `/{command}`
    Description: {description}

    Prompt: {prompt}
    To execute: `/{command}`
    ```
  - **Mandatory hook** (`optional: false`):
    ```
    ## Extension Hooks

    **Automatic Hook**: {extension}
    Executing: `/{command}`
    EXECUTE_COMMAND: {command}
    ```
- If no hooks are registered or `.specify/extensions.yml` does not exist, skip silently
