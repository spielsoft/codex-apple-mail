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

on pad2(theNumber)
	set valueText to theNumber as text
	if (count of valueText) is 1 then return "0" & valueText
	return valueText
end pad2

on isoDate(theDate)
	return ((year of theDate as integer) as text) & "-" & my pad2(month of theDate as integer) & "-" & my pad2(day of theDate as integer) & "T" & my pad2(hours of theDate) & ":" & my pad2(minutes of theDate) & ":" & my pad2(seconds of theDate)
end isoDate

on beginsWith(theText, prefixText)
	if prefixText is "" then return true
	if (count of theText) < (count of prefixText) then return false
	return text 1 thru (count of prefixText) of theText is prefixText
end beginsWith

on normalizedMessageID(theText)
	set normalized to theText as text
	if normalized begins with "<" and normalized ends with ">" and (count of normalized) > 2 then set normalized to text 2 thru -2 of normalized
	return normalized
end normalizedMessageID

on normalizedSender(theText)
	set senderText to theText as text
	set quoteMarker to quote & " <"
	if senderText begins with quote then
		set quotePosition to offset of quoteMarker in senderText
		if quotePosition > 1 then
			return (text 2 thru (quotePosition - 1) of senderText) & (text (quotePosition + 1) thru -1 of senderText)
		end if
	end if
	return senderText
end normalizedSender

on textMatches(leftValue, rightValue)
	set leftText to leftValue as text
	set rightText to rightValue as text
	if (count of leftText) is not (count of rightText) then return false
	repeat with characterIndex from 1 to count of leftText
		if (id of character characterIndex of leftText) is not (id of character characterIndex of rightText) then return false
	end repeat
	return true
end textMatches

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

on identityMatches(theMessage, expectedMessageID, expectedSubject, expectedSender, datePrefix, expectedRead)
	tell application "Mail"
		set actualMessageID to my normalizedMessageID(«class meid» of theMessage)
		set actualSubject to (get subject of theMessage) as text
		set actualSender to (get sender of theMessage) as text
		if not my textMatches(actualMessageID, my normalizedMessageID(expectedMessageID)) then return false
		if not my textMatches(actualSubject, expectedSubject as text) then return false
		if expectedSender is not "" and not my textMatches(my normalizedSender(actualSender), my normalizedSender(expectedSender)) then return false
		if not my beginsWith(my isoDate(«class rdrc» of theMessage), datePrefix) then return false
		if («class isrd» of theMessage as text) is not expectedRead then return false
	end tell
	return true
end identityMatches

on run argv
	if (count of argv) < 10 then error "Insufficient arguments"
	if ((count of argv) - 4) mod 6 is not 0 then error "Message arguments must be groups of six"
	set sourceMailbox to my resolveSource(item 1 of argv, item 2 of argv, item 3 of argv)
	set bodyLimit to item 4 of argv as integer
	if bodyLimit < 0 or bodyLimit > 100000 then error "Body limit is outside the supported range"
	set itemCount to ((count of argv) - 4) div 6
	if itemCount < 1 or itemCount > 50 then error "Body batch size is outside the supported range"
	set targetMessages to {}

	repeat with itemNumber from 1 to itemCount
		set argumentOffset to 5 + ((itemNumber - 1) * 6)
		set expectedMailID to item argumentOffset of argv as integer
		set expectedMessageID to item (argumentOffset + 1) of argv
		set expectedSubject to item (argumentOffset + 2) of argv
		set expectedSender to item (argumentOffset + 3) of argv
		set datePrefix to item (argumentOffset + 4) of argv
		set expectedRead to item (argumentOffset + 5) of argv
		set sourceMatches to my indexedMessages(sourceMailbox, expectedMailID)
		if (count of sourceMatches) is not 1 then error "Expected one indexed source match"
		set targetMessage to item 1 of sourceMatches
		if not my identityMatches(targetMessage, expectedMessageID, expectedSubject, expectedSender, datePrefix, expectedRead) then error "Indexed source identity check failed"
		set end of targetMessages to targetMessage
	end repeat

	set outputLines to {"TYPE" & tab & "MAIL_ID" & tab & "MESSAGE_ID" & tab & "SUBJECT" & tab & "SENDER" & tab & "READ" & tab & "ATTACHMENT_COUNT" & tab & "BODY_TRUNCATED" & tab & "BODY"}
	tell application "Mail"
		repeat with itemNumber from 1 to itemCount
			set targetMessage to item itemNumber of targetMessages
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
			set end of outputLines to outputLine
		end repeat
	end tell
	set AppleScript's text item delimiters to linefeed
	set outputText to outputLines as text
	set AppleScript's text item delimiters to ""
	return outputText
end run
