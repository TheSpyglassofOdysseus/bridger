# Build-something prompt

```text
I want to build the following on my Bridger server:

<describe the thing>

Read AI_HANDOFF.md and docs/STARTER-ARCHITECTURE.md first.

Before implementing, classify the project:
- private or public;
- persistent state or disposable;
- expected CPU/RAM/storage;
- secrets required;
- backup requirement;
- architecture compatibility (ARM64/x86_64);
- services/ports it needs;
- estimated new paid resources, if any.

Prefer a private Tailscale-only first version. Show me any financial or public
exposure boundary before crossing it. Keep source in Git, durable state outside
the repository where appropriate, and include a rollback/recovery path.
```
