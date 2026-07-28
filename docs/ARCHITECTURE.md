# Architecture

**Read when:** implementing or reviewing the plugin.

## Boundary

The `apple-mail` skill owns reusable email mechanics:

- mailbox discovery and bounded listing;
- indexed message retrieval;
- immutable plans and exact destination allowlists;
- read/unread changes;
- local mailbox creation;
- local-to-local bulk moves;
- Gmail Inbox-to-local transfers;
- verification, OAuth, rollback, and append-only audit records.

The plugin contains no filing policy or user-specific state.

## Interfaces

Python standard-library code validates plans and orchestrates narrow
AppleScripts. AppleScript is the public Apple Mail interface. A constrained
Gmail API client is used only for lookup and adding or removing `INBOX`.

The tool never reads or writes Mail's private database.

## Identity and batching

Every message plan carries:

- indexed, short-lived Mail numeric `mail_id`;
- durable RFC Message-ID; and
- subject, sender, received date, and read-state corroborators.

A batch binds by numeric ID, validates all corroborators, then submits one
numeric-ID-filtered Mail object specifier to the bulk `duplicate` or `move`
command. A materialized AppleScript list is not a Mail object specifier and
must not be used as the command's direct parameter. The implementation never
scans a large source once per RFC Message-ID.

## Plan actions

- `gmail_inbox_to_local`
- `move_local`
- `set_read`
- `create_local_mailbox`

Plans are canonical-JSON hashed and written exclusively. Applying a plan
requires `--execute`; destination-bearing plans also require an exact
`--allow-destination` matching the hashed plan.

## Gmail transfer

AppleScript cross-store `move` does not reliably remove Gmail's `INBOX` label.
The transaction validates sources, bulk-copies missing local messages, verifies
the complete destination, removes only Gmail `INBOX`, requests one Mail
synchronization, and performs one final indexed check. Partial Gmail mutation
rolls back by adding `INBOX`.

Display lag returns `pending_mail_sync`; the tool does not poll continuously.

## Layout

```text
.codex-plugin/plugin.json
skills/apple-mail/
  SKILL.md
  agents/
  references/
  scripts/
    apple-mail
    apple_mail/
      applescript/
scripts/apple-mail       # development convenience wrapper
docs/
tests/
```
