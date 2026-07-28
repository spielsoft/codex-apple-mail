# Gmail OAuth Setup

**Read when:** authorizing, refreshing, revoking, or troubleshooting Gmail.

Gmail authorization is optional. Apple Mail discovery, listing, reading, local
mailbox creation, local moves, and read-state changes do not need Google
credentials. Gmail Inbox-to-local transfers use this flow. A Gmail Inbox
`get-batch` can also use the same token as an optional faster read backend.

The Gmail API is used only for bounded message lookup/body retrieval and adding
or removing `INBOX` after a local copy is verified. `gmail.modify` already
includes the read access needed by the optional batch-read path, so it does
not request another scope. The desktop OAuth flow prints a URL and waits on
localhost; it does not control a browser.

## Setup

1. Select a permitted Google Cloud project.
2. Enable the Gmail API.
3. Configure the consent screen.
4. Add only `https://www.googleapis.com/auth/gmail.modify`.
5. Create a Desktop app OAuth client.
6. Store the downloaded client JSON outside the plugin tree, or in the
   consuming project's private, gitignored `local-artifacts/` directory.

The client JSON and token are runtime inputs, never plugin source files. The
repository ignores credential-like JSON, token files, environment files, and
private key files, but do not rely on ignore rules as a substitute for keeping
secrets outside the repository.

Workspace policy may block authorization. Do not work around it.

## Authorize

```sh
scripts/apple-mail authorize \
  --client-secrets /private/path/gmail-client-credentials.json \
  --token /private/path/gmail-token.json
```

The command binds to `127.0.0.1`, validates OAuth state, uses PKCE, requests
only `gmail.modify`, writes mode `0600`, and refuses to overwrite a token.
Keep the token path private and do not commit either input or output file.

Every Gmail transfer compares the authenticated profile, expected account
argument, and account embedded in the hashed plan.

For an already-authorized account, the read-only fast path is:

```sh
scripts/apple-mail get-batch \
  --account "person@example.com" --mailbox INBOX \
  --selection /private/path/selection.json \
  --body-limit 50000 \
  --token /private/path/gmail-token.json \
  --expected-account "person@example.com"
```

It performs a complete bounded metadata and read-state corroboration before
retrieving any body. It does not change labels, read state, or Mail.

Never store credentials or tokens in this plugin repository.

This plugin intentionally uses a narrow local desktop flow rather than a
browser-control workflow or a connector-managed account. Workspace policy may
require an administrator to approve the OAuth client; do not work around that
policy.

Official references:

- [Gmail API OAuth scopes](https://developers.google.com/workspace/gmail/api/auth/scopes)
- [OAuth for desktop apps](https://developers.google.com/identity/protocols/oauth2/native-app)
- [Workspace app-access controls](https://support.google.com/a/answer/7281227)
