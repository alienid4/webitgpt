# Field Issue Intake And Masking

Use this document when reporting a webitgpt field issue back to Codex or GPT.
The goal is one complete masked report instead of many back-and-forth replies.

## Rule

Collect as much context as possible in one pass. Mask sensitive values before
sending the report outside the company-controlled environment.

## What To Mask

Always mask:

- real passwords
- API keys and tokens
- private keys
- session cookies
- real personal usernames
- real customer names
- hostnames when sending to external AI
- IP addresses when sending to external AI
- internal DNS names
- private paths that reveal user names or business names

## Masking Format

Use stable aliases so relationships remain understandable:

```text
192.168.1.221     -> IP-A
192.168.1.224     -> IP-B
SECSVR198-014T    -> HOST-A
sysinfra          -> USER-A
alienid4          -> USER-B
mongodb://x:y@... -> MONGO-URI-MASKED
wgpt_xxx          -> API-TOKEN-MASKED
```

If the same value appears multiple times, use the same alias every time.

## One Pass Issue Report

Fill as much as possible.

```text
Issue title:

Target environment:
- OS:
- OS version:
- Host role: dev / test / offline migration / production-like
- Install path:
- Port:
- Network mode: online / offline / Satellite repo / no repo

Package:
- Release tag:
- Package filename:
- Patch filename, if any:
- SHA256 checked: yes / no

Expected result:

Actual result:

Current install step:
- Step 1 prerequisites / Mongo / app install / bootstrap / systemd / health check

Important log excerpt:
<paste masked error lines and the 80 lines before the failure if possible>

Database mode:
- podman Mongo / native mongod / existing external Mongo / unknown
- Mongo URI masked:
- Is port 27017 listening: yes / no / unknown

Container/runtime:
- podman installed: yes / no / unknown
- podman version:
- Mongo container name:
- Mongo container status:

Service status:
- webitgpt systemd status:
- webitgpt-mongo systemd status:
- health endpoint:
- ready endpoint:

What has already been tried:

Constraints:
- Cannot use internet:
- Can use Satellite/RHEL repo:
- Cannot install OS packages:
- Must avoid podman:
- Must keep existing Mongo data:

Question for Codex:
```

## Good Error Excerpt

Good:

```text
Problem: package podman-X.el9_7 requires container-selinux...
file /etc/redhat-release conflicts with redhat-release...
pymongo.errors.ServerSelectionTimeoutError: localhost:27017 connection refused
```

Less useful:

```text
It failed.
```

## Internal Vs External AI

For company internal GPT approved to see internal infrastructure:

- IP and hostnames may remain unmasked if policy allows.
- Still never include passwords, tokens, cookies, private keys, or API keys.

For external/personal AI:

- Mask IP, hostname, username, system name, customer name, tokens, passwords,
  keys, internal DNS names, and sensitive paths.

## Codex Response Expectation

Codex should answer with:

- likely root cause
- confidence level
- safest next action
- commands only through GitHub docs when field execution is required
- whether the issue is a packaging bug, install environment issue, or runtime bug
- whether a patch package is needed
