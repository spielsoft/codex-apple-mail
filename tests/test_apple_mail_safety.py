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
)


class AppleMailSafetyTests(unittest.TestCase):
    def test_batch_scripts_avoid_mail_offset_term_collision(self):
        for script in BATCH_SCRIPTS:
            source = script.read_text(encoding="utf-8")
            self.assertIsNone(
                re.search(r"\bset\s+offset\s+to\b|\bitem\s+offset\b", source),
                "{} uses Mail's offset term as a loop variable".format(
                    script.name
                ),
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
