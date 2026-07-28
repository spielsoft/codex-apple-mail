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
	if theDate is missing value then return ""
	return ((year of theDate as integer) as text) & "-" & my pad2(month of theDate as integer) & "-" & my pad2(day of theDate as integer) & "T" & my pad2(hours of theDate) & ":" & my pad2(minutes of theDate) & ":" & my pad2(seconds of theDate)
end isoDate

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

on run argv
	if (count of argv) is not 5 then error "Expected source, start, and limit"
	set sourceKind to item 1 of argv
	set sourceName to item 2 of argv
	set sourcePath to item 3 of argv
	set startIndex to item 4 of argv as integer
	set batchLimit to item 5 of argv as integer
	if startIndex < 1 then error "Start must be positive"
	if batchLimit < 1 or batchLimit > 250 then error "Limit is outside the supported range"
	set sourceMailbox to my resolveSource(sourceKind, sourceName, sourcePath)
	set outputLines to {"TYPE" & tab & "SEQUENCE" & tab & "MAIL_ID" & tab & "MESSAGE_ID" & tab & "SUBJECT" & tab & "SENDER" & tab & "DATE_SENT" & tab & "DATE_RECEIVED" & tab & "READ" & tab & "FLAGGED" & tab & "JUNK" & tab & "SIZE"}
	tell application "Mail"
		set totalMessages to count of messages of sourceMailbox
		if startIndex <= totalMessages then
			set endIndex to startIndex + batchLimit - 1
			if endIndex > totalMessages then set endIndex to totalMessages
			repeat with messageIndex from startIndex to endIndex
				set theMessage to item messageIndex of messages of sourceMailbox
				set messageLine to "MESSAGE" & tab & messageIndex & tab & (id of theMessage as text)
				set messageLine to messageLine & tab & my escapeField(«class meid» of theMessage)
				set messageLine to messageLine & tab & my escapeField(subject of theMessage)
				set messageLine to messageLine & tab & my escapeField(sender of theMessage)
				set messageLine to messageLine & tab & my isoDate(«class drcv» of theMessage)
				set messageLine to messageLine & tab & my isoDate(«class rdrc» of theMessage)
				set messageLine to messageLine & tab & («class isrd» of theMessage as text)
				set messageLine to messageLine & tab & («class isfl» of theMessage as text)
				set messageLine to messageLine & tab & («class isjk» of theMessage as text)
				set messageLine to messageLine & tab & («class msze» of theMessage as text)
				set end of outputLines to messageLine
			end repeat
		end if
		set end of outputLines to "SUMMARY" & tab & startIndex & tab & totalMessages
	end tell
	set AppleScript's text item delimiters to linefeed
	set outputText to outputLines as text
	set AppleScript's text item delimiters to ""
	return outputText
end run
