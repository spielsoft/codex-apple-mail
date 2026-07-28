# Safety

Allowed operations are bounded reads, read/unread changes, local mailbox
creation, local-to-local moves, and Gmail Inbox-to-local transfers.

Never:

- permanently remove messages or mailboxes;
- invoke standalone source removal, Trash, Junk emptying, or a deletion
  destination;
- send, draft, reply, forward, or redirect;
- change account settings, rules, credentials, or server configuration;
- use Computer Control, Accessibility UI scripting, mouse, or keyboard input;
- read or write Mail's private database or message-store files; or
- retrieve attachment contents.

Every mutation must use a canonical hashed plan, exact source identity,
caller-supplied destination allowlist, `--execute`, bounded batch, batch
verification, and append-only audit.

For Gmail transfers, the only server mutation is adding or removing the
`INBOX` label. The local-copy barrier must pass before removing `INBOX`.
Adding `INBOX` is the only rollback. A message remaining in All Mail is
expected.

Protected local destination leaf names include Trash, Deleted Messages, Junk,
Outbox, Drafts, Sent, and Send Later.
