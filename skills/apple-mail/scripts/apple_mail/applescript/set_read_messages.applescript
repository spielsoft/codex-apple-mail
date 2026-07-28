on beginsWith(theText, prefixText)
	if prefixText is "" then return true
	if (count of theText) < (count of prefixText) then return false
	return text 1 thru (count of prefixText) of theText is prefixText
end beginsWith

on pad2(theNumber)
	set valueText to theNumber as text
	if (count of valueText) is 1 then return "0" & valueText
	return valueText
end pad2

on isoDate(theDate)
	return ((year of theDate as integer) as text) & "-" & my pad2(month of theDate as integer) & "-" & my pad2(day of theDate as integer) & "T" & my pad2(hours of theDate) & ":" & my pad2(minutes of theDate) & ":" & my pad2(seconds of theDate)
end isoDate

on localPathParts(fullPath)
	if not my beginsWith(fullPath, "On My Mac/") then error "Local path must begin with On My Mac/"
	set relativePath to text 11 thru -1 of fullPath
	set AppleScript's text item delimiters to "/"
	set pathParts to every text item of relativePath
	set AppleScript's text item delimiters to ""
	return pathParts
end localPathParts

on resolveSource(sourceKind, sourceName, sourcePath)
	tell application "Mail"
		if sourceKind is "account" then
			if not (exists account (sourceName as text)) then error "Account not found"
			set sourceAccount to account (sourceName as text)
			if not (exists mailbox (sourcePath as text) of sourceAccount) then error "Account mailbox not found"
			return mailbox (sourcePath as text) of sourceAccount
		end if
		if sourceKind is not "local" then error "Unsupported source kind"
		set pathParts to my localPathParts(sourcePath)
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
	if (count of argv) < 10 then error "Insufficient arguments"
	if ((count of argv) - 4) mod 6 is not 0 then error "Message arguments must be groups of six"
	set sourceKind to item 1 of argv
	set sourceName to item 2 of argv
	set sourcePath to item 3 of argv
	set targetReadText to item 4 of argv
	if targetReadText is "true" then
		set targetRead to true
	else if targetReadText is "false" then
		set targetRead to false
	else
		error "Invalid target state"
	end if
	set itemCount to ((count of argv) - 4) div 6
	set sourceMailbox to my resolveSource(sourceKind, sourceName, sourcePath)
	tell application "Mail"
		set messagesToChange to {}
		repeat with itemNumber from 1 to itemCount
			set argumentOffset to 5 + ((itemNumber - 1) * 6)
			set expectedMailID to item argumentOffset of argv as integer
			set expectedMessageID to my normalizedMessageID(item (argumentOffset + 1) of argv)
			set expectedSubject to item (argumentOffset + 2) of argv
			set expectedSender to item (argumentOffset + 3) of argv
			set datePrefix to item (argumentOffset + 4) of argv
			set expectedRead to item (argumentOffset + 5) of argv
			set sourceMatches to my indexedMessages(sourceMailbox, expectedMailID)
			if (count of sourceMatches) is not 1 then error "Expected one indexed source match"
			set sourceMessage to item 1 of sourceMatches
			if not my textMatches(my normalizedMessageID(«class meid» of sourceMessage), expectedMessageID) then error "Indexed source identity check failed"
			set actualSubject to (get subject of sourceMessage) as text
			set actualSender to (get sender of sourceMessage) as text
			if not my textMatches(actualSubject, expectedSubject) then error "Indexed source subject check failed"
			if expectedSender is not "" and not my textMatches(my normalizedSender(actualSender), my normalizedSender(expectedSender)) then error "Indexed source originator check failed"
			if not my beginsWith(my isoDate(«class rdrc» of sourceMessage), datePrefix) then error "Indexed source date check failed"
			if («class isrd» of sourceMessage as text) is not expectedRead then error "Indexed source state check failed"
			set end of messagesToChange to sourceMessage
		end repeat
		repeat with messageReference in messagesToChange
			set «class isrd» of contents of messageReference to targetRead
		end repeat
	end tell
	return "STATUS" & tab & "COUNT" & linefeed & "CHANGED" & tab & (itemCount as text)
end run
