# Mail Performance Strategy

**Read when:** changing lookup, batching, verification, or Gmail-to-local
transactions.

## Decision

Bind messages through Mail's indexed numeric IDs, corroborate durable RFC
identity and metadata, and use one bulk Mail command per batch.

Never perform one large-mailbox RFC Message-ID scan per message. Numeric IDs
are fast but non-durable, so a numeric hit without complete corroboration must
fail closed.

## Transaction shape

For Gmail Inbox-to-local:

1. Resolve the account, source, and destination once.
2. Bind and validate every source by numeric ID.
3. Submit one bulk `duplicate` command using a direct numeric-ID-filtered Mail
   object specifier.
4. Traverse the local destination once and verify the complete set.
5. Remove only Gmail `INBOX` with per-message responses and rollback.
6. Request one Mail synchronization.
7. Perform one final indexed source check.

For local-to-local filing, use the same binding stage followed by one bulk
`move`.

## Expected complexity

The Mail work should scale with batch size plus one destination traversal, not
batch size multiplied by source-mailbox size. Batches are capped at 250.

## Live validation gate

After changing this design:

1. run all synthetic tests and compile every AppleScript;
2. benchmark a read-only batch of ten recent numeric IDs;
3. inspect a no-mutation dry run; and
4. obtain explicit authorization before any live mutation.
