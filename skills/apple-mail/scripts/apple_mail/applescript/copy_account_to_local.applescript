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

on localPathParts(fullPath)
	if not my beginsWith(fullPath, "On My Mac/") then error "Local path must begin with On My Mac/"
	set relativePath to text 11 thru -1 of fullPath
	set AppleScript's text item delimiters to "/"
	set pathParts to every text item of relativePath
	set AppleScript's text item delimiters to ""
	repeat with partReference in pathParts
		set partText to contents of partReference
		if partText is "" or partText is "." or partText is ".." then error "Invalid local path"
	end repeat
	return pathParts
end localPathParts

on resolveLocalMailbox(fullPath)
	set pathParts to my localPathParts(fullPath)
	tell application "Mail"
		set rootName to item 1 of pathParts
		if not (exists mailbox (rootName as text)) then error "Local mailbox not found: " & fullPath
		set resolvedMailbox to mailbox (rootName as text)
		repeat with partIndex from 2 to count of pathParts
			set childName to item partIndex of pathParts
			if not (exists mailbox (childName as text) of resolvedMailbox) then error "Local mailbox not found: " & fullPath
			set resolvedMailbox to mailbox (childName as text) of resolvedMailbox
		end repeat
	end tell
	return resolvedMailbox
end resolveLocalMailbox

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

on destinationSnapshot(destinationMailbox)
	set destinationMessages to {}
	set destinationMessageIDs to {}
	tell application "Mail"
		set destinationMessages to messages of destinationMailbox
		repeat with destinationReference in destinationMessages
			set end of destinationMessageIDs to «class meid» of (contents of destinationReference) as text
		end repeat
	end tell
	return {destinationMessages, destinationMessageIDs}
end destinationSnapshot

on destinationState(destinationMessages, destinationMessageIDs, expectedMessageID, expectedSubject, expectedSender, datePrefix, expectedRead)
	set normalizedExpectedID to my normalizedMessageID(expectedMessageID)
	set destinationCount to 0
	set destinationRead to ""
	set candidateCount to 0
	repeat with destinationIndex from 1 to count of destinationMessageIDs
		if my textMatches(my normalizedMessageID(item destinationIndex of destinationMessageIDs), normalizedExpectedID) then
			set candidateCount to candidateCount + 1
			set destinationMessage to item destinationIndex of destinationMessages
			if my identityMatches(destinationMessage, expectedMessageID, expectedSubject, expectedSender, datePrefix, expectedRead) then
				set destinationCount to destinationCount + 1
				tell application "Mail" to set destinationRead to «class isrd» of destinationMessage as text
			end if
		end if
	end repeat
	if candidateCount is not destinationCount then error "Destination message-id collision"
	if destinationCount > 1 then error "Destination identity is ambiguous"
	return {destinationCount, destinationRead}
end destinationState

on probeResult(itemCount, copyCount, reusedCount, selectorCount)
	set probeReady to selectorCount is copyCount and (copyCount + reusedCount) is itemCount
	return "MODE" & tab & "ITEM_COUNT" & tab & "COPY_COUNT" & tab & "REUSED_COUNT" & tab & "MISSING_COPY_COUNT" & tab & "SOURCE_SELECTOR_COUNT" & tab & "SOURCE_RESOLVED" & tab & "DESTINATION_RESOLVED" & tab & "READY" & linefeed & "probe" & tab & (itemCount as text) & tab & (copyCount as text) & tab & (reusedCount as text) & tab & (copyCount as text) & tab & (selectorCount as text) & tab & "true" & tab & "true" & tab & (probeReady as text)
end probeResult

on run argv
	if (count of argv) < 10 then error "Insufficient arguments"
	if ((count of argv) - 4) mod 6 is not 0 then error "Message arguments must be groups of six"
	set operationMode to item 1 of argv
	if operationMode is not "apply" and operationMode is not "probe" then error "Unsupported operation mode"
	set accountName to item 2 of argv
	set sourcePath to item 3 of argv
	set destinationPath to item 4 of argv
	set itemCount to ((count of argv) - 4) div 6
	if itemCount < 1 or itemCount > 10 then error "Gmail transfer batch size is outside the supported range"
	set destinationMailbox to my resolveLocalMailbox(destinationPath)
	tell application "Mail"
		if not (exists account (accountName as text)) then error "Account not found: " & accountName
		set sourceAccount to account (accountName as text)
		if not (exists mailbox (sourcePath as text) of sourceAccount) then error "Account mailbox not found: " & sourcePath
		set sourceMailbox to mailbox (sourcePath as text) of sourceAccount
	end tell

	set initialDestination to my destinationSnapshot(destinationMailbox)
	set destinationMessages to item 1 of initialDestination
	set destinationMessageIDs to item 2 of initialDestination
	set mailIDsToCopy to {}
	set statuses to {}
	set reusedCount to 0
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
		set sourceMessage to item 1 of sourceMatches
		if not my identityMatches(sourceMessage, expectedMessageID, expectedSubject, expectedSender, datePrefix, expectedRead) then error "Indexed source identity check failed"
		set destinationResult to my destinationState(destinationMessages, destinationMessageIDs, expectedMessageID, expectedSubject, expectedSender, datePrefix, expectedRead)
		set destinationCount to item 1 of destinationResult
		if destinationCount is 0 then
			set end of mailIDsToCopy to expectedMailID
			set end of statuses to "COPIED"
		else
			set reusedCount to reusedCount + 1
			set end of statuses to "REUSED"
		end if
	end repeat

	set copyCount to count of mailIDsToCopy
	set bulkSourceCount to 0
	if copyCount > 0 then
		set selectorMailIDs to {} & mailIDsToCopy
		repeat while (count of selectorMailIDs) < 10
			set end of selectorMailIDs to -1
		end repeat
		set {selectorMailID01, selectorMailID02, selectorMailID03, selectorMailID04, selectorMailID05, selectorMailID06, selectorMailID07, selectorMailID08, selectorMailID09, selectorMailID10} to selectorMailIDs
		tell application "Mail"
			set bulkSourceCount to count of (messages of sourceMailbox whose id is selectorMailID01 or id is selectorMailID02 or id is selectorMailID03 or id is selectorMailID04 or id is selectorMailID05 or id is selectorMailID06 or id is selectorMailID07 or id is selectorMailID08 or id is selectorMailID09 or id is selectorMailID10)
		end tell
	end if
	if operationMode is "probe" then return my probeResult(itemCount, copyCount, reusedCount, bulkSourceCount)
	if bulkSourceCount is not copyCount then error "Bulk source selector count mismatch: expected " & (copyCount as text) & ", got " & (bulkSourceCount as text)
	if copyCount > 0 then
		tell application "Mail"
			duplicate (messages of sourceMailbox whose id is selectorMailID01 or id is selectorMailID02 or id is selectorMailID03 or id is selectorMailID04 or id is selectorMailID05 or id is selectorMailID06 or id is selectorMailID07 or id is selectorMailID08 or id is selectorMailID09 or id is selectorMailID10) to destinationMailbox
		end tell
	end if

	set finalDestination to my destinationSnapshot(destinationMailbox)
	set destinationMessages to item 1 of finalDestination
	set destinationMessageIDs to item 2 of finalDestination
	set outputLines to {"MAIL_ID" & tab & "STATUS" & tab & "DESTINATION_COUNT" & tab & "DESTINATION_READ" & tab & "DESTINATION_IDENTITY"}
	repeat with itemNumber from 1 to itemCount
		set argumentOffset to 5 + ((itemNumber - 1) * 6)
		set expectedMailID to item argumentOffset of argv as integer
		set expectedMessageID to item (argumentOffset + 1) of argv
		set expectedSubject to item (argumentOffset + 2) of argv
		set expectedSender to item (argumentOffset + 3) of argv
		set datePrefix to item (argumentOffset + 4) of argv
		set expectedRead to item (argumentOffset + 5) of argv
		set destinationResult to my destinationState(destinationMessages, destinationMessageIDs, expectedMessageID, expectedSubject, expectedSender, datePrefix, expectedRead)
		set destinationCount to item 1 of destinationResult
		set destinationRead to item 2 of destinationResult
		set destinationIdentity to destinationCount is 1 and destinationRead is expectedRead
		set end of outputLines to (expectedMailID as text) & tab & (item itemNumber of statuses) & tab & (destinationCount as text) & tab & destinationRead & tab & (destinationIdentity as text)
	end repeat
	set AppleScript's text item delimiters to linefeed
	set outputText to outputLines as text
	set AppleScript's text item delimiters to ""
	return outputText
end run
