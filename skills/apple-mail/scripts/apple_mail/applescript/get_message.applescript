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

on beginsWith(theText, prefixText)
	if prefixText is "" then return true
	if (count of theText) < (count of prefixText) then return false
	return text 1 thru (count of prefixText) of theText is prefixText
end beginsWith

on resolveSource(sourceKind, sourceName, sourcePath)
	tell application "Mail"
		if sourceKind is "account" then
			if not (exists account (sourceName as text)) then error "Account not found"
			set sourceAccount to account (sourceName as text)
			if not (exists mailbox (sourcePath as text) of sourceAccount) then error "Account mailbox not found"
			return mailbox (sourcePath as text) of sourceAccount
		end if
		if sourceKind is not "local" then error "Unsupported source kind"
		if not my beginsWith(sourcePath, "On My Mac/") then error "Invalid local path"
		set relativePath to text 11 thru -1 of sourcePath
		set AppleScript's text item delimiters to "/"
		set pathParts to every text item of relativePath
		set AppleScript's text item delimiters to ""
		set rootName to item 1 of pathParts
		if not (exists mailbox (rootName as text)) then error "Local mailbox not found"
		set resolvedMailbox to mailbox (rootName as text)
		repeat with partIndex from 2 to count of pathParts
			set childName to item partIndex of pathParts
			if not (exists mailbox (childName as text) of resolvedMailbox) then error "Local mailbox not found"
			set resolvedMailbox to mailbox (childName as text) of resolvedMailbox
		end repeat
		return resolvedMailbox
	end tell
end resolveSource

on normalizedMessageID(theText)
	set normalized to theText as text
	if normalized begins with "<" and normalized ends with ">" and (count of normalized) > 2 then set normalized to text 2 thru -2 of normalized
	return normalized
end normalizedMessageID

on indexedMessages(sourceMailbox, expectedMailID)
	tell application "Mail"
		try
			return messages of sourceMailbox whose id is expectedMailID
		on error errorMessage number errorNumber
			if errorNumber is -1719 then return {}
			error errorMessage number errorNumber
		end try
	end tell
end indexedMessages

on run argv
	if (count of argv) is not 6 then error "Expected source, identity, and body limit"
	set sourceMailbox to my resolveSource(item 1 of argv, item 2 of argv, item 3 of argv)
	set expectedMailID to item 4 of argv as integer
	set expectedMessageID to my normalizedMessageID(item 5 of argv)
	set bodyLimit to item 6 of argv as integer
	if bodyLimit < 0 or bodyLimit > 100000 then error "Body limit is outside the supported range"
	tell application "Mail"
		set sourceMatches to my indexedMessages(sourceMailbox, expectedMailID)
		if (count of sourceMatches) is not 1 then error "Expected one indexed source match"
		set targetMessage to item 1 of sourceMatches
		if my normalizedMessageID(«class meid» of targetMessage) is not expectedMessageID then error "Indexed source identity check failed"
		set bodyText to content of targetMessage as text
		set bodyWasTruncated to false
		if (count of bodyText) > bodyLimit then
			if bodyLimit is 0 then
				set bodyText to ""
			else
				set bodyText to text 1 thru bodyLimit of bodyText
			end if
			set bodyWasTruncated to true
		end if
		set attachmentCount to -1
		try
		set attachmentCount to count of «class attc» of targetMessage
		end try
		set outputLine to "MESSAGE" & tab & (id of targetMessage as text) & tab & my escapeField(«class meid» of targetMessage) & tab & my escapeField(subject of targetMessage) & tab & my escapeField(sender of targetMessage) & tab & («class isrd» of targetMessage as text) & tab & attachmentCount & tab & (bodyWasTruncated as text) & tab & my escapeField(bodyText)
	end tell
	return "TYPE" & tab & "MAIL_ID" & tab & "MESSAGE_ID" & tab & "SUBJECT" & tab & "SENDER" & tab & "READ" & tab & "ATTACHMENT_COUNT" & tab & "BODY_TRUNCATED" & tab & "BODY" & linefeed & outputLine
end run
