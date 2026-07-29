# Command Reference

Set `APPLE_MAIL` to the absolute path of this skill's `scripts/apple-mail`
entry point.

Commands that access Mail or Gmail require macOS Apple Events or network
access. Run the first `discover`, `list`, `get`, `get-batch`, `verify`,
`reconcile`, `probe-copy`, `apply --execute`, or `authorize` attempt with
scoped sandbox escalation. Do not spend a failed attempt discovering this
requirement. Planning, plan inspection, and dry runs remain local and can run
in the normal workspace sandbox.

## Read

```sh
"$APPLE_MAIL" discover

"$APPLE_MAIL" list \
  --account "person@example.com" --mailbox INBOX \
  --start 1 --limit 50

"$APPLE_MAIL" list \
  --account "person@example.com" --mailbox "Junk" \
  --start 1 --limit 50

"$APPLE_MAIL" list \
  --account "person@example.com" --mailbox "Custom Label" \
  --start 1 --limit 50

"$APPLE_MAIL" list \
  --local "On My Mac/Archive" \
  --start 1 --limit 50

"$APPLE_MAIL" get \
  --account "person@example.com" --mailbox INBOX \
  --mail-id 123 --message-id "stable@example.com" \
  --body-limit 50000

"$APPLE_MAIL" get-batch \
  --account "person@example.com" --mailbox INBOX \
  --selection selection.json \
  --body-limit 50000

"$APPLE_MAIL" get-batch \
  --account "person@example.com" --mailbox "Junk" \
  --selection selection.json \
  --body-limit 50000 \
  --token /private/path/gmail-token.json \
  --expected-account "person@example.com"
```

`get` returns one `MESSAGE` record. Its `BODY` field preserves embedded line
breaks and Unicode line or paragraph separators without creating extra
records. `get-batch` returns one ordered `MESSAGE` record per selected identity,
accepts at most fifty messages, and validates every identity before retrieving
any body. Without OAuth arguments it uses one serial AppleScript process. With
both OAuth arguments it verifies the authenticated profile, resolves all
selected Gmail identities with at most ten concurrent requests, completes the
metadata/read-state barrier, and then retrieves the bodies with the same
concurrency cap. It emits the same record schema and does not change Gmail or
Mail. When Gmail exposes selected text only through an attachment identifier,
the tool does not retrieve attachment content. It falls back to one bounded
Mail batch after the completed Gmail identity barrier. Authentication, network,
and identity failures do not trigger this fallback. Do not parallelize
singleton `get` calls against Mail.

`list`, `get`, and `get-batch` accept any exact account mailbox returned by
`discover`, including Junk/Spam, Important, Sent, and custom Gmail-label
mailboxes. OAuth RFC Message-ID lookup includes Spam and Trash so a recent Mail
selection can be corroborated there. These commands do not change labels.
Arbitrary Gmail search syntax is not exposed as a mutation or as a replacement
for the recent Mail selection and numeric-ID binding.

`get-batch` retains `ATTACHMENT_COUNT` and adds
`ATTACHMENT_COUNT_SOURCE`. A source of `apple_mail` means Mail's native
attachment object count; `gmail_mime` means the count was derived from Gmail
MIME metadata and should not be assumed to be identical to Mail's object
model.

Each `MESSAGE` row from `list` includes:

- `FLAGGED`: Mail's existing Boolean flagged state;
- `FLAG_INDEX`: Mail's integer flag index; and
- `FLAG_COLOR`: a stable color name derived from that index.

The Mail 16 flag mapping is:

| `FLAG_INDEX` | `FLAG_COLOR` |
| ---: | --- |
| `-1` | `none` |
| `0` | `red` |
| `1` | `orange` |
| `2` | `yellow` |
| `3` | `green` |
| `4` | `blue` |
| `5` | `purple` |
| `6` | `gray` |

Unknown future indices are reported as `unknown` while preserving the raw
index. Listing flag metadata is read-only; the skill does not change flags.

## Selection JSON

Use a list or an object containing `messages`, `items`, or `records`:

```json
[
  {
    "mail_id": 123,
    "message_id": "stable@example.com",
    "subject": "Example",
    "sender": "Sender <sender@example.com>",
    "received_at": "2018-03-07T12:00:00",
    "read": false
  }
]
```

## Plan

```sh
"$APPLE_MAIL" plan-gmail-transfer \
  --account "person@example.com" \
  --destination "On My Mac/Review" \
  --selection selection.json --output transfer-plan.json

"$APPLE_MAIL" plan-gmail-junk-transfer \
  --account "person@example.com" \
  --mailbox "Junk" \
  --destination "On My Mac/Review" \
  --selection selection.json --output junk-transfer-plan.json

"$APPLE_MAIL" plan-local-move \
  --source "On My Mac/Review" \
  --destination "On My Mac/Archive" \
  --selection selection.json --output local-plan.json

"$APPLE_MAIL" plan-set-read \
  --account "person@example.com" --mailbox INBOX \
  --state read \
  --selection selection.json --output read-plan.json

"$APPLE_MAIL" plan-create-mailbox \
  --destination "On My Mac/New Mailbox" \
  --output mailbox-plan.json
```

## Inspect, dry-run, execute, verify

```sh
"$APPLE_MAIL" inspect-plan --plan transfer-plan.json

"$APPLE_MAIL" apply \
  --plan transfer-plan.json \
  --allow-destination "On My Mac/Review"

"$APPLE_MAIL" apply \
  --plan transfer-plan.json \
  --allow-destination "On My Mac/Review" \
  --token gmail-token.json \
  --expected-account "person@example.com" \
  --audit audit.jsonl \
  --execute

"$APPLE_MAIL" apply \
  --plan transfer-plan.json \
  --allow-destination "On My Mac/Review" \
  --token gmail-token.json \
  --expected-account "person@example.com" \
  --audit audit.jsonl \
  --resume \
  --execute

"$APPLE_MAIL" verify --plan transfer-plan.json

"$APPLE_MAIL" reconcile \
  --plan transfer-plan.json \
  --audit audit.jsonl

"$APPLE_MAIL" probe-copy --plan transfer-plan.json
```

Read-state plans omit `--allow-destination`. All execution requires `--audit`.
Gmail execution additionally requires `--token` and `--expected-account`.
Read-only Gmail resolution and per-message `INBOX` or `SPAM` label changes
accept at most fifty selected messages and use at most ten concurrent network
requests. Inbox plans remove only `INBOX`. Junk plans require `SPAM` on every
resolved Gmail message, remove `SPAM`, and remove `INBOX` if Gmail adds it
during that transition. Label removal still requires a confirmed final state
per message; if any request fails, every confirmed change is rolled back before
the command reports failure.
Verification reports separate source match Booleans for Message-ID, subject,
sender, and received time. A failed mutation preflight names only the plan item
positions and mismatched field names; it does not print message content.
Post-Gmail verification treats Mail error `-1719` from a disappearing indexed
Inbox lookup as zero source matches; every other Mail error still propagates.
Mail error `-10000` is retried only for the same indexed read on the bounded
0.1, 0.2, 0.4, and 0.8 second schedule. A persistent failure remains an error
and is never interpreted as source absence.
`probe-copy` is valid only for a Gmail Inbox- or Spam-to-local plan. It
executes the copy AppleScript's bounded source-selector resolution, in-memory
identity corroboration, destination candidate, and selector-count path,
reports copied/reused aggregate counts, and exits before `duplicate`. Gmail
transfer plans are capped at fifty messages per transaction. Mail copy and
verification work is split into ordered chunks of at most ten messages. All
independently validated chunks are submitted serially before one bounded
whole-plan durability barrier runs on the fixed 5- and 10-second schedule. The
barrier re-resolves every source and requires exactly one identity-matching,
read-preserved destination copy for every plan item. It never polls
continuously, and Gmail label removal cannot begin until the complete barrier
passes.

After confirmed Gmail label removal, execution requests one Mail
synchronization and returns `pending_mail_sync` without launching a
predictably premature full cache verification. Do not reapply. Run one later
bounded `reconcile` with the same immutable plan and audit before beginning
another sequential block. Reconciliation is read-only and needs neither OAuth
nor a destination allowlist. It appends and returns:

- `complete` only when every destination has exactly one identity-matching
  copy with preserved read state and every planned source is absent;
- `pending_mail_sync` when every destination is valid, every source is either
  exact or absent, and at least one exact source still remains; or
- `mutation_state_unknown` for invalid, unreadable, ambiguous, or
  numeric-ID-reuse states.

The reconciliation audit contains only the action, plan hash, aggregate
counts, status, and generic reason codes. Use `verify` when raw per-message
diagnostics are needed; unlike `reconcile`, it does not append a lifecycle
event. `DESTINATION_COUNT=1` already denotes one fully identity-matching copy:
the verifier rejects Message-ID collisions and counts only full identity
matches.

`--resume` is a mutation mode only for a Gmail transfer whose same audit ends
in `operation_failed` or `mutation_state_unknown` after an earlier
`operation_started`. It first verifies one exact, read-preserved destination
copy for every planned message. It submits no Mail copy, accepts only the
action-specific Gmail source label being either present or already absent,
and removes the label only from the still-present subset. Spam resume also
requires `INBOX` absent before proceeding. A normal apply remains strict and
requires the source label on every selected Gmail message.
`reconcile` refuses an audit whose latest matching lifecycle event is
`operation_failed`; Mail's cache cannot authoritatively close a failed Gmail
mutation. After resume returns `pending_mail_sync`, reconciliation is enabled
again.

## OAuth

```sh
"$APPLE_MAIL" authorize \
  --client-secrets gmail-client-credentials.json \
  --token gmail-token.json
```

The same token can be supplied to the read-only `get-batch` fast path. No
additional scope or authorization grant is required.

The `plan-gmail-spam-transfer` spelling is accepted as an alias for
`plan-gmail-junk-transfer`. Always pass the exact Mail mailbox name from
`discover`; the Gmail label preflight, not that display name, proves that every
selected message is actually in `SPAM`.
