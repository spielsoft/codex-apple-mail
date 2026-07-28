import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills" / "apple-mail"
PACKAGE = SKILL / "scripts" / "apple_mail"
APPLESCRIPTS = PACKAGE / "applescript"
MUTATION_SCRIPTS = (
    APPLESCRIPTS / "copy_account_to_local.applescript",
    APPLESCRIPTS / "move_local_messages.applescript",
    APPLESCRIPTS / "set_read_messages.applescript",
    APPLESCRIPTS / "create_local_mailbox.applescript",
)
BATCH_SCRIPTS = MUTATION_SCRIPTS[:3] + (
    APPLESCRIPTS / "verify_messages.applescript",
    APPLESCRIPTS / "get_messages.applescript",
)
INDEXED_MESSAGE_SCRIPTS = MUTATION_SCRIPTS[1:3] + (
    APPLESCRIPTS / "get_message.applescript",
    APPLESCRIPTS / "get_messages.applescript",
    APPLESCRIPTS / "verify_messages.applescript",
)


class AppleMailSafetyTests(unittest.TestCase):
    def test_skill_requires_first_call_mail_escalation(self):
        source = (SKILL / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn('sandbox_permissions: "require_escalated"', source)
        self.assertRegex(
            source, r"Do not try the command in\s+the sandbox first\."
        )

    def test_batch_scripts_avoid_mail_offset_term_collision(self):
        for script in BATCH_SCRIPTS:
            source = script.read_text(encoding="utf-8")
            self.assertIsNone(
                re.search(r"\bset\s+offset\s+to\b|\bitem\s+offset\b", source),
                "{} uses Mail's offset term as a loop variable".format(
                    script.name
                ),
            )

    def test_missing_index_error_is_normalized_only_at_indexed_lookup(self):
        for script in INDEXED_MESSAGE_SCRIPTS:
            source = script.read_text(encoding="utf-8")
            self.assertIn(
                "on indexedMessages(sourceMailbox, expectedMailID)", source
            )
            self.assertIn(
                "if errorNumber is -1719 then return {}", source
            )
            self.assertIn("error errorMessage number errorNumber", source)
            self.assertIn(
                "set sourceMatches to my indexedMessages("
                "sourceMailbox, expectedMailID)",
                source,
            )
            self.assertNotIn(
                "set sourceMatches to messages of sourceMailbox whose id is "
                "expectedMailID",
                source,
            )

    def test_verify_retries_transient_mail_handler_failure_but_never_normalizes_it(self):
        source = (
            APPLESCRIPTS / "verify_messages.applescript"
        ).read_text(encoding="utf-8")
        self.assertIn(
            "set retryDelays to {0.1, 0.2, 0.4, 0.8}", source
        )
        self.assertIn("repeat with attemptNumber from 1 to 5", source)
        self.assertIn(
            "if errorNumber is -10000 and attemptNumber < 5 then", source
        )
        self.assertNotIn(
            "if errorNumber is -10000 then return {}", source
        )

    def test_bulk_copy_and_move_use_direct_mail_specifiers(self):
        copy_source = MUTATION_SCRIPTS[0].read_text(encoding="utf-8")
        move_source = MUTATION_SCRIPTS[1].read_text(encoding="utf-8")
        verify_source = (
            APPLESCRIPTS / "verify_messages.applescript"
        ).read_text(encoding="utf-8")
        self.assertIn(
            "duplicate (messages of sourceMailbox whose id is selectorMailID01",
            copy_source,
        )
        self.assertIn(
            "move (messages of sourceMailbox whose id is selectorMailID001",
            move_source,
        )
        self.assertNotIn("duplicate messagesToCopy", copy_source)
        self.assertNotIn("move messagesToMove", move_source)
        self.assertIn(
            "set copyCount to count of mailIDsToCopy", copy_source
        )
        self.assertIn(
            "if bulkSourceCount is not copyCount then error", copy_source
        )
        self.assertLess(
            copy_source.index("set copyCount to count of mailIDsToCopy"),
            copy_source.index("set selectorMailIDs to {} & mailIDsToCopy"),
        )
        self.assertLess(
            copy_source.index(
                'if operationMode is "probe" then return my probeResult'
            ),
            copy_source.index("duplicate (messages of sourceMailbox"),
        )
        self.assertNotIn("whose id is in", copy_source)
        self.assertIn("selectorMailID10", copy_source)
        self.assertNotIn("selectorMailID250", copy_source)
        self.assertIn(
            "repeat while (count of selectorMailIDs) < 10", copy_source
        )
        self.assertIn("selectorMailID250", move_source)
        self.assertIn(
            "repeat while (count of selectorMailIDs) < 250", move_source
        )
        self.assertIn("on bulkMessages10(", verify_source)
        self.assertIn(
            "repeat while (count of selectorMailIDs) < 10", verify_source
        )
        self.assertIn("selectorMailID10", verify_source)
        self.assertNotIn("selectorMailID250", verify_source)
        self.assertNotIn("whose id is in", verify_source)
        self.assertIn("SOURCE_BULK_COUNT", verify_source)
        self.assertLess(
            copy_source.index("duplicate (messages of sourceMailbox"),
            copy_source.index(
                "set finalDestination to my destinationSnapshot"
            ),
        )
        self.assertIn("DESTINATION_IDENTITY", copy_source)
        self.assertIn("BARRIER_ATTEMPTS", copy_source)
        self.assertIn(
            "set barrierDelays to {1.5, 4.8}",
            copy_source,
        )
        self.assertIn(
            "repeat with barrierDelay in barrierDelays", copy_source
        )
        self.assertNotIn("repeat while not", copy_source)
        self.assertIn(
            "set plannedSourceMessages to my bulkMessages10", copy_source
        )
        self.assertNotIn(
            "set sourceMatches to my indexedMessages(sourceMailbox, expectedMailID)",
            copy_source,
        )

    def test_identity_checks_coerce_mail_sender_to_text(self):
        for script in MUTATION_SCRIPTS[:3] + (
            APPLESCRIPTS / "verify_messages.applescript",
            APPLESCRIPTS / "get_messages.applescript",
        ):
            source = script.read_text(encoding="utf-8")
            self.assertRegex(
                source,
                r"set actualSender to \(get sender of .+\) as text",
                script.name,
            )
            self.assertIn("id of character characterIndex", source)
            self.assertIn("on normalizedSender(theText)", source)
            self.assertIn('set quoteMarker to quote & " <"', source)
            self.assertIn("normalizedSender(actualSender)", source)
            self.assertRegex(
                source, r"normalizedSender\(expectedSender(?:Text)?\)"
            )

    def test_mutation_scripts_have_no_forbidden_commands(self):
        for script in MUTATION_SCRIPTS:
            source = script.read_text(encoding="utf-8").lower()
            for forbidden in (
                "delete",
                "trash",
                "send",
                "reply",
                "forward",
                "redirect",
                "empty",
            ):
                self.assertIsNone(
                    re.search(r"\b{}\b".format(forbidden), source),
                    "{} contains forbidden command: {}".format(
                        script.name, forbidden
                    ),
                )

    def test_generic_package_has_no_campaign_concepts(self):
        sources = "\n".join(
            path.read_text(encoding="utf-8")
            for path in PACKAGE.rglob("*")
            if path.suffix in (".py", ".applescript")
        ).casefold()
        self.assertNotIn("pur" + "ge", sources)
        self.assertNotIn("no" + "pur" + "ge", sources)

    @unittest.skipUnless(sys.platform == "darwin", "AppleScript compiler requires macOS")
    def test_all_applescripts_compile(self):
        with tempfile.TemporaryDirectory() as temporary:
            for source in sorted(APPLESCRIPTS.glob("*.applescript")):
                destination = Path(temporary) / (source.stem + ".scpt")
                result = subprocess.run(
                    ["/usr/bin/osacompile", "-o", str(destination), str(source)],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                )
                self.assertEqual(
                    result.returncode,
                    0,
                    "{} failed to compile: {}".format(source.name, result.stderr),
                )


if __name__ == "__main__":
    unittest.main()
