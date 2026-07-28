# Safety and Operational Limits

**Read when:** writing or running anything that accesses Apple Mail.

This document is authoritative.

## Allowed

- Read message metadata and explicitly selected, bounded message content.
- Mark messages read or unread.
- Move messages between non-protected mailboxes.
- Create local mailboxes.
- For Gmail-backed Inbox transfers, copy locally and remove only `INBOX`.

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
8. use one bulk Mail command for a batch, not a process per message;
9. verify the local copy barrier before Gmail mutation, request one Mail
   synchronization afterward, and report the cache state as pending until one
   later bounded verification rather than querying or polling immediately; and
10. append a start and outcome event to a private audit log.

Local move source and destination must differ. Protected destination leaf
names include Trash, Deleted Messages, Junk, Outbox, Drafts, Sent, and Send
Later.

## Gmail transfer

Gmail labels are not folders. A message may remain in `[Gmail]/All Mail` after
leaving `INBOX`; that is expected.

AppleScript does not reliably reproduce Mail's GUI cross-store move. The
approved generic transaction is:

1. bulk-copy the validated messages to the exact local destination;
2. verify one copy of every message with preserved read state;
3. resolve the same messages through Gmail;
4. remove only `INBOX`;
5. add `INBOX` back if a later Gmail mutation in the batch fails;
6. request one Mail synchronization and return `pending_mail_sync`; perform
   one later bounded verification before beginning another sequential block.

The Gmail request layer allows only profile lookup, message search, bounded
metadata/full-message reads, and a single-message modification whose sole
changed label is `INBOX`. Gmail requests may run concurrently only within the
ten-message transfer/read limit. It rejects other labels, server-side batch
mutation, unsafe methods, and unsafe endpoints.

The Gmail API response is authoritative server confirmation. If Mail still
shows a corroborated source message after synchronization, the later `verify`
continues to report it. If a numeric ID resolves to different metadata, fail
closed.

## Inventory and content

- Begin with `list`, which reads metadata only.
- Use limits no larger than 250.
- Use account-qualified mailboxes, not Mail's global unified Inbox.
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
