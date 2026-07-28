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

on resolveSource(sourceKind, sourceName, sourcePath)
	if sourceKind is "local" then return my resolveLocalMailbox(sourcePath)
	if sourceKind is not "account" then error "Unsupported source kind"
	tell application "Mail"
		if not (exists account (sourceName as text)) then error "Account not found: " & sourceName
		set sourceAccount to account (sourceName as text)
		if not (exists mailbox (sourcePath as text) of sourceAccount) then error "Account mailbox not found: " & sourcePath
		return mailbox (sourcePath as text) of sourceAccount
	end tell
end resolveSource

on identityMatches(theMessage, expectedMessageID, expectedSubject, expectedSender, datePrefix)
	tell application "Mail"
		if my normalizedMessageID(«class meid» of theMessage) is not my normalizedMessageID(expectedMessageID) then return false
		if subject of theMessage is not expectedSubject then return false
		if expectedSender is not "" and sender of theMessage is not expectedSender then return false
		if not my beginsWith(my isoDate(«class rdrc» of theMessage), datePrefix) then return false
	end tell
	return true
end identityMatches

on run argv
	if (count of argv) < 11 then error "Insufficient arguments"
	if ((count of argv) - 5) mod 6 is not 0 then error "Message arguments must be groups of six"
	set sourceKind to item 1 of argv
	set sourceName to item 2 of argv
	set sourcePath to item 3 of argv
	set destinationKind to item 4 of argv
	set destinationPath to item 5 of argv
	set itemCount to ((count of argv) - 5) div 6
	if itemCount < 1 or itemCount > 250 then error "Batch size is outside the supported range"
	set sourceMailbox to my resolveSource(sourceKind, sourceName, sourcePath)
	set destinationMessages to {}
	if destinationKind is "local" then
		set destinationMailbox to my resolveLocalMailbox(destinationPath)
		tell application "Mail" to set destinationMessages to messages of destinationMailbox
	else if destinationKind is not "none" then
		error "Unsupported destination kind"
	end if
	set outputLines to {"MAIL_ID" & tab & "MESSAGE_ID" & tab & "SOURCE_ID_COUNT" & tab & "SOURCE_IDENTITY" & tab & "SOURCE_READ" & tab & "DESTINATION_COUNT" & tab & "DESTINATION_READ"}
	tell application "Mail"
		repeat with itemNumber from 1 to itemCount
			set offset to 6 + ((itemNumber - 1) * 6)
			set expectedMailID to item offset of argv as integer
			set expectedMessageID to item (offset + 1) of argv
			set expectedSubject to item (offset + 2) of argv
			set expectedSender to item (offset + 3) of argv
			set datePrefix to item (offset + 4) of argv
			set expectedRead to item (offset + 5) of argv
			set sourceMatches to messages of sourceMailbox whose id is expectedMailID
			set sourceIdentity to false
			set sourceRead to ""
			if (count of sourceMatches) is 1 then
				set sourceMessage to item 1 of sourceMatches
				set sourceIdentity to my identityMatches(sourceMessage, expectedMessageID, expectedSubject, expectedSender, datePrefix)
					set sourceRead to «class isrd» of sourceMessage as text
			end if
			set destinationCount to 0
			set destinationRead to ""
			repeat with destinationReference in destinationMessages
				set destinationMessage to contents of destinationReference
				if my identityMatches(destinationMessage, expectedMessageID, expectedSubject, expectedSender, datePrefix) then
					set destinationCount to destinationCount + 1
					set destinationRead to «class isrd» of destinationMessage as text
				end if
			end repeat
			set end of outputLines to (expectedMailID as text) & tab & expectedMessageID & tab & ((count of sourceMatches) as text) & tab & (sourceIdentity as text) & tab & sourceRead & tab & (destinationCount as text) & tab & destinationRead
		end repeat
	end tell
	set AppleScript's text item delimiters to linefeed
	set outputText to outputLines as text
	set AppleScript's text item delimiters to ""
	return outputText
end run
