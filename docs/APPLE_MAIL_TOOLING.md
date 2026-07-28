# Generic Apple Mail Tool

**Read when:** using the bundled `apple-mail` skill or development wrapper.

## Codex execution permission

Mail automation uses macOS Apple Events, which are outside Codex's default
command sandbox. A task that invokes this plugin authorizes Codex to request
the required scoped escalation on the first Mail-accessing command rather than
probing in the sandbox first. This includes the read-only `probe-copy`
diagnostic. Codex's active approval policy still decides whether that
escalation is auto-reviewed or shown to the user. Planning, inspection, and
dry runs do not need Apple Events access.

## Capabilities

```sh
scripts/apple-mail discover

scripts/apple-mail list \
  --account "person@example.com" --mailbox INBOX \
  --start 1 --limit 50

scripts/apple-mail list \
  --local "On My Mac/Archive" \
  --start 1 --limit 50

scripts/apple-mail get \
  --account "person@example.com" --mailbox INBOX \
  --mail-id 123 --message-id "stable@example.com" \
  --body-limit 50000

scripts/apple-mail get-batch \
  --account "person@example.com" --mailbox INBOX \
  --selection local-artifacts/selection.json \
  --body-limit 50000

scripts/apple-mail get-batch \
  --account "person@example.com" --mailbox INBOX \
  --selection local-artifacts/selection.json \
  --body-limit 50000 \
  --token local-artifacts/gmail-token.json \
  --expected-account "person@example.com"
```

`list` returns Mail order and never retrieves bodies. Message rows retain the
Boolean `FLAGGED` field and also include Mail's integer `FLAG_INDEX` plus a
derived `FLAG_COLOR`: `-1` is `none`, and indices `0` through `6` are `red`,
`orange`, `yellow`, `green`, `blue`, `purple`, and `gray`. Unknown indices are
reported as `unknown` without discarding the raw value. Listing does not change
flags. `get` binds by indexed numeric ID, corroborates RFC Message-ID, and
bounds body output to 100,000 characters. Embedded body line breaks and Unicode
line or paragraph separators remain inside one `MESSAGE` record. `get-batch`
validates up to ten selected identities in one Mail process before retrieving
their bodies; use it instead of concurrent singleton reads. When a Gmail token
and expected account are supplied, it instead uses bounded concurrent Gmail
API calls, with a complete metadata/read-state barrier before any full body is
fetched. If Gmail represents a selected text body only through an attachment
identifier, the request layer does not fetch that attachment; after the Gmail
identity barrier succeeds, `get-batch` falls back to the same bounded Mail
batch rather than returning an incomplete body. Other Gmail failures remain
errors and do not trigger fallback.

`ATTACHMENT_COUNT_SOURCE` identifies how `get-batch` produced
`ATTACHMENT_COUNT`: `apple_mail` is Mail's native attachment object count and
`gmail_mime` is a count derived from Gmail MIME metadata. The source field
makes the two backend semantics explicit while retaining the existing count.

## Selection format

Plan commands consume a JSON list, or an object containing `messages`,
`items`, or `records`:

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

## Plan commands

```sh
scripts/apple-mail plan-gmail-transfer \
  --account "person@example.com" \
  --destination "On My Mac/Review" \
  --selection local-artifacts/selection.json \
  --output local-artifacts/transfer-plan.json

scripts/apple-mail plan-local-move \
  --source "On My Mac/Review" \
  --destination "On My Mac/Archive" \
  --selection local-artifacts/selection.json \
  --output local-artifacts/local-plan.json

scripts/apple-mail plan-set-read \
  --account "person@example.com" --mailbox INBOX \
  --state read \
  --selection local-artifacts/selection.json \
  --output local-artifacts/read-plan.json

scripts/apple-mail plan-create-mailbox \
  --destination "On My Mac/New Mailbox" \
  --output local-artifacts/mailbox-plan.json
```

Plan output is exclusive: choose a new filename rather than overwrite a plan.

## Inspect, dry run, apply, and verify

```sh
scripts/apple-mail inspect-plan --plan local-artifacts/transfer-plan.json

scripts/apple-mail apply \
  --plan local-artifacts/transfer-plan.json \
  --allow-destination "On My Mac/Review"

scripts/apple-mail apply \
  --plan local-artifacts/transfer-plan.json \
  --allow-destination "On My Mac/Review" \
  --token local-artifacts/gmail-token.json \
  --expected-account "person@example.com" \
  --audit local-artifacts/audit.jsonl \
  --execute

scripts/apple-mail verify --plan local-artifacts/transfer-plan.json

scripts/apple-mail reconcile \
  --plan local-artifacts/transfer-plan.json \
  --audit local-artifacts/audit.jsonl

scripts/apple-mail probe-copy --plan local-artifacts/transfer-plan.json
```

`probe-copy` is a read-only diagnostic for Gmail transfer plans. It exercises
the copy script's resolution, identity, candidate, and selector-count path,
reports missing and reused copies, then exits before `duplicate`. Gmail
transfer transactions are capped at ten messages.

During execution, the copy script resolves the complete bounded numeric-ID
selector once, validates every source, and rechecks destination visibility
after fixed 1.5 and 4.8 second delays for at most 6.3 seconds after
`duplicate`. It stops after the first complete snapshot and reports
`pending_local_copy` without changing Gmail when Mail still has not exposed
every exact copy.

Execution reports `phase_seconds` for Gmail profile lookup, Gmail preflight,
local copy, Gmail label removal, Mail synchronization, and total transaction
time. These timings contain no message content. The copy script is the
authoritative Mail preflight and local-copy barrier, so execution does not
launch redundant full verifier processes before or immediately after it.

During Mail synchronization, an indexed read can transiently fail with Mail
error `-10000`. Verification retries only that exact read after 0.1, 0.2, 0.4,
and 0.8 seconds. A fifth failure and every other unexpected Mail error still
propagate; `-10000` is never treated as proof that a source is absent.

`apply` is a dry run unless `--execute` is present. Execution requires an audit
path. Destination-bearing plans require an exact allowlist on both dry run and
execution. `set_read` has no destination allowlist.

Verification reports separate source match Booleans for Message-ID, subject,
sender, and received time. It also reports `SOURCE_BULK_COUNT`, which must equal
the plan batch size before a bulk copy or move can run. A failed mutation
preflight identifies only plan item positions and mismatched field names; it
never includes message content. During post-Gmail verification, Mail error
`-1719` from an indexed source lookup is treated as the expected zero-result
state; all other Mail errors remain failures.

A successful Gmail label-removal phase returns `pending_mail_sync` after
requesting one synchronization. Do not reapply. Wait one synchronization
interval and run one bounded `reconcile` with the same plan and audit.
Reconciliation is read-only and requires no OAuth. It appends `complete` only
when every destination copy is exact and read-preserved and every source is
absent. It retains `pending_mail_sync` while every source is either exact or
absent and at least one exact source remains during cache convergence, and
appends `mutation_state_unknown` for invalid, unreadable, ambiguous, or
numeric-ID-reuse evidence. `DESTINATION_COUNT=1` already denotes one fully
identity-matching copy because verification rejects Message-ID collisions and
counts only complete identity matches. Begin another sequential block only
after reconciliation reports `complete`. Use `verify` separately when
per-message diagnostics are needed; it does not append a lifecycle event.

## OAuth

```sh
scripts/apple-mail authorize \
  --client-secrets local-artifacts/gmail-client-credentials.json \
  --token local-artifacts/gmail-token.json
```

See [OAUTH.md](OAUTH.md) for setup and storage rules.
