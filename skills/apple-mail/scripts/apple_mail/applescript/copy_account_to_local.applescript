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

on identityMatches(theMessage, expectedMessageID, expectedSubject, expectedSender, datePrefix, expectedRead)
	tell application "Mail"
		if my normalizedMessageID(«class meid» of theMessage) is not my normalizedMessageID(expectedMessageID) then return false
		if subject of theMessage is not expectedSubject then return false
		if expectedSender is not "" and sender of theMessage is not expectedSender then return false
		if not my beginsWith(my isoDate(«class rdrc» of theMessage), datePrefix) then return false
		if («class isrd» of theMessage as text) is not expectedRead then return false
	end tell
	return true
end identityMatches

on run argv
	if (count of argv) < 9 then error "Insufficient arguments"
	if ((count of argv) - 3) mod 6 is not 0 then error "Message arguments must be groups of six"
	set accountName to item 1 of argv
	set sourcePath to item 2 of argv
	set destinationPath to item 3 of argv
	set itemCount to ((count of argv) - 3) div 6
	if itemCount < 1 or itemCount > 250 then error "Batch size is outside the supported range"
	set destinationMailbox to my resolveLocalMailbox(destinationPath)
	tell application "Mail"
		if not (exists account (accountName as text)) then error "Account not found: " & accountName
		set sourceAccount to account (accountName as text)
		if not (exists mailbox (sourcePath as text) of sourceAccount) then error "Account mailbox not found: " & sourcePath
		set sourceMailbox to mailbox (sourcePath as text) of sourceAccount
		set destinationMessages to messages of destinationMailbox
		set messagesToCopy to {}
		set statuses to {}
		repeat with itemNumber from 1 to itemCount
			set argumentOffset to 4 + ((itemNumber - 1) * 6)
			set expectedMailID to item argumentOffset of argv as integer
			set expectedMessageID to item (argumentOffset + 1) of argv
			set expectedSubject to item (argumentOffset + 2) of argv
			set expectedSender to item (argumentOffset + 3) of argv
			set datePrefix to item (argumentOffset + 4) of argv
			set expectedRead to item (argumentOffset + 5) of argv
			set sourceMatches to messages of sourceMailbox whose id is expectedMailID
			if (count of sourceMatches) is not 1 then error "Expected one indexed source match"
			set sourceMessage to item 1 of sourceMatches
			if not my identityMatches(sourceMessage, expectedMessageID, expectedSubject, expectedSender, datePrefix, expectedRead) then error "Indexed source identity check failed"
			set destinationCount to 0
			repeat with destinationReference in destinationMessages
				if my identityMatches(contents of destinationReference, expectedMessageID, expectedSubject, expectedSender, datePrefix, expectedRead) then set destinationCount to destinationCount + 1
			end repeat
			if destinationCount > 1 then error "Destination identity is ambiguous"
			if destinationCount is 0 then
				set end of messagesToCopy to sourceMessage
				set end of statuses to "COPIED"
			else
				set end of statuses to "REUSED"
			end if
		end repeat
		if (count of messagesToCopy) > 0 then duplicate messagesToCopy to destinationMailbox
	end tell
	set outputLines to {"MAIL_ID" & tab & "STATUS"}
	repeat with itemNumber from 1 to itemCount
		set argumentOffset to 4 + ((itemNumber - 1) * 6)
		set end of outputLines to (item argumentOffset of argv) & tab & (item itemNumber of statuses)
	end repeat
	set AppleScript's text item delimiters to linefeed
	set outputText to outputLines as text
	set AppleScript's text item delimiters to ""
	return outputText
end run
