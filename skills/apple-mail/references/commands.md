# Command Reference

Set `APPLE_MAIL` to the absolute path of this skill's `scripts/apple-mail`
entry point.

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
```

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
```

Read-state plans omit `--allow-destination`. All execution requires `--audit`.
Gmail execution additionally requires `--token` and `--expected-account`.

## OAuth

```sh
"$APPLE_MAIL" authorize \
  --client-secrets gmail-client-credentials.json \
  --token gmail-token.json
```
