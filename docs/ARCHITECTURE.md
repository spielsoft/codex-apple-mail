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
- Gmail Inbox- and Spam-to-local transfers;
- verification, OAuth, rollback, and append-only audit records.

The plugin contains no filing policy or user-specific state.

## Interfaces

Python standard-library code validates plans and orchestrates narrow
AppleScripts. AppleScript is the public Apple Mail interface. A constrained
Gmail API client provides optional bounded body reads for recent selections
from any account mailbox and handles lookup plus adding or removing only
`INBOX` and `SPAM` for explicit Gmail transfers.

The tool never reads or writes Mail's private database.

## Identity and batching

Every message plan carries:

- indexed, short-lived Mail numeric `mail_id`;
- durable RFC Message-ID; and
- subject, sender, received date, and read-state corroborators.

A batch binds by numeric ID and validates all corroborators. Gmail transfers
then submit ordered internal chunks of at most ten numeric-ID-filtered Mail
object specifiers to bulk `duplicate`; Gmail label mutation waits for one
bounded whole-plan barrier after every chunk has returned. Local moves retain
their single bounded bulk `move`. A materialized AppleScript list is not a Mail
object specifier and must not be used as the command's direct parameter.
Capture the candidate count before padding a selector list: AppleScript list
concatenation can retain shared mutable backing. The implementation never scans
a large source once per RFC Message-ID.

## Plan actions

- `gmail_inbox_to_local`
- `gmail_spam_to_local`
- `move_local`
- `set_read`
- `create_local_mailbox`

Plans are canonical-JSON hashed and written exclusively. Applying a plan
requires `--execute`; destination-bearing plans also require an exact
`--allow-destination` matching the hashed plan.

## Gmail transfer

AppleScript cross-store `move` does not reliably remove Gmail source labels.
The copy script resolves one bounded numeric-ID selector, validates every
source from that result, and bulk-copies missing local messages. Plans above
ten messages submit every independently validated ten-message chunk before a
single bounded whole-plan durability barrier. The barrier re-resolves every
source and requires exactly one read-preserved local destination copy for every
planned identity. A slow-settling chunk therefore cannot prevent later safe
copy submissions, while Gmail mutation remains impossible until the complete
plan is durable. The transaction then removes the action-specific Gmail source
label. A Spam transaction also removes `INBOX` if Gmail adds it while removing
`SPAM`. It requests one Mail synchronization and returns
`pending_mail_sync` rather than
immediately querying the cache that it just asked to synchronize; one later
bounded, audited reconciliation gates the next sequential block.
Reconciliation owns the terminal state transition: it appends `complete` only
for exact local copies with preserved read state and absent sources, retains
`pending_mail_sync` while any exact source remains during cache convergence,
and records `mutation_state_unknown` for invalid, unreadable, ambiguous, or
numeric-ID-reuse evidence. `DESTINATION_COUNT=1` already represents a full
identity match because the verifier rejects Message-ID collisions and counts
only messages whose complete corroborating identity matches. Partial Gmail
mutation rolls back by authoritatively reading every planned Gmail ID and
restoring the action-specific pre-state. Inbox rollback restores `INBOX`; Spam
rollback restores `SPAM` and ensures `INBOX` is absent. It then reads the
complete batch again. An unreadable final label state is audited as
`mutation_state_unknown`, never as a confirmed rollback. Gmail lookup and
label requests accept a fifty-message transaction but use at most ten
concurrent workers; each label change still requires its own confirmed
outcome. Mail Apple Events remain serial and transfer selectors are chunked at
ten messages.

Modify responses must bind the immutable Gmail ID. A complete returned label
snapshot is authoritative; when Gmail omits `labelIds`, a targeted metadata
read fills that missing snapshot before the transaction can continue. Those
idempotent metadata reads use a short bounded retry schedule for transient
request failures; label mutations are never retried implicitly. A bound
metadata response with no `labelIds` represents an empty label set, consistent
with Gmail's omission of empty repeated JSON fields.
Complete snapshots identify Spam-created `INBOX` labels, gate cleanup, and
confirm the final state. Explicit resume is available only for the same plan
and audit after a started-and-failed lifecycle. It verifies every destination
copy through Mail, skips copying, and removes the source label only from the
Gmail subset where it remains present. Reconciliation is lifecycle-gated: an
apply failure must pass through Gmail-aware resume before Mail-only
reconciliation can classify the transaction.

After source-label removal, Mail can raise error `-1719` while an indexed source
filter is disappearing instead of returning an empty collection. The indexed
lookup boundary normalizes only that error to zero matches; other Mail errors
still propagate. Pre-mutation callers continue to reject zero matches.

Display lag returns `pending_mail_sync`; the tool neither polls continuously
nor performs a predictably premature immediate cache check. The reconciliation
command is read-only, does not require OAuth, and emits only aggregate state
plus generic reason codes to its append-only audit.

Read access deliberately remains broader than mutation. Apple Mail supplies
the exact account mailbox and recent numeric-ID selection. Gmail RFC
Message-ID resolution includes Spam and Trash, so OAuth body retrieval can
corroborate messages from Junk, Important, Sent, custom-label, and other
mailboxes. No arbitrary mailbox name, label, or search filter is translated
into a Gmail mutation.

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
