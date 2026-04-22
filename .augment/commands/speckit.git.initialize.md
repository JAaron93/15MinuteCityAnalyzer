---
description: Initialize a Git repository with an initial commit
---


<!-- Extension: git -->
<!-- Config: .specify/extensions/git/ -->
# Initialize Git Repository

Initialize a Git repository in the current project directory if one does not already exist.

## Execution

Run the appropriate script from the project root:

- **Bash**: `.specify/extensions/git/scripts/bash/initialize-repo.sh`
- **PowerShell**: `.specify/extensions/git/scripts/powershell/initialize-repo.ps1`

If the extension scripts are not found, fall back to a safe initialization that creates an empty initial commit (to avoid inadvertently committing sensitive files, leaving staging to the user or extensions):
- **Bash**: `git init && git commit --allow-empty -m "Initial commit from Specify template"`
- **PowerShell**: `git init; if ($LASTEXITCODE -eq 0) { git commit --allow-empty -m "Initial commit from Specify template" }`

*(Note: The fallback commands are minimal; the caller must verify Git availability and ensure they are not already in a repository before executing them.)*

The **extension scripts** (`initialize-repo.sh` / `initialize-repo.ps1`) handle all checks internally:
- Skips if Git is not available
- Skips if already inside a Git repository
- Runs `git init` and an empty `git commit` to safely establish the initial branch
- Requires extension scripts to supply a `.gitignore` and handle secure staging if file tracking is needed

## Customization

Replace the script to add project-specific Git initialization steps:
- Custom `.gitignore` templates
- Default branch naming (`git config init.defaultBranch`)
- Git LFS setup
- Git hooks installation
- Commit signing configuration
- Git Flow initialization

## Output

On success:
- `✓ Git repository initialized`

## Graceful Degradation

If Git is not installed:
- Warn the user
- Skip repository initialization
- The project continues to function without Git (specs can still be created under `specs/`)

If Git is installed but `git init`, `git add .`, or `git commit` fails:
- Surface the error to the user
- Stop this command rather than continuing with a partially initialized repository