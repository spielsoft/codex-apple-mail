import csv
import subprocess
from pathlib import Path
from typing import Any, Dict, Iterable, List


FLAG_INDEX_TO_COLOR = {
    -1: "none",
    0: "red",
    1: "orange",
    2: "yellow",
    3: "green",
    4: "blue",
    5: "purple",
    6: "gray",
}


class MailScriptError(RuntimeError):
    pass


def flag_color_from_index(value: Any) -> str:
    try:
        flag_index = int(value)
    except (TypeError, ValueError):
        return "unknown"
    return FLAG_INDEX_TO_COLOR.get(flag_index, "unknown")


def unescape_field(value: str) -> str:
    output: List[str] = []
    index = 0
    replacements = {"t": "\t", "n": "\n", "r": "\r", "\\": "\\"}
    while index < len(value):
        if value[index] == "\\" and index + 1 < len(value):
            code = value[index + 1]
            if code in replacements:
                output.append(replacements[code])
                index += 2
                continue
        output.append(value[index])
        index += 1
    return "".join(output)


def parse_tsv(text: str) -> List[Dict[str, Any]]:
    lines = [line for line in text.splitlines() if line]
    if not lines:
        return []
    rows = list(csv.reader(lines, delimiter="\t"))
    header = rows[0]
    parsed: List[Dict[str, Any]] = []
    for row in rows[1:]:
        if len(row) < len(header):
            row += [""] * (len(header) - len(row))
        record = {
            key: unescape_field(value) for key, value in zip(header, row)
        }
        if record.get("TYPE") == "MESSAGE" and "FLAG_INDEX" in record:
            try:
                record["FLAG_INDEX"] = int(record["FLAG_INDEX"])
            except (TypeError, ValueError):
                pass
            record["FLAG_COLOR"] = flag_color_from_index(record["FLAG_INDEX"])
        parsed.append(record)
    return parsed


class MailRunner:
    def __init__(self, applescript_dir: Path, timeout: int = 120):
        self.applescript_dir = applescript_dir
        self.timeout = timeout

    def run_raw(self, script_name: str, arguments: Iterable[str] = ()) -> str:
        script_path = self.applescript_dir / script_name
        if not script_path.is_file():
            raise MailScriptError("AppleScript not found: {}".format(script_path))
        command = ["/usr/bin/osascript", str(script_path)]
        command.extend(str(argument) for argument in arguments)
        result = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=self.timeout,
        )
        if result.returncode != 0:
            raise MailScriptError(result.stderr.strip() or result.stdout.strip())
        return result.stdout.strip()

    def run_tsv(
        self, script_name: str, arguments: Iterable[str] = ()
    ) -> List[Dict[str, Any]]:
        return parse_tsv(self.run_raw(script_name, arguments))
