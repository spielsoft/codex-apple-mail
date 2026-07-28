# Interface Research

**Read when:** revisiting the automation interface or provider transaction.

## Conclusions

- Apple Events is the supported background interface for Mail accounts,
  mailboxes, messages, metadata, read state, mailbox creation, and moves.
- Mail's numeric message ID is indexed but short-lived. RFC Message-ID is
  durable but can be slow to query over large mailboxes.
- Mail's custom list `duplicate` and `move` commands are intended for efficient
  bulk operations.
- Gmail represents Inbox as a label; Archive removes `INBOX` while retaining
  the message in All Mail.
- AppleScript cross-store moves can copy locally without reliably removing
  Gmail `INBOX`, while the GUI behaves differently.
- Gmail API `users.messages.modify` limited to `INBOX` is narrower and more
  auditable than IMAP deletion semantics.

## Rejected approaches

- Computer Control or Accessibility UI scripting prevents transparent
  background use.
- Direct Mail database or `.emlx` access depends on private formats and cannot
  safely mutate Mail objects.
- IMAP `\Deleted`/`EXPUNGE` and standalone Mail deletion can route messages to
  Trash and are outside scope.
- JXA and ScriptingBridge expose the same Mail automation semantics rather than
  a hidden GUI-equivalent move.
- MailKit actions target newly downloaded messages, not arbitrary historical
  filing.

## Primary references

- [Apple scripting dictionary guidance](https://developer.apple.com/library/archive/documentation/LanguagesUtilities/Conceptual/MacAutomationScriptingGuide/NavigateaScriptingDictionary.html)
- [Gmail API message modification](https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.messages/modify)
- [Gmail archive behavior](https://support.google.com/mail/answer/6576)
- [MsgFiler AppleScript filing analysis](https://msgfiler.wordpress.com/2024/02/12/a-deep-dive-into-filing-mail-messages-using-applescript/)
- [sweetrb/apple-mail-mcp bulk implementation](https://github.com/sweetrb/apple-mail-mcp)
- [apple-mail-fast-mcp architecture](https://github.com/s-morgan-jeffries/apple-mail-fast-mcp)
