on run argv
	if (count of argv) is not 1 then error "Expected one account"
	set accountName to item 1 of argv
	tell application "Mail"
		if not (exists account (accountName as text)) then error "Account not found: " & accountName
		set targetAccount to account (accountName as text)
		synchronize with targetAccount
		return "SYNCHRONIZE_REQUESTED" & tab & accountName
	end tell
end run
