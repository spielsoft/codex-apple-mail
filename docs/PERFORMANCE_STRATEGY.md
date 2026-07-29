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
an absolute tolerance of at most 25 hours. This admits an adjacent-day
representation plus a small client/server processing skew without accepting
the nearly 48-hour discrepancy that calendar-date comparison could allow.

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
   A slow-settling chunk does not block submission of later independently
   validated chunks.
4. After all chunks have returned, run one bounded whole-plan durability
   barrier. Re-resolve every source and require exactly one identity-matching,
   read-preserved local copy for every plan item on the fixed 5- and 10-second
   schedule. Never poll continuously. Do not begin any Gmail mutation unless
   this complete barrier passes.
5. Remove only the action-specific Gmail source label with bounded concurrent
   per-message responses. Bind response IDs and accept complete returned label
   snapshots; issue targeted metadata reads for responses that omit
   `labelIds`. Targeted metadata reads use a short bounded retry schedule and
   treat an omitted empty repeated field as an empty label set; mutation calls
   are never retried implicitly. Spam removal clears any `INBOX` labels found
   in those complete snapshots. On any failure, restore the complete Inbox or
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
