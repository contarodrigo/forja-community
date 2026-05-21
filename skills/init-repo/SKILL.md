---
name: init-repo
description: Use when initializing a new Git repository in a directory that will be backed up to GitHub. Sets up git, SSH, .gitignore, initial commit and push.
version: 1.0.0
author: forja
license: MIT
metadata:
  hermes:
    tags: [git, github, ssh, setup, repo-init]
    related_skills: [github-auth, github-repo-management]
---

# Initialize Git Repository with GitHub

## Overview

Initializes a local directory as a Git repository, configures SSH authentication for GitHub, creates a sensible `.gitignore`, performs the initial commit, and pushes to a remote repository. Designed for directories that live outside the hermes-agent repo (e.g. `~/.hermes/`) and serve as personal backups.

## When to Use

- User says "initialize this directory as a git repo" or "set up git backup for this folder"
- Starting version control for a new project that will live on GitHub
- Setting up a new Hermes home directory with version control

## Prerequisites

1. GitHub account with a repository already created (empty is fine — this script pushes the initial content)
2. User must provide:
   - **Commit username** (e.g. `meu agente`)
   - **Commit email** (e.g. `mmeu-agente@empresa.local`)
   - **GitHub repository URL** (e.g. `https://github.com/username/my-repo.git`)

## Step-by-Step Process

### Step 1 — Ask for User Details

Before starting, collect:

```
- Commit username (git config user.name)
- Commit email (git config user.email)
- GitHub repository URL
```

If the repo does not exist on GitHub yet, instruct the user to create it first (empty repo).

### Step 2 — Initialize Git and Configure Remote

```bash
cd <target_directory>
git init
git remote add origin <github_url>
```

Replace `https://` URLs with SSH format:
```bash
git remote set-url origin git@github.com:<owner>/<repo>.git
```

### Step 3 — Configure Commit Identity

```bash
git config user.name "<username>"
git config user.email "<email>"
```

### Step 4 — Create .gitignore

Create a `.gitignore` tailored to the directory content. Example for a Hermes home:

```
# Environment and auth
.env
.env.*
!.env.example
auth.json
auth.lock
*.db
*.db-shm
*.db-wal

# Hermes state and sessions
state.db
kanban.db
sessions/
gateway.pid
gateway.lock
gateway_state.json
channel_directory.json
models_dev_cache.json

# Logs
logs/
*.log

# Caches
audio_cache/
image_cache/
memories/
cron/

# Checkpoints (Hermes agent state)
checkpoints/

# Node/bundled TUI deps
node/

# Backups
*.bak
*.backup
*.swp
*.swo
*~

# OS
.DS_Store
Thumbs.db
```

General rule: always exclude secrets (`.env`, `auth.json`), databases, logs, and session state.

### Step 5 — Generate SSH Key (if not present)

Check for existing keys:
```bash
ls ~/.ssh/id_ed25519  # or id_rsa
```

If none exists, generate one:
```bash
ssh-keygen -t ed25519 -C "<email>" -f ~/.ssh/id_ed25519 -N ""
```

Add GitHub's host key:
```bash
ssh-keyscan github.com >> ~/.ssh/known_hosts 2>/dev/null
```

### Step 6 — Display Public Key for User to Add to GitHub

```bash
cat ~/.ssh/id_ed25519.pub
```

Instruct the user to add this key in GitHub: **Settings → SSH and GPG keys → New SSH key**.

### Step 7 — Test SSH Connection

```bash
ssh -T git@github.com
```

Expected output:
```
Hi <username>! You've successfully authenticated, but GitHub does not provide shell access.
```

### Step 8 — Initial Commit

```bash
git add -A
git status --short  # review what will be committed
git commit -m "Initial commit: <description of content>"
```

### Step 9 — Push to GitHub

```bash
git push -u origin master  # or main, depending on the repo
```

If the user needs to force-push (e.g. after amending the author), warn them before proceeding.

## SSH Key Creation Flow

```
┌─────────────────────────────────────────────┐
│  Generate SSH key (ed25519)                  │
│  ssh-keygen -t ed25519 -C "email" \          │
│    -f ~/.ssh/id_ed25519 -N ""               │
└────────────────────┬────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────┐
│  Display public key                          │
│  cat ~/.ssh/id_ed25519.pub                  │
└────────────────────┬────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────┐
│  User adds key to GitHub                     │
│  Settings → SSH and GPG keys → New SSH key  │
└────────────────────┬────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────┐
│  Test connection                            │
│  ssh -T git@github.com                       │
└─────────────────────────────────────────────┘
```

## Common Pitfalls

1. **Repository URL uses HTTPS instead of SSH.** Git operations will fail without authentication. Always convert to SSH format: `git@github.com:owner/repo.git`.

2. **No SSH key exists and GitHub auth fails.** Always check `ls ~/.ssh/` before attempting push. Generate a key if missing.

3. **GitHub host key not in known_hosts.** First SSH connection to GitHub fails with "Host key verification failed." Fix with `ssh-keyscan github.com >> ~/.ssh/known_hosts`.

4. **Commit author is wrong.** If the wrong name appears, amend the commit:
   ```bash
   git commit --amend --author="Name <email>" --no-edit
   ```
   Then force-push: `git push --force`.

5. **Pushing to a repo that already has commits (e.g. a README).** The push will be rejected. User must either force-push (warning: destroys remote history) or pull/merge first.

6. **Sensitive files committed before .gitignore was created.** Remove from git tracking:
   ```bash
   git rm --cached <file>
   git rm -r --cached <directory>
   ```
   Then recommit.

## Verification Checklist

- [ ] Git remote is set to SSH URL (`git@github.com:...`)
- [ ] Commit identity configured (`git config user.name` / `user.email`)
- [ ] `.gitignore` created and excludes secrets + state files
- [ ] SSH key generated or confirmed present
- [ ] User added public key to GitHub
- [ ] `ssh -T git@github.com` returns successful authentication message
- [ ] Initial commit created with correct author
- [ ] Push succeeded with `-u origin master` (first push sets upstream)
- [ ] Repo visible at GitHub URL with correct content
