# Generic Apple Mail Tool

**Read when:** using the bundled `apple-mail` skill or development wrapper.

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
```

`list` returns Mail order and never retrieves bodies. Message rows retain the
Boolean `FLAGGED` field and also include Mail's integer `FLAG_INDEX` plus a
derived `FLAG_COLOR`: `-1` is `none`, and indices `0` through `6` are `red`,
`orange`, `yellow`, `green`, `blue`, `purple`, and `gray`. Unknown indices are
reported as `unknown` without discarding the raw value. Listing does not change
flags. `get` binds by indexed numeric ID, corroborates RFC Message-ID, and
bounds body output to 100,000 characters.

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
```

`apply` is a dry run unless `--execute` is present. Execution requires an audit
path. Destination-bearing plans require an exact allowlist on both dry run and
execution. `set_read` has no destination allowlist.

## OAuth

```sh
scripts/apple-mail authorize \
  --client-secrets local-artifacts/gmail-client-credentials.json \
  --token local-artifacts/gmail-token.json
```

See [OAUTH.md](OAUTH.md) for setup and storage rules.
