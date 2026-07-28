on replaceText(theText, oldText, newText)
	set AppleScript's text item delimiters to oldText
	set textParts to every text item of theText
	set AppleScript's text item delimiters to newText
	set theText to textParts as text
	set AppleScript's text item delimiters to ""
	return theText
end replaceText

on escapeField(theValue)
	if theValue is missing value then return ""
	set escaped to theValue as text
	set escaped to my replaceText(escaped, "\\", "\\\\")
	set escaped to my replaceText(escaped, tab, "\\t")
	set escaped to my replaceText(escaped, linefeed, "\\n")
	set escaped to my replaceText(escaped, return, "\\r")
	return escaped
end escapeField

on mailboxPath(theMailbox)
	tell application "Mail"
		set pathParts to {name of theMailbox}
		set currentContainer to missing value
		try
			set currentContainer to container of theMailbox
		end try
		repeat
			try
				set containerName to name of currentContainer
				set nextContainer to container of currentContainer
			on error
				exit repeat
			end try
			set beginning of pathParts to containerName
			if nextContainer is missing value then exit repeat
			set currentContainer to nextContainer
		end repeat
	end tell
	set AppleScript's text item delimiters to "/"
	set pathText to pathParts as text
	set AppleScript's text item delimiters to ""
	return pathText
end mailboxPath

on mailboxLine(recordType, accountName, accountID, theMailbox)
	tell application "Mail"
		set messageCount to count of messages of theMailbox
		set unreadMessageCount to «class mbuc» of theMailbox
		set mailboxName to name of theMailbox
	end tell
	return recordType & tab & my escapeField(accountName) & tab & my escapeField(accountID) & tab & my escapeField(my mailboxPath(theMailbox)) & tab & my escapeField(mailboxName) & tab & messageCount & tab & unreadMessageCount
end mailboxLine

on run
	set outputLines to {"TYPE" & tab & "ACCOUNT" & tab & "ACCOUNT_ID" & tab & "PATH" & tab & "NAME" & tab & "MESSAGE_COUNT" & tab & "UNREAD_COUNT"}
	tell application "Mail"
		repeat with accountReference in accounts
			set theAccount to contents of accountReference
			set accountName to name of theAccount
			set accountID to ""
			try
				set accountID to id of theAccount
			end try
			set end of outputLines to "ACCOUNT" & tab & my escapeField(accountName) & tab & my escapeField(accountID) & tab & "" & tab & "" & tab & "" & tab & ""
			repeat with mailboxReference in mailboxes of theAccount
				set end of outputLines to my mailboxLine("MAILBOX", accountName, accountID, contents of mailboxReference)
			end repeat
		end repeat
		repeat with mailboxReference in mailboxes
			set theMailbox to contents of mailboxReference
			set isLocal to false
			try
				set ignoredAccount to account of theMailbox
				if ignoredAccount is missing value then set isLocal to true
			on error
				set isLocal to true
			end try
			if isLocal then set end of outputLines to my mailboxLine("LOCAL", "On My Mac", "", theMailbox)
		end repeat
	end tell
	set AppleScript's text item delimiters to linefeed
	set outputText to outputLines as text
	set AppleScript's text item delimiters to ""
	return outputText
end run
