# Mail Performance Strategy

**Read when:** changing lookup, batching, verification, or Gmail-to-local
transactions.

## Decision

Bind messages through Mail's indexed numeric IDs, corroborate durable RFC
identity and metadata, and use one bulk Mail command per batch.

Never perform one large-mailbox RFC Message-ID scan per message. Numeric IDs
are fast but non-durable, so a numeric hit without complete corroboration must
fail closed.

Mail Apple Events must remain serial. Independent Gmail API requests may run
concurrently within the fixed ten-message bound. The client resolves its OAuth
access token once per process so concurrent reads never race token refresh.

## Transaction shape

For Gmail Inbox-to-local:

1. Resolve the account, source, and destination once.
2. Resolve the complete bounded numeric-ID selector once and validate every
   selected source from that result. Do not launch a separate indexed Mail
   query per message or a redundant verifier process before the copy script.
3. Submit one bulk `duplicate` command using a direct numeric-ID-filtered Mail
   object specifier capped at ten transfer messages.
4. Refresh destination Message-IDs after `duplicate` and corroborate only the
   matching candidates. Because Mail may expose accepted copies
   asynchronously, take snapshots after fixed 1.5 and 4.8 second delays,
   stopping after the first complete snapshot. Treat the final result as the
   local-copy barrier; never poll beyond the same 6.3-second wait bound.
5. Remove only Gmail `INBOX` with bounded concurrent per-message responses.
   Wait for every response; on any failure, roll back every confirmed change
   before returning the error.
6. Request one Mail synchronization.
7. Return `pending_mail_sync` without immediately querying the cache that was
   just asked to synchronize. A later bounded `reconcile` establishes and
   audits Mail's aggregate transfer state before another sequential block
   begins.

For local-to-local filing, use the same binding stage followed by one bulk
`move`.

## Expected complexity

The Mail work should scale with batch size plus one destination Message-ID
snapshot, not batch size multiplied by source-mailbox size. General metadata
and local operations are capped at 250; Gmail transfers and batch body reads
are capped at ten.

For verification batches of ten or fewer, resolve the complete numeric-ID
selector once and corroborate its returned messages in memory. Retain the
per-ID verifier only as the larger general-operation fallback.

For Gmail Inbox body retrieval, `get-batch --token --expected-account` performs
two concurrent phases: first resolve and corroborate every selected identity
and read state, then fetch full bodies. The phase boundary prevents a bad
selection from causing any body retrieval. The serial AppleScript backend
remains available when no token is supplied. If the full Gmail payload exposes
a selected text body only through an attachment identifier, the client does
not issue a prohibited attachment-content request. Only that explicit
body-unavailable result falls back to one bounded AppleScript batch after the
Gmail identity barrier; unrelated Gmail errors propagate.

## Live validation gate

After changing this design:

1. run all synthetic tests and compile every AppleScript;
2. benchmark a read-only batch of ten recent numeric IDs;
3. inspect a no-mutation dry run; and
4. obtain explicit authorization before any live mutation.
