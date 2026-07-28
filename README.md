# codex-apple-mail

A generic Codex plugin for reading and organizing Apple Mail through
transparent background scripts—without Computer Control.

Capabilities include mailbox discovery, bounded message reading, read/unread
changes, local mailbox creation, local-to-local moves, and verified Gmail
Inbox-to-local transfers.

The plugin manifest is [.codex-plugin/plugin.json](.codex-plugin/plugin.json)
and the bundled skill is [skills/apple-mail/SKILL.md](skills/apple-mail/SKILL.md).
See [AGENTS.md](AGENTS.md) for development guidance.

## Installation and use

The repository root is the installable plugin. Keep the `codex-apple-mail`
directory name and the manifest `name` synchronized. Use the bundled skill's
`scripts/apple-mail` entry point for every Mail operation; the root-level
`scripts/apple-mail` command is only a development convenience wrapper.

Apple Mail discovery, listing, reading, local mailbox creation, local moves,
and read-state changes do not require Google authentication. Gmail OAuth is
needed only for a Gmail Inbox-to-local transfer. See [docs/OAUTH.md](docs/OAUTH.md)
for the optional setup and [docs/PUBLISHING.md](docs/PUBLISHING.md) before
pushing this repository to GitHub.
