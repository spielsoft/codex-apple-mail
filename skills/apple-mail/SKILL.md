---
name: apple-mail
description: Read and organize email in Apple's Mail app on macOS through transparent background scripts, without Computer Control. Use for mailbox discovery, bounded message listing including flag colors, body retrieval, marking messages read or unread, creating local mailboxes, moving messages between local mailboxes, or moving Gmail Inbox messages to local On My Mac mailboxes with audited Gmail label handling.
---

# Apple Mail

Use the bundled `scripts/apple-mail` command for every Mail operation. Do not
control Mail's UI or issue ad hoc AppleScript.

## Execution permission

Apple Mail access uses macOS Apple Events, which the default command sandbox
blocks. For `discover`, `list`, `get`, `get-batch`, `verify`, `reconcile`, `probe-copy`,
`apply --execute`, and `authorize`, make the first shell-tool call with
`sandbox_permissions: "require_escalated"` (or the surface's equivalent scoped
permission) and a concise Apple Mail justification. Do not try the command in
the sandbox first. Invocation of this skill authorizes requesting that scoped
permission immediately; it does not override the active Codex approval policy.

## Choose the workflow

- For discovery, listing including flag labels, or reading: run a bounded
  read-only command. Prefer one `get-batch` call over concurrent singleton
  `get` calls when reading two to ten messages from one mailbox. For Gmail
  Inbox and an existing OAuth token, pass `--token` and `--expected-account`
  to use the faster Gmail API backend; otherwise the command uses Mail. If
  Gmail reports that selected text is not inline, the command safely falls
  back to its bounded Mail batch; do not fetch Gmail attachment content.
- For a change: list exact messages, create a hashed plan, inspect it, dry-run
  it, then apply only when the user has authorized that scope.
- For Gmail Inbox to local: use `plan-gmail-transfer`; never substitute a Mail
  cross-store move or a source-removal command.
- For local filing: use `plan-local-move`.
- For read state or mailbox creation: use the corresponding plan command.

Read [references/safety.md](references/safety.md) before any mutation. Read
[references/commands.md](references/commands.md) for exact command syntax and
selection schema.

## Core rules

1. Keep message-derived artifacts private and outside source control.
2. Limit metadata listings to at most 250 messages.
3. Retrieve bodies only from identities returned by the same recent listing.
   `get-batch` corroborates all six selection fields before reading any body.
   Its OAuth backend completes the entire metadata barrier before fetching
   any selected body.
4. Treat numeric IDs as short-lived locators; the tool corroborates durable
   identity before use.
5. Use `probe-copy` to exercise a Gmail transfer's copy preflight and selector
   path without calling Mail's `duplicate` command.
6. Never change Mail without a hashed plan and explicit `--execute`.
7. Supply every destination again through exact `--allow-destination`.
8. Require an append-only audit path for execution.
9. If a Gmail transfer is pending synchronization, run one later `reconcile`
   with the same plan and audit; do not repeat the mutation or poll
   continuously. Continue only after reconciliation reports `complete`.

The tool supplies mechanics only. Apply the user's separate filing or
retention policy in agent reasoning, not in this skill's code.
