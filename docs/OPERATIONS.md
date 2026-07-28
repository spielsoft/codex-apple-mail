# Development Operations

**Read when:** testing or changing the plugin.

## Validation

Run from the repository root:

```sh
python3 -m unittest discover -s tests -v

python3 /path/to/skill-creator/scripts/quick_validate.py skills/apple-mail

python3 /path/to/plugin-creator/scripts/validate_plugin.py .
```

The test suite compiles every AppleScript on macOS and statically checks
mutation scripts for prohibited operations.

## Manual tool checks

Use [APPLE_MAIL_TOOLING.md](APPLE_MAIL_TOOLING.md) for command syntax. Do not
run a live mutation merely to test plugin installation. Prefer `--help`,
synthetic unit tests, read-only discovery/listing, and dry runs.

Runtime credentials, selections, plans, and audits belong in the consuming
project, not this repository.
