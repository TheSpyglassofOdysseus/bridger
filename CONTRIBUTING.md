# Contributing

Contributions are welcome, especially around portability, security hardening, tests, and additional bounded client adapters.

## Development

```bash
scripts/check.sh
scripts/check-starter-publication.sh
```

Starter/onboarding changes should also preserve the approval boundaries in `AI_HANDOFF.md` and the objections recorded in `docs/STARTER-COUNTER-REVIEW.md`.

The canonical release gate is intentionally runnable on a normal Linux host and does not require GitHub-hosted CI.

Changes to request identity, receipt reconciliation, replay behavior, authentication, command policy, or deployment boundaries should include regression tests and a short threat-model note in the pull request.

Please keep the core small. Bridger is infrastructure plumbing, not an autonomous agent framework.
