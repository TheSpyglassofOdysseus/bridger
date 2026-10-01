# 11. Build the first project

The first project should prove the stack without making the server important.

## Goal

Build one tiny web service, keep it private on Tailscale first, commit it to Git, run it under a service manager, reboot, and prove it comes back.

The example in `examples/hello-server/` is intentionally boring.

That is good.

## What this teaches

You will touch:

- a working directory;
- Python or another runtime;
- a listening address/port;
- systemd or another durable service mechanism;
- Tailscale reachability;
- Git history;
- logs;
- restart/reboot behavior.

Those concepts transfer directly to more interesting projects.

## AI prompt

Use:

```text
Read START_HERE.md, AI_HANDOFF.md, SECURITY.md, docs/STARTER-ARCHITECTURE.md,
and docs/beginner/09-first-project.md.

Help me deploy the hello-server example privately through Tailscale.

Inspect my current host before changing anything. Keep the application off the
public Internet. Explain the systemd unit, listening address, logs, and rollback.
Commit the project only after verifying no secrets are present. Then help me
perform a reboot/cold-start check.
```

## Graduation

After this succeeds, build what you actually want.

Examples:

- private personal dashboard;
- research collector;
- family photo/tool archive;
- home inventory;
- small API;
- scheduled report generator;
- web application;
- data-analysis service.

For each new service, decide **private or public** before deciding how to expose it.
