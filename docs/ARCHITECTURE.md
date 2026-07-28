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
Gmail API client provides optional bounded Inbox body reads and handles lookup
plus adding or removing `INBOX` for Gmail transfers.

The tool never reads or writes Mail's private database.

## Identity and batching

Every message plan carries:

- indexed, short-lived Mail numeric `mail_id`;
- durable RFC Message-ID; and
- subject, sender, received date, and read-state corroborators.

A batch binds by numeric ID, validates all corroborators, then submits one
numeric-ID-filtered Mail object specifier to the bulk `duplicate` or `move`
command. A materialized AppleScript list is not a Mail object specifier and
must not be used as the command's direct parameter. Capture the candidate
count before padding a selector list: AppleScript list concatenation can retain
shared mutable backing. The implementation never scans a large source once per
RFC Message-ID.

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
The copy script resolves one bounded numeric-ID selector, validates every
source from that result, bulk-copies missing local messages, and verifies the
complete destination. The transaction then removes only Gmail `INBOX` and
requests one Mail synchronization. It returns `pending_mail_sync` rather than
immediately querying the cache that it just asked to synchronize; one later
bounded, audited reconciliation gates the next sequential block.
Reconciliation owns the terminal state transition: it appends `complete` only
for exact local copies with preserved read state and absent sources, retains
`pending_mail_sync` while any exact source remains during cache convergence,
and records `mutation_state_unknown` for invalid, unreadable, ambiguous, or
numeric-ID-reuse evidence. `DESTINATION_COUNT=1` already represents a full
identity match because the verifier rejects Message-ID collisions and counts
only messages whose complete corroborating identity matches. Partial Gmail
mutation rolls back by authoritatively reading every planned Gmail ID, adding
`INBOX` where removal is observed or the initial state cannot be read, and
reading the complete batch again. An unreadable final label state is audited
as `mutation_state_unknown`, never as a confirmed rollback. Gmail lookup and
label requests may run concurrently within the fixed ten-message bound, but
each label change still requires its own confirmed outcome. Mail Apple Events
remain serial.

After `INBOX` removal, Mail can raise error `-1719` while an indexed source
filter is disappearing instead of returning an empty collection. The indexed
lookup boundary normalizes only that error to zero matches; other Mail errors
still propagate. Pre-mutation callers continue to reject zero matches.

Display lag returns `pending_mail_sync`; the tool neither polls continuously
nor performs a predictably premature immediate cache check. The reconciliation
command is read-only, does not require OAuth, and emits only aggregate state
plus generic reason codes to its append-only audit.

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
