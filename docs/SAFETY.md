# Safety and Operational Limits

**Read when:** writing or running anything that accesses Apple Mail.

This document is authoritative.

## Allowed

- Read message metadata and explicitly selected, bounded message content.
- Mark messages read or unread.
- Move messages between non-protected mailboxes.
- Create local mailboxes.
- For Gmail-backed Inbox transfers, copy locally and remove only `INBOX`.
- For explicitly planned Gmail Spam/Junk transfers, copy locally, remove
  `SPAM`, and remove `INBOX` only if Gmail adds it during the not-spam
  transition.

The Spam/Junk action remains a bounded, identity-selected transfer. It does
not authorize a mailbox-wide empty command or permanent deletion.

## Prohibited

- Permanent deletion, standalone message deletion, mailbox deletion, Trash or
  Junk emptying, or moves to a deletion destination.
- Sending, drafting, replying, forwarding, or redirecting.
- Changes to Mail accounts, settings, rules, credentials, or server
  configuration.
- Computer Control, Accessibility UI scripting, mouse, or keyboard control.
- Reading or writing Mail's private database or message-store files.

## Script-first rule

Every Mail access or change uses the version-controlled `scripts/apple-mail`
entry point. Never issue an ad hoc write command. Add and test a generic
operation before using it.

Filing judgment belongs to the consuming agent or application. It must not be
embedded in this generic plugin.

## Mutation invariants

Every mutation must:

1. consume a canonical, hashed plan created before execution;
2. require `--execute`;
3. require a caller-supplied exact allowlist for any destination;
4. use fully qualified account/mailbox or `On My Mac/...` sources;
5. bind by indexed numeric Mail ID and corroborate RFC Message-ID, subject,
   sender, date, and read state before changing anything;
6. reject stale, missing, duplicate, or ambiguous identities;
7. operate on one bounded batch, at most 250 messages;
8. use one bulk Mail command per bounded internal chunk, not a process per
   message;
9. verify the local copy barrier before Gmail mutation, request one Mail
   synchronization afterward, and report the cache state as pending until one
   later bounded reconciliation rather than querying or polling immediately;
   and
10. append a start and outcome event to a private audit log; a later
    reconciliation appends the terminal Gmail transfer outcome.

Local move source and destination must differ. Protected destination leaf
names include Trash, Deleted Messages, Junk, Outbox, Drafts, Sent, and Send
Later.

## Gmail transfer

Gmail labels are not folders. A message may remain in `[Gmail]/All Mail` after
leaving `INBOX` or `SPAM`; that is expected.

AppleScript does not reliably reproduce Mail's GUI cross-store move. The
approved generic transaction is:

1. bulk-copy the validated messages to the exact local destination;
2. verify one copy of every message with preserved read state;
3. resolve the same messages through Gmail and require the action-specific
   source label (`INBOX` or `SPAM`) on every message;
4. remove only that source label; after `SPAM` removal, also remove `INBOX` if
   Gmail adds it while marking the message not spam;
5. if any Gmail mutation fails or returns an invalid response, read every
   planned Gmail ID authoritatively and restore the complete pre-state:
   `INBOX` for an Inbox plan, or `SPAM` present plus `INBOX` absent for a Spam
   plan;
6. request one Mail synchronization and return `pending_mail_sync`; perform
   one later bounded, audited reconciliation before beginning another
   sequential block.

Rollback is confirmed by a final bounded authoritative-read pass over every
planned Gmail ID. Each idempotent metadata read has a short retry schedule for
transient request failures; mutation requests are never retried implicitly. If
those reads cannot establish the final label state, the audit outcome is
`mutation_state_unknown`; the tool never reports a successful rollback from
request responses alone.

The Gmail request layer allows only profile lookup, message search, bounded
metadata/full-message reads, and a single-message modification whose sole
changed label is `INBOX` or `SPAM`. Gmail transfer and batch-read selections
are capped at 50 messages, with at most 10 concurrent network requests and at
most 10 messages in each Mail transfer selector. It rejects every other label,
server-side batch mutation, unsafe methods, and unsafe endpoints.

The Gmail API response is authoritative server confirmation. If Mail still
shows a corroborated source message after synchronization, the later
`reconcile` continues to report the transfer as pending. If a numeric ID
resolves to different metadata, fail closed.

Use `reconcile`, not a repeated mutation, to close a pending Gmail transfer.
It is read-only and requires no OAuth. It records `complete` only when every
planned destination copy is exact and read-preserved and every source is
absent. It retains `pending_mail_sync` while all source rows are either exact
or absent and at least one exact source remains during cache convergence.
Invalid, unreadable, ambiguous, or numeric-ID-reuse evidence is recorded as
`mutation_state_unknown`. `DESTINATION_COUNT=1` already represents full
identity corroboration: the verifier rejects Message-ID collisions and counts
only complete identity matches.

If execution instead ends in `operation_failed` or
`mutation_state_unknown` after local copies exist, normal reapplication is
prohibited. Explicit resume requires the same immutable plan and audit, a
prior matching started-and-failed lifecycle, and one exact read-preserved
destination copy for every planned message. It changes only source labels
that remain present and treats an already-absent source label as completed.
Reconciliation refuses a latest `operation_failed` lifecycle because Mail's
cache is not authoritative for recovery from a failed Gmail mutation.

## Inventory and content

- Begin with `list`, which reads metadata only.
- Use limits no larger than 250.
- Use account-qualified mailboxes, not Mail's global unified Inbox.
- Any exact account mailbox returned by discovery may be read, including
  Junk/Spam, Important, Sent, Trash, and custom Gmail-label mailboxes. Reading
  one does not authorize label mutation.
- `get` requires both numeric and RFC IDs and bounds body output to 100,000
  characters.
- OAuth-backed `get-batch` must validate all selected metadata and read states
  before issuing any full-message body request.
- Do not retrieve attachment contents.

## OAuth and sensitive artifacts

- Require exact authenticated-profile matching before Gmail mutation.
- Request only `gmail.modify`.
- Store credentials and tokens only in gitignored `local-artifacts/`; tokens
  must use mode `0600`.
- Never print credential or token contents.
- Stop if Workspace policy blocks the client.
- Keep inventories, bodies, selections, plans, and audits out of Git unless
  the user explicitly requests otherwise.
