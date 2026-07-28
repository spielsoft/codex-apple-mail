# Mail Performance Strategy

**Read when:** changing lookup, batching, verification, or Gmail-to-local
transactions.

## Decision

Bind messages through Mail's indexed numeric IDs, corroborate durable RFC
identity and metadata, and use one bulk Mail command per bounded internal
chunk.

Never perform one large-mailbox RFC Message-ID scan per message. Numeric IDs
are fast but non-durable, so a numeric hit without complete corroboration must
fail closed.

Gmail `internalDate` is compared to the plan's local-naive `received_at` with
an absolute tolerance of at most 24 hours. This admits adjacent-midnight
representations without accepting a wider discrepancy than calendar-date
comparison previously could.

Mail Apple Events must remain serial. Independent Gmail API requests may run
with at most ten concurrent workers inside a fifty-message transaction. The
client resolves its OAuth access token once per process, while a private
per-token file lock serializes refresh across processes.

## Transaction shape

For Gmail Inbox- or Spam-to-local:

1. Resolve the account, source, and destination once.
2. Resolve and validate each ordered internal Mail chunk from one complete
   numeric-ID selector. Do not launch a separate indexed Mail query per message
   or a redundant verifier process before the copy script.
3. Submit one bulk `duplicate` command per internal chunk using a direct
   numeric-ID-filtered Mail object specifier capped at ten transfer messages.
   Do not begin Gmail mutation until every chunk's local-copy barrier passes.
4. For each submitted chunk, refresh destination Message-IDs after `duplicate`
   and corroborate only the matching candidates. Because Mail may expose copies
   asynchronously, take snapshots after fixed 1.5 and 4.8 second delays,
   stopping after the first complete snapshot. Treat the final result as the
   local-copy barrier; never poll beyond the same 6.3-second wait bound.
5. Remove only the action-specific Gmail source label with bounded concurrent
   per-message responses. Spam removal also clears `INBOX` if Gmail adds it
   during the not-spam transition. Wait for every response; on any failure,
   authoritatively read every planned Gmail ID, restore the complete Inbox or
   Spam pre-state, then read every ID again before reporting rollback or an
   unknown mutation state.
6. Request one Mail synchronization.
7. Return `pending_mail_sync` without immediately querying the cache that was
   just asked to synchronize. A later bounded `reconcile` establishes and
   audits Mail's aggregate transfer state before another sequential block
   begins.

For local-to-local filing, use the same binding stage followed by one bulk
`move`.

## Expected complexity

The Mail work should scale with batch size plus one destination Message-ID
snapshot per ten-message transfer chunk, not batch size multiplied by
source-mailbox size. General metadata and local operations are capped at 250;
Gmail transfers and batch body reads are capped at fifty.

For Gmail transfer verification, resolve each ten-message numeric-ID selector
once, corroborate its returned messages in memory, and normalize the combined
bulk count across the full plan. Retain the per-ID verifier only as the larger
general-operation fallback.

For Gmail body retrieval from any exact account mailbox,
`get-batch --token --expected-account` performs two concurrent phases: first
resolve and corroborate every selected identity and read state, then fetch full
bodies. The phase boundary prevents a bad selection from causing any body
retrieval. The serial AppleScript backend remains available when no token is
supplied. If the full Gmail payload exposes a selected text body only through
an attachment identifier, the client does not issue a prohibited
attachment-content request. Only that explicit body-unavailable result falls
back to one bounded AppleScript batch after the Gmail identity barrier;
unrelated Gmail errors propagate. RFC Message-ID search includes Spam and
Trash, but the recent Apple Mail selection remains the identity and mailbox
boundary.

## Live validation gate

After changing this design:

1. run all synthetic tests and compile every AppleScript;
2. benchmark a read-only batch of up to fifty recent numeric IDs;
3. inspect a no-mutation dry run; and
4. obtain explicit authorization before any live mutation.
