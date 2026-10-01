# Release checklist

A Bridger release should not be cut from a dirty working tree or from unreviewed dependency changes.

## Required gates

1. Run `scripts/check-starter-publication.sh`.
2. Run `scripts/check.sh` on Node 22+.
3. Run `scripts/check-public-candidate.sh` when validating an initial public seed.
4. Run an isolated real MCP probe: initialize, tools/list, harmless `read_file`, harmless bounded `start_process`.
5. Run `npm audit --omit=dev`.
6. Scan the release tree for credentials, private hostnames/IPs, personal paths, account IDs, and operational mailbox coordinates.
7. Confirm public examples contain placeholders rather than live credentials or registration IDs.

## Platform acceptance

Before claiming a platform is supported, verify the release from a fresh checkout on that platform.

For v0.1, the release-certified platform is **ARM64 Linux** (the Oracle A1 reference path). The clean-room ARM64 gate must pass from an exported candidate.

x86_64 Linux is an expected portability target, but it must be described as **experimental / not release-certified** until a clean x86_64 host passes the same gate. Do not block an ARM64 v0.1 release by pretending an unverified platform is supported.

The starter acceptance should also cover:

- private/Tailscale-only operation with no domain;
- public HTTPS edge when intentionally configured;
- credential rotation/revocation;
- reboot/cold-start behavior on the reference deployment;
- backup/restore;
- at least one second-user onboarding pass.

## Release artifact

Tag only the exact reviewed commit. Record the commit/tree hash and keep the source tree reproducible from the tag.

Do not publish operational receipts, incident logs, production coordinates, secrets, or private control-plane data as release assets.
