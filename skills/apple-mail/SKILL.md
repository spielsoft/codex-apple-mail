---
name: apple-mail
description: Read and organize email in Apple's Mail app on macOS through transparent background scripts, without Computer Control. Use for mailbox discovery, bounded message listing including flag colors, body retrieval, marking messages read or unread, creating local mailboxes, moving messages between local mailboxes, or moving Gmail Inbox messages to local On My Mac mailboxes with audited Gmail label handling.
---

# Apple Mail

Use the bundled `scripts/apple-mail` command for every Mail operation. Do not
control Mail's UI or issue ad hoc AppleScript.

## Choose the workflow

- For discovery, listing including flag labels, or reading: run a bounded
  read-only command.
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
3. Retrieve a body only with both the numeric Mail ID and RFC Message-ID
   returned by the same recent listing.
4. Treat numeric IDs as short-lived locators; the tool corroborates durable
   identity before use.
5. Never change Mail without a hashed plan and explicit `--execute`.
6. Supply every destination again through exact `--allow-destination`.
7. Require an append-only audit path for execution.
8. If a result is pending synchronization, verify later; do not repeat the
   mutation or poll continuously.

The tool supplies mechanics only. Apply the user's separate filing or
retention policy in agent reasoning, not in this skill's code.
