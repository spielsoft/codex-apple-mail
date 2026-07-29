# Safety

Allowed operations are bounded reads, read/unread changes, local mailbox
creation, local-to-local moves, and explicit Gmail Inbox- or Spam-to-local
transfers.

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

For Gmail transfers, the only mutable source labels are `INBOX` and `SPAM`.
All independently validated local-copy chunks are submitted serially, then one
bounded whole-plan barrier must confirm every exact, read-preserved local copy
before either source label is removed. Inbox rollback restores `INBOX`. Spam
rollback restores `SPAM` and ensures `INBOX` is absent. A successful Spam
transfer also removes `INBOX` if Gmail adds it while the message is marked not
spam. A message remaining in All Mail is expected.

Reading an exact Sent, Important, custom-label, Trash, or other account
mailbox does not authorize any Gmail label mutation.

Protected local destination leaf names include Trash, Deleted Messages, Junk,
Outbox, Drafts, Sent, and Send Later.
