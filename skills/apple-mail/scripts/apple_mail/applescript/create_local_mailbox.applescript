on beginsWith(theText, prefixText)
	if prefixText is "" then return true
	if (count of theText) < (count of prefixText) then return false
	return text 1 thru (count of prefixText) of theText is prefixText
end beginsWith

on run argv
	if (count of argv) is not 1 then error "Expected one mailbox path"
	set fullPath to item 1 of argv
	if not my beginsWith(fullPath, "On My Mac/") then error "Local path must begin with On My Mac/"
	set relativePath to text 11 thru -1 of fullPath
	set AppleScript's text item delimiters to "/"
	set pathParts to every text item of relativePath
	set AppleScript's text item delimiters to ""
	repeat with partReference in pathParts
		set partText to contents of partReference
		if partText is "" or partText is "." or partText is ".." then error "Invalid local path"
	end repeat
	tell application "Mail"
		if (count of pathParts) is 1 then
			set leafName to item 1 of pathParts
			if exists mailbox (leafName as text) then
				set statusName to "EXISTS"
			else
				make new mailbox with properties {name:leafName}
				set statusName to "CREATED"
			end if
		else
			set parentName to item 1 of pathParts
			if not (exists mailbox (parentName as text)) then error "Parent mailbox not found"
			set parentMailbox to mailbox (parentName as text)
			repeat with partIndex from 2 to ((count of pathParts) - 1)
				set childName to item partIndex of pathParts
				if not (exists mailbox (childName as text) of parentMailbox) then error "Parent mailbox not found"
				set parentMailbox to mailbox (childName as text) of parentMailbox
			end repeat
			set leafName to item -1 of pathParts
			if exists mailbox (leafName as text) of parentMailbox then
				set statusName to "EXISTS"
			else
				make new mailbox at parentMailbox with properties {name:leafName}
				set statusName to "CREATED"
			end if
		end if
	end tell
	return "STATUS" & tab & "PATH" & linefeed & statusName & tab & fullPath
end run
