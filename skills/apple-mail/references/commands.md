# Command Reference

Set `APPLE_MAIL` to the absolute path of this skill's `scripts/apple-mail`
entry point.

Commands that access Mail or Gmail require macOS Apple Events or network
access. Run the first `discover`, `list`, `get`, `get-batch`, `verify`, `probe-copy`,
`apply --execute`, or `authorize` attempt with scoped sandbox escalation. Do
not spend a failed attempt discovering this requirement. Planning, plan
inspection, and dry runs remain local and can run in the normal workspace
sandbox.

## Read

```sh
"$APPLE_MAIL" discover

"$APPLE_MAIL" list \
  --account "person@example.com" --mailbox INBOX \
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
```

`get` returns one `MESSAGE` record. Its `BODY` field preserves embedded line
breaks and Unicode line or paragraph separators without creating extra
records. `get-batch` returns one ordered `MESSAGE` record per selected identity,
accepts at most ten messages, and validates every identity before retrieving
any body. Do not parallelize singleton `get` calls against Mail.

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

"$APPLE_MAIL" verify --plan transfer-plan.json

"$APPLE_MAIL" probe-copy --plan transfer-plan.json
```

Read-state plans omit `--allow-destination`. All execution requires `--audit`.
Gmail execution additionally requires `--token` and `--expected-account`.
Verification reports separate source match Booleans for Message-ID, subject,
sender, and received time. A failed mutation preflight names only the plan item
positions and mismatched field names; it does not print message content.
Post-Gmail verification treats Mail error `-1719` from a disappearing indexed
Inbox lookup as zero source matches; every other Mail error still propagates.
Mail error `-10000` is retried only for the same indexed read on the bounded
0.1, 0.2, 0.4, and 0.8 second schedule. A persistent failure remains an error
and is never interpreted as source absence.
`probe-copy` is valid only for a Gmail Inbox-to-local plan. It executes the
copy AppleScript's source/destination resolution, identity, candidate, and
selector-count path, reports copied/reused aggregate counts, and exits before
`duplicate`. Gmail transfer plans are intentionally capped at ten messages per
transaction. Execution waits on a fixed, bounded destination-visibility
schedule for at most 6.3 seconds after `duplicate`; it never polls
continuously.

## OAuth

```sh
"$APPLE_MAIL" authorize \
  --client-secrets gmail-client-credentials.json \
  --token gmail-token.json
```
