# GitHub Publication Checklist

Use this checklist before publishing `codex-apple-mail`.

## Repository checks

From the repository root:

```sh
python3 /Users/ispielma/.codex/skills/.system/skill-creator/scripts/quick_validate.py skills/apple-mail
python3 /Users/ispielma/.codex/skills/.system/plugin-creator/scripts/validate_plugin.py .
python3 -m unittest discover -s tests -v
git diff --check
```

Confirm that the manifest name, repository directory, and public repository URL
all use `codex-apple-mail`.

## Sensitive-data checks

Credentials, tokens, message inventories, selections, plans, bodies, and audit
logs must stay outside the published tree. `local-artifacts/` is ignored for
runtime data, but a private external directory is preferred for OAuth client
JSON and tokens.

Before staging, inspect tracked paths and scan for credential-like content:

```sh
git ls-files | rg -i '(credential|client.?secret|token|\.env|\.pem|\.p12)' || true
rg -n -i --hidden -g '!/.git/**' -g '!local-artifacts/**' \
  '(AIza[0-9A-Za-z_-]{20,}|ya29\.[0-9A-Za-z._-]{20,}|BEGIN .*PRIVATE KEY|refresh_token[[:space:]]*[:=]|access_token[[:space:]]*[:=])' . || true
```

Do not publish old branches, tags, or all refs. The repository was split from
an earlier private workflow, so the publication branch must have a clean
ancestry containing only the generic plugin.

## Safe push

Create and verify a clean orphan publication branch, then push only that branch
as GitHub `main`:

```sh
git push --set-upstream origin main
```

Never use `git push --all` or push the local pre-publication backup branch.
