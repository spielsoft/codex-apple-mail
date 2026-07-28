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

on identityMatchFields(theMessage, expectedMessageID, expectedSubject, expectedSender, datePrefix)
	tell application "Mail"
		set actualMessageID to my normalizedMessageID(«class meid» of theMessage)
		set actualSubject to (get subject of theMessage) as text
		set actualSender to (get sender of theMessage) as text
		set actualReceivedAt to my isoDate(«class rdrc» of theMessage)
	end tell
	set expectedMessageIDText to my normalizedMessageID(expectedMessageID)
	set expectedSubjectText to expectedSubject as text
	set expectedSenderText to expectedSender as text
	set messageIDMatch to my textMatches(actualMessageID, expectedMessageIDText)
	set subjectMatch to my textMatches(actualSubject, expectedSubjectText)
	set senderMatch to expectedSenderText is "" or my textMatches(my normalizedSender(actualSender), my normalizedSender(expectedSenderText))
	set receivedAtMatch to my beginsWith(actualReceivedAt, datePrefix)
	return {messageIDMatch, subjectMatch, senderMatch, receivedAtMatch}
end identityMatchFields

on allIdentityFieldsMatch(fieldMatches)
	return item 1 of fieldMatches and item 2 of fieldMatches and item 3 of fieldMatches and item 4 of fieldMatches
end allIdentityFieldsMatch

on identityMatches(theMessage, expectedMessageID, expectedSubject, expectedSender, datePrefix)
	return my allIdentityFieldsMatch(my identityMatchFields(theMessage, expectedMessageID, expectedSubject, expectedSender, datePrefix))
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
	set expectedMailIDs to {}
	repeat with itemNumber from 1 to itemCount
		set argumentOffset to 6 + ((itemNumber - 1) * 6)
		set end of expectedMailIDs to item argumentOffset of argv as integer
	end repeat
	set selectorMailIDs to {} & expectedMailIDs
	repeat while (count of selectorMailIDs) < 250
		set end of selectorMailIDs to -1
	end repeat
	set {selectorMailID001, selectorMailID002, selectorMailID003, selectorMailID004, selectorMailID005, selectorMailID006, selectorMailID007, selectorMailID008, selectorMailID009, selectorMailID010, selectorMailID011, selectorMailID012, selectorMailID013, selectorMailID014, selectorMailID015, selectorMailID016, selectorMailID017, selectorMailID018, selectorMailID019, selectorMailID020, selectorMailID021, selectorMailID022, selectorMailID023, selectorMailID024, selectorMailID025, selectorMailID026, selectorMailID027, selectorMailID028, selectorMailID029, selectorMailID030, selectorMailID031, selectorMailID032, selectorMailID033, selectorMailID034, selectorMailID035, selectorMailID036, selectorMailID037, selectorMailID038, selectorMailID039, selectorMailID040, selectorMailID041, selectorMailID042, selectorMailID043, selectorMailID044, selectorMailID045, selectorMailID046, selectorMailID047, selectorMailID048, selectorMailID049, selectorMailID050, selectorMailID051, selectorMailID052, selectorMailID053, selectorMailID054, selectorMailID055, selectorMailID056, selectorMailID057, selectorMailID058, selectorMailID059, selectorMailID060, selectorMailID061, selectorMailID062, selectorMailID063, selectorMailID064, selectorMailID065, selectorMailID066, selectorMailID067, selectorMailID068, selectorMailID069, selectorMailID070, selectorMailID071, selectorMailID072, selectorMailID073, selectorMailID074, selectorMailID075, selectorMailID076, selectorMailID077, selectorMailID078, selectorMailID079, selectorMailID080, selectorMailID081, selectorMailID082, selectorMailID083, selectorMailID084, selectorMailID085, selectorMailID086, selectorMailID087, selectorMailID088, selectorMailID089, selectorMailID090, selectorMailID091, selectorMailID092, selectorMailID093, selectorMailID094, selectorMailID095, selectorMailID096, selectorMailID097, selectorMailID098, selectorMailID099, selectorMailID100, selectorMailID101, selectorMailID102, selectorMailID103, selectorMailID104, selectorMailID105, selectorMailID106, selectorMailID107, selectorMailID108, selectorMailID109, selectorMailID110, selectorMailID111, selectorMailID112, selectorMailID113, selectorMailID114, selectorMailID115, selectorMailID116, selectorMailID117, selectorMailID118, selectorMailID119, selectorMailID120, selectorMailID121, selectorMailID122, selectorMailID123, selectorMailID124, selectorMailID125, selectorMailID126, selectorMailID127, selectorMailID128, selectorMailID129, selectorMailID130, selectorMailID131, selectorMailID132, selectorMailID133, selectorMailID134, selectorMailID135, selectorMailID136, selectorMailID137, selectorMailID138, selectorMailID139, selectorMailID140, selectorMailID141, selectorMailID142, selectorMailID143, selectorMailID144, selectorMailID145, selectorMailID146, selectorMailID147, selectorMailID148, selectorMailID149, selectorMailID150, selectorMailID151, selectorMailID152, selectorMailID153, selectorMailID154, selectorMailID155, selectorMailID156, selectorMailID157, selectorMailID158, selectorMailID159, selectorMailID160, selectorMailID161, selectorMailID162, selectorMailID163, selectorMailID164, selectorMailID165, selectorMailID166, selectorMailID167, selectorMailID168, selectorMailID169, selectorMailID170, selectorMailID171, selectorMailID172, selectorMailID173, selectorMailID174, selectorMailID175, selectorMailID176, selectorMailID177, selectorMailID178, selectorMailID179, selectorMailID180, selectorMailID181, selectorMailID182, selectorMailID183, selectorMailID184, selectorMailID185, selectorMailID186, selectorMailID187, selectorMailID188, selectorMailID189, selectorMailID190, selectorMailID191, selectorMailID192, selectorMailID193, selectorMailID194, selectorMailID195, selectorMailID196, selectorMailID197, selectorMailID198, selectorMailID199, selectorMailID200, selectorMailID201, selectorMailID202, selectorMailID203, selectorMailID204, selectorMailID205, selectorMailID206, selectorMailID207, selectorMailID208, selectorMailID209, selectorMailID210, selectorMailID211, selectorMailID212, selectorMailID213, selectorMailID214, selectorMailID215, selectorMailID216, selectorMailID217, selectorMailID218, selectorMailID219, selectorMailID220, selectorMailID221, selectorMailID222, selectorMailID223, selectorMailID224, selectorMailID225, selectorMailID226, selectorMailID227, selectorMailID228, selectorMailID229, selectorMailID230, selectorMailID231, selectorMailID232, selectorMailID233, selectorMailID234, selectorMailID235, selectorMailID236, selectorMailID237, selectorMailID238, selectorMailID239, selectorMailID240, selectorMailID241, selectorMailID242, selectorMailID243, selectorMailID244, selectorMailID245, selectorMailID246, selectorMailID247, selectorMailID248, selectorMailID249, selectorMailID250} to selectorMailIDs
	set destinationMessages to {}
	if destinationKind is "local" then
		set destinationMailbox to my resolveLocalMailbox(destinationPath)
		tell application "Mail" to set destinationMessages to messages of destinationMailbox
	else if destinationKind is not "none" then
		error "Unsupported destination kind"
	end if
	set outputLines to {"MAIL_ID" & tab & "MESSAGE_ID" & tab & "SOURCE_ID_COUNT" & tab & "SOURCE_BULK_COUNT" & tab & "SOURCE_IDENTITY" & tab & "SOURCE_MESSAGE_ID_MATCH" & tab & "SOURCE_SUBJECT_MATCH" & tab & "SOURCE_SENDER_MATCH" & tab & "SOURCE_RECEIVED_AT_MATCH" & tab & "SOURCE_READ" & tab & "DESTINATION_COUNT" & tab & "DESTINATION_READ"}
	tell application "Mail"
		set sourceBulkCount to count of (messages of sourceMailbox whose id is selectorMailID001 or id is selectorMailID002 or id is selectorMailID003 or id is selectorMailID004 or id is selectorMailID005 or id is selectorMailID006 or id is selectorMailID007 or id is selectorMailID008 or id is selectorMailID009 or id is selectorMailID010 or id is selectorMailID011 or id is selectorMailID012 or id is selectorMailID013 or id is selectorMailID014 or id is selectorMailID015 or id is selectorMailID016 or id is selectorMailID017 or id is selectorMailID018 or id is selectorMailID019 or id is selectorMailID020 or id is selectorMailID021 or id is selectorMailID022 or id is selectorMailID023 or id is selectorMailID024 or id is selectorMailID025 or id is selectorMailID026 or id is selectorMailID027 or id is selectorMailID028 or id is selectorMailID029 or id is selectorMailID030 or id is selectorMailID031 or id is selectorMailID032 or id is selectorMailID033 or id is selectorMailID034 or id is selectorMailID035 or id is selectorMailID036 or id is selectorMailID037 or id is selectorMailID038 or id is selectorMailID039 or id is selectorMailID040 or id is selectorMailID041 or id is selectorMailID042 or id is selectorMailID043 or id is selectorMailID044 or id is selectorMailID045 or id is selectorMailID046 or id is selectorMailID047 or id is selectorMailID048 or id is selectorMailID049 or id is selectorMailID050 or id is selectorMailID051 or id is selectorMailID052 or id is selectorMailID053 or id is selectorMailID054 or id is selectorMailID055 or id is selectorMailID056 or id is selectorMailID057 or id is selectorMailID058 or id is selectorMailID059 or id is selectorMailID060 or id is selectorMailID061 or id is selectorMailID062 or id is selectorMailID063 or id is selectorMailID064 or id is selectorMailID065 or id is selectorMailID066 or id is selectorMailID067 or id is selectorMailID068 or id is selectorMailID069 or id is selectorMailID070 or id is selectorMailID071 or id is selectorMailID072 or id is selectorMailID073 or id is selectorMailID074 or id is selectorMailID075 or id is selectorMailID076 or id is selectorMailID077 or id is selectorMailID078 or id is selectorMailID079 or id is selectorMailID080 or id is selectorMailID081 or id is selectorMailID082 or id is selectorMailID083 or id is selectorMailID084 or id is selectorMailID085 or id is selectorMailID086 or id is selectorMailID087 or id is selectorMailID088 or id is selectorMailID089 or id is selectorMailID090 or id is selectorMailID091 or id is selectorMailID092 or id is selectorMailID093 or id is selectorMailID094 or id is selectorMailID095 or id is selectorMailID096 or id is selectorMailID097 or id is selectorMailID098 or id is selectorMailID099 or id is selectorMailID100 or id is selectorMailID101 or id is selectorMailID102 or id is selectorMailID103 or id is selectorMailID104 or id is selectorMailID105 or id is selectorMailID106 or id is selectorMailID107 or id is selectorMailID108 or id is selectorMailID109 or id is selectorMailID110 or id is selectorMailID111 or id is selectorMailID112 or id is selectorMailID113 or id is selectorMailID114 or id is selectorMailID115 or id is selectorMailID116 or id is selectorMailID117 or id is selectorMailID118 or id is selectorMailID119 or id is selectorMailID120 or id is selectorMailID121 or id is selectorMailID122 or id is selectorMailID123 or id is selectorMailID124 or id is selectorMailID125 or id is selectorMailID126 or id is selectorMailID127 or id is selectorMailID128 or id is selectorMailID129 or id is selectorMailID130 or id is selectorMailID131 or id is selectorMailID132 or id is selectorMailID133 or id is selectorMailID134 or id is selectorMailID135 or id is selectorMailID136 or id is selectorMailID137 or id is selectorMailID138 or id is selectorMailID139 or id is selectorMailID140 or id is selectorMailID141 or id is selectorMailID142 or id is selectorMailID143 or id is selectorMailID144 or id is selectorMailID145 or id is selectorMailID146 or id is selectorMailID147 or id is selectorMailID148 or id is selectorMailID149 or id is selectorMailID150 or id is selectorMailID151 or id is selectorMailID152 or id is selectorMailID153 or id is selectorMailID154 or id is selectorMailID155 or id is selectorMailID156 or id is selectorMailID157 or id is selectorMailID158 or id is selectorMailID159 or id is selectorMailID160 or id is selectorMailID161 or id is selectorMailID162 or id is selectorMailID163 or id is selectorMailID164 or id is selectorMailID165 or id is selectorMailID166 or id is selectorMailID167 or id is selectorMailID168 or id is selectorMailID169 or id is selectorMailID170 or id is selectorMailID171 or id is selectorMailID172 or id is selectorMailID173 or id is selectorMailID174 or id is selectorMailID175 or id is selectorMailID176 or id is selectorMailID177 or id is selectorMailID178 or id is selectorMailID179 or id is selectorMailID180 or id is selectorMailID181 or id is selectorMailID182 or id is selectorMailID183 or id is selectorMailID184 or id is selectorMailID185 or id is selectorMailID186 or id is selectorMailID187 or id is selectorMailID188 or id is selectorMailID189 or id is selectorMailID190 or id is selectorMailID191 or id is selectorMailID192 or id is selectorMailID193 or id is selectorMailID194 or id is selectorMailID195 or id is selectorMailID196 or id is selectorMailID197 or id is selectorMailID198 or id is selectorMailID199 or id is selectorMailID200 or id is selectorMailID201 or id is selectorMailID202 or id is selectorMailID203 or id is selectorMailID204 or id is selectorMailID205 or id is selectorMailID206 or id is selectorMailID207 or id is selectorMailID208 or id is selectorMailID209 or id is selectorMailID210 or id is selectorMailID211 or id is selectorMailID212 or id is selectorMailID213 or id is selectorMailID214 or id is selectorMailID215 or id is selectorMailID216 or id is selectorMailID217 or id is selectorMailID218 or id is selectorMailID219 or id is selectorMailID220 or id is selectorMailID221 or id is selectorMailID222 or id is selectorMailID223 or id is selectorMailID224 or id is selectorMailID225 or id is selectorMailID226 or id is selectorMailID227 or id is selectorMailID228 or id is selectorMailID229 or id is selectorMailID230 or id is selectorMailID231 or id is selectorMailID232 or id is selectorMailID233 or id is selectorMailID234 or id is selectorMailID235 or id is selectorMailID236 or id is selectorMailID237 or id is selectorMailID238 or id is selectorMailID239 or id is selectorMailID240 or id is selectorMailID241 or id is selectorMailID242 or id is selectorMailID243 or id is selectorMailID244 or id is selectorMailID245 or id is selectorMailID246 or id is selectorMailID247 or id is selectorMailID248 or id is selectorMailID249 or id is selectorMailID250)
		repeat with itemNumber from 1 to itemCount
			set argumentOffset to 6 + ((itemNumber - 1) * 6)
			set expectedMailID to item argumentOffset of argv as integer
			set expectedMessageID to item (argumentOffset + 1) of argv
			set expectedSubject to item (argumentOffset + 2) of argv
			set expectedSender to item (argumentOffset + 3) of argv
			set datePrefix to item (argumentOffset + 4) of argv
			set expectedRead to item (argumentOffset + 5) of argv
			set sourceMatches to messages of sourceMailbox whose id is expectedMailID
			set sourceIdentity to false
			set sourceMessageIDMatch to false
			set sourceSubjectMatch to false
			set sourceSenderMatch to false
			set sourceReceivedAtMatch to false
			set sourceRead to ""
			if (count of sourceMatches) is 1 then
				set sourceMessage to item 1 of sourceMatches
				set sourceFieldMatches to my identityMatchFields(sourceMessage, expectedMessageID, expectedSubject, expectedSender, datePrefix)
				set sourceMessageIDMatch to item 1 of sourceFieldMatches
				set sourceSubjectMatch to item 2 of sourceFieldMatches
				set sourceSenderMatch to item 3 of sourceFieldMatches
				set sourceReceivedAtMatch to item 4 of sourceFieldMatches
				set sourceIdentity to my allIdentityFieldsMatch(sourceFieldMatches)
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
			set end of outputLines to (expectedMailID as text) & tab & expectedMessageID & tab & ((count of sourceMatches) as text) & tab & (sourceBulkCount as text) & tab & (sourceIdentity as text) & tab & (sourceMessageIDMatch as text) & tab & (sourceSubjectMatch as text) & tab & (sourceSenderMatch as text) & tab & (sourceReceivedAtMatch as text) & tab & sourceRead & tab & (destinationCount as text) & tab & destinationRead
		end repeat
	end tell
	set AppleScript's text item delimiters to linefeed
	set outputText to outputLines as text
	set AppleScript's text item delimiters to ""
	return outputText
end run
