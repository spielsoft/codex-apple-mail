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

on normalizedMessageID(theText)
	set normalized to theText as text
	if normalized begins with "<" and normalized ends with ">" and (count of normalized) > 2 then set normalized to text 2 thru -2 of normalized
	return normalized
end normalizedMessageID

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
	set sourcePath to item 1 of argv
	set destinationPath to item 2 of argv
	set modeName to item 3 of argv
	if sourcePath is destinationPath then error "Source and destination must differ"
	if modeName is not "apply" then error "Invalid mode"
	set itemCount to ((count of argv) - 3) div 6
	if itemCount < 1 or itemCount > 250 then error "Batch size is outside the supported range"
	set sourceMailbox to my resolveLocalMailbox(sourcePath)
	set destinationMailbox to my resolveLocalMailbox(destinationPath)
	tell application "Mail"
		set messagesToMove to {}
		set destinationMessages to messages of destinationMailbox
		repeat with itemNumber from 1 to itemCount
			set argumentOffset to 4 + ((itemNumber - 1) * 6)
			set expectedMailID to item argumentOffset of argv as integer
			set expectedMessageID to my normalizedMessageID(item (argumentOffset + 1) of argv)
			set expectedSubject to item (argumentOffset + 2) of argv
			set expectedSender to item (argumentOffset + 3) of argv
			set datePrefix to item (argumentOffset + 4) of argv
			set expectedRead to item (argumentOffset + 5) of argv
			set sourceMatches to messages of sourceMailbox whose id is expectedMailID
			if (count of sourceMatches) is not 1 then error "Expected one indexed source match"
			set sourceMessage to item 1 of sourceMatches
			if my normalizedMessageID(«class meid» of sourceMessage) is not expectedMessageID then error "Indexed source identity check failed"
			if subject of sourceMessage is not expectedSubject then error "Indexed source subject check failed"
			if expectedSender is not "" and sender of sourceMessage is not expectedSender then error "Indexed source originator check failed"
			if not my beginsWith(my isoDate(«class rdrc» of sourceMessage), datePrefix) then error "Indexed source date check failed"
			if («class isrd» of sourceMessage as text) is not expectedRead then error "Indexed source state check failed"
			set destinationCount to 0
			repeat with destinationReference in destinationMessages
				if my identityMatches(contents of destinationReference, item (argumentOffset + 1) of argv, expectedSubject, expectedSender, datePrefix, expectedRead) then set destinationCount to destinationCount + 1
			end repeat
			if destinationCount is not 0 then error "Destination identity already exists"
			set end of messagesToMove to sourceMessage
		end repeat
		move messagesToMove to destinationMailbox
	end tell
	return "STATUS" & tab & "COUNT" & linefeed & "MOVED" & tab & (itemCount as text)
end run
