---
name: apple-mail
description: Read and organize email in Apple's Mail app on macOS through transparent background scripts, without Computer Control. Use for mailbox discovery, bounded message listing including flag colors, body retrieval from account mailboxes including Gmail Junk, Important, Sent, and custom labels, marking messages read or unread, creating local mailboxes, moving messages between local mailboxes, or moving Gmail Inbox or Spam messages to local On My Mac mailboxes with audited Gmail label handling.
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
  read-only command against the exact account mailbox returned by `discover`.
  This includes Gmail Junk/Spam, Important, Sent, and custom-label mailboxes.
  Prefer one `get-batch` call over concurrent singleton `get` calls when
  reading two to fifty messages from one mailbox. For Gmail and an existing
  OAuth token, pass `--token` and `--expected-account` to use the faster Gmail
  API backend; otherwise the command uses Mail. If Gmail reports that selected
  text is not inline, the command safely falls back to its bounded Mail batch;
  do not fetch Gmail attachment content.
- For a change: list exact messages, create a hashed plan, inspect it, dry-run
  it, then apply only when the user has authorized that scope.
- For Gmail Inbox to local: use `plan-gmail-transfer`; never substitute a Mail
  cross-store move or a source-removal command.
- For Gmail Junk/Spam to local: use `plan-gmail-junk-transfer` with the exact
  discovered Mail mailbox name. It removes only Gmail `SPAM` after the local
  copy barrier, and also removes `INBOX` if Gmail adds it while marking the
  message not spam.
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
   Gmail body-read and transfer selections are capped at 50 messages; Gmail
   network concurrency and Mail transfer selectors remain capped at 10.
4. Treat mailbox access as read-only by default. `INBOX` and `SPAM` are the
   only Gmail source labels the mutation layer can remove; Sent, Important,
   custom labels, Trash, and arbitrary filters are never implicit mutations.
5. Treat numeric IDs as short-lived locators; the tool corroborates durable
   identity before use.
6. Use `probe-copy` to exercise a Gmail transfer's copy preflight and selector
   path without calling Mail's `duplicate` command.
7. Never change Mail without a hashed plan and explicit `--execute`.
8. Supply every destination again through exact `--allow-destination`.
9. Require an append-only audit path for execution.
10. Gmail transfer copy chunks are submitted serially, then one bounded
    whole-plan barrier must confirm every exact, read-preserved local copy
    before any Gmail label can change.
11. If a Gmail transfer is pending synchronization, run one later `reconcile`
   with the same plan and audit; do not repeat the mutation or poll
   continuously. Continue only after reconciliation reports `complete`.
12. If execution records `operation_failed` or `mutation_state_unknown` after
    the local-copy barrier, do not reapply normally. Use explicit `--resume`
    with the same plan and audit; it proceeds only after every destination
    copy is exact and the audit proves a prior started-and-failed lifecycle.

The tool supplies mechanics only. Apply the user's separate filing or
retention policy in agent reasoning, not in this skill's code.
