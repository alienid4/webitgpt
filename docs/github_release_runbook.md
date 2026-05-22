# webitgpt GitHub / Release Runbook

## Repository

```text
https://github.com/alienid4/webitgpt
```

This repository should stay private unless the owner explicitly changes the policy.

## Current Rule

- Version format: `v1.0.X.Y`
- Each segment after `v1.0` must be 0 to 99.
- Do not use `v2.0` under the current policy.
- First delivery uses a full offline release package.
- Later updates may use compressed patch packages.

## Before Push

Always check:

```powershell
cd F:\ClaudeHome\webitgpt
git status --short
git remote -v
```

Do not commit or push:

- `data/`
- `logs/`
- `backup/`
- `venv/`
- `.git/`
- Mongo dump
- secrets, passwords, tokens, private keys
- company production logs

## First GitHub Push

Use this after reviewing the changed file list:

```powershell
cd F:\ClaudeHome\webitgpt
git add .
git status --short
git commit -m "chore: initial webitgpt offline install baseline"
git push -u origin HEAD
```

If there are files that should not be committed, remove them from staging before commit.

## First Full Offline Release

Build the full offline package:

```powershell
cd F:\ClaudeHome\webitgpt
powershell -ExecutionPolicy Bypass -File .\scripts\prepare_offline_bundle.ps1
```

Verify the package:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\verify_offline_bundle.ps1 -Archive .\dist\<bundle>.tar.gz
```

Create a GitHub Release:

```powershell
gh release create v1.0.2.96 .\dist\<bundle>.tar.gz `
  --repo alienid4/webitgpt `
  --title "webitgpt v1.0.2.96 offline install" `
  --notes-file .\docs\release_notes\v1.0.2.96.md
```

If the release note file does not exist yet, create it first.

## Test Machine Install Command

On the target host:

```bash
cd /tmp
tar -xzf webitgpt_offline_*.tar.gz
cd webitgpt_offline_*
sudo bash INSTALL.sh
curl http://localhost:8002/health
systemctl status webitgpt --no-pager
```

## Later Patch Flow

Later updates should create a compressed patch package with:

- `install_patch_<version>.sh`
- release note
- changed files
- verification notes
- rollback notes if available

The release page must include copyable commands for:

- download
- unpack
- install patch
- health check
- rollback or troubleshooting
