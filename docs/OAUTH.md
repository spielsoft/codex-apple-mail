# Gmail OAuth Setup

**Read when:** authorizing, refreshing, revoking, or troubleshooting Gmail.

Gmail authorization is optional. Apple Mail discovery, listing, reading, local
mailbox creation, local moves, and read-state changes do not need Google
credentials. Gmail Inbox- and Spam-to-local transfers use this flow.
`get-batch` can also use the same token as an optional faster read backend for
recent selections from any exact account mailbox.

The Gmail API is used only for bounded message lookup/body retrieval and adding
or removing the allowlisted `INBOX` and `SPAM` source labels after a local copy
is verified. `gmail.modify` already includes the read access needed by the
optional batch-read path, so it does not request another scope. The desktop
OAuth flow prints a URL and waits on localhost; it does not control a browser.

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
Token refreshes are serialized across processes by a mode-`0600` sibling lock
file. After acquiring that lock, each process reloads the token so a refresh
completed by another process is reused. A required refresh is fsynced to a
unique mode-`0600` file in the token directory and atomically replaces the
prior token; failures before that atomic replacement leave the prior token
intact and remove the temporary file.

Every Gmail transfer compares the authenticated profile, expected account
argument, and account embedded in the hashed plan.

For an already-authorized account, the read-only fast path is:

```sh
scripts/apple-mail get-batch \
  --account "person@example.com" --mailbox "Junk" \
  --selection /private/path/selection.json \
  --body-limit 50000 \
  --token /private/path/gmail-token.json \
  --expected-account "person@example.com"
```

It performs a complete bounded metadata and read-state corroboration before
retrieving any body. It does not change labels, read state, or Mail. Gmail
RFC Message-ID lookup includes Spam and Trash so the same read path works for
recent selections from Junk/Spam, Important, Sent, custom-label, and other
account mailboxes. Gmail sometimes represents a large text body with an
attachment identifier rather than inline data. The API client never follows
that identifier because
attachment-content reads are prohibited. In that specific case, after Gmail
identity validation has succeeded, `get-batch` uses its bounded Apple Mail
backend for the selected batch. Authentication, network, and identity failures
still fail closed instead of falling back.

Never store credentials or tokens in this plugin repository.

This plugin intentionally uses a narrow local desktop flow rather than a
browser-control workflow or a connector-managed account. Workspace policy may
require an administrator to approve the OAuth client; do not work around that
policy.

Official references:

- [Gmail API OAuth scopes](https://developers.google.com/workspace/gmail/api/auth/scopes)
- [Gmail message listing](https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.messages/list)
- [Gmail message modification](https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.messages/modify)
- [Gmail system and user labels](https://developers.google.com/workspace/gmail/api/guides/labels)
- [OAuth for desktop apps](https://developers.google.com/identity/protocols/oauth2/native-app)
- [Workspace app-access controls](https://support.google.com/a/answer/7281227)
