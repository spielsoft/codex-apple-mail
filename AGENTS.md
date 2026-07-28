# codex-apple-mail Agent Guide

This repository is a standalone, generic Codex plugin for background Apple
Mail operations.

## Start here

1. Read [docs/SAFETY.md](docs/SAFETY.md) before accessing Mail.
2. Read [docs/APPLE_MAIL_TOOLING.md](docs/APPLE_MAIL_TOOLING.md) when using the
   command-line tool.
3. Read [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) before implementation.
4. Read [docs/OAUTH.md](docs/OAUTH.md) only for Gmail authorization work.
5. Read [docs/PERFORMANCE_STRATEGY.md](docs/PERFORMANCE_STRATEGY.md) before
   changing batching or identity resolution.
6. Read [docs/RESEARCH.md](docs/RESEARCH.md) when revisiting interface choices.

## Repository rules

- Keep all code and documentation generic. Do not add user accounts, campaign
  mailbox names, classification rules, filing policy, credentials, plans,
  audits, or live mailbox state.
- The installable plugin root is this repository. Keep
  `.codex-plugin/plugin.json` and `skills/apple-mail/` valid.
- Use `scripts/apple-mail` only as a project-development wrapper; the skill's
  bundled script is the implementation.
- Every Mail mutation must remain plan-based, allowlisted, bounded, verified,
  and audited.
- Never use Computer Control or Mail's private database.
- Keep generated runtime data under gitignored `local-artifacts/`.

## Documentation rule

Use progressive disclosure. Keep this file stable and procedural, put safety
limits only in `docs/SAFETY.md`, and link to canonical documents instead of
copying them.
