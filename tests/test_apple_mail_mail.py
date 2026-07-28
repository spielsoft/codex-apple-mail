import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skills" / "apple-mail" / "scripts"))

from apple_mail.mail import FLAG_INDEX_TO_COLOR, flag_color_from_index, parse_tsv


class AppleMailMetadataTests(unittest.TestCase):
    def test_flag_index_mapping_matches_mail(self):
        self.assertEqual(
            FLAG_INDEX_TO_COLOR,
            {
                -1: "none",
                0: "red",
                1: "orange",
                2: "yellow",
                3: "green",
                4: "blue",
                5: "purple",
                6: "gray",
            },
        )
        self.assertEqual(flag_color_from_index("0"), "red")
        self.assertEqual(flag_color_from_index("3"), "green")
        self.assertEqual(flag_color_from_index("-1"), "none")
        self.assertEqual(flag_color_from_index("7"), "unknown")
        self.assertEqual(flag_color_from_index("not-an-index"), "unknown")

    def test_list_parser_adds_color_and_preserves_flag_fields(self):
        rows = parse_tsv(
            "TYPE\tMAIL_ID\tSUBJECT\tFLAGGED\tFLAG_INDEX\n"
            "MESSAGE\t101\tRed example\ttrue\t0\n"
            "MESSAGE\t102\tGreen example\ttrue\t3\n"
            "MESSAGE\t103\tUnlabeled\tfalse\t-1\n"
            "SUMMARY\t1\t3\t\t\n"
        )

        self.assertEqual(rows[0]["FLAGGED"], "true")
        self.assertEqual(rows[0]["FLAG_INDEX"], 0)
        self.assertEqual(rows[0]["FLAG_COLOR"], "red")
        self.assertEqual(rows[1]["FLAG_INDEX"], 3)
        self.assertEqual(rows[1]["FLAG_COLOR"], "green")
        self.assertEqual(rows[2]["FLAGGED"], "false")
        self.assertEqual(rows[2]["FLAG_INDEX"], -1)
        self.assertEqual(rows[2]["FLAG_COLOR"], "none")
        self.assertNotIn("FLAG_COLOR", rows[3])

    def test_legacy_tsv_without_flag_index_still_parses(self):
        rows = parse_tsv(
            "TYPE\tMAIL_ID\tFLAGGED\n"
            "MESSAGE\t101\ttrue\n"
        )
        self.assertEqual(rows[0]["FLAGGED"], "true")
        self.assertNotIn("FLAG_INDEX", rows[0])
        self.assertNotIn("FLAG_COLOR", rows[0])

    def test_get_parser_keeps_multiline_body_in_one_record(self):
        encoded_body = (
            "First line\\nSecond line\\r"
            "Signature\u2028Address\u2029Footer\u0085Postscript"
        )
        rows = parse_tsv(
            "TYPE\tMAIL_ID\tMESSAGE_ID\tBODY\n"
            "MESSAGE\t101\tgeneric@example.test\t{}\n".format(encoded_body)
        )

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["TYPE"], "MESSAGE")
        self.assertEqual(
            rows[0]["BODY"],
            "First line\nSecond line\r"
            "Signature\u2028Address\u2029Footer\u0085Postscript",
        )


if __name__ == "__main__":
    unittest.main()
