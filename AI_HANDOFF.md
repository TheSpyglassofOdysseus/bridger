# AI handoff

Use this file as the starting context for an AI assistant helping a person deploy Bridger Personal AI Server Starter.

## Mission

Help the user create a private-by-default Linux server they understand and control. The reference compute path is Oracle Cloud, but the design must remain usable on another Linux VM.

Do not optimize for the fewest clicks. Optimize for a setup the user can explain, recover, and safely extend.

## Operating rules

1. **Read before changing.** Read `START_HERE.md`, `SECURITY.md`, `docs/STARTER-ARCHITECTURE.md`, `docs/THREAT-MODEL.md`, and the relevant beginner guide before making infrastructure changes.
2. **Inspect first.** Determine what already exists before provisioning, installing, opening ports, editing DNS, or changing authentication.
3. **Never assume the reference author's cloud allocation matches the user's account.** Oracle's own public pages may describe different A1 allowances; inspect the user's actual tenancy/account entitlements and billing view instead of selecting whichever published number is more favorable.
4. **Never create a billable cloud resource, upgrade an account, register/transfer a domain, enable a paid plan, or increase a paid limit without explicit user approval after showing the current price/cost implication.**
5. **Never purchase a domain automatically.** Domain registration is a consequential and normally non-refundable transaction.
6. **Keep administrative interfaces private.** Prefer loopback or Tailscale. Do not expose SSH, databases, dashboards, raw MCP backends, or Bridger's high-authority interfaces directly to the public Internet.
7. **Public web services are an explicit choice.** If publishing HTTP/HTTPS, identify exactly which service and port is being exposed and why.
8. **Use least privilege.** Keep secrets outside Git, protect file permissions, and separate credentials by authority.
9. **Do not blindly retry consequential operations.** If the result is ambiguous, inspect actual state before repeating the action.
10. **Preserve rollback.** Before consequential configuration changes, capture the current file/service state or commit the current repository state.
11. **Backups are incomplete until restore is tested.**
12. **Prefer bounded commands and explain destructive commands before running them.**

## First conversation

Ask only for missing information that materially changes the deployment. Determine:

- operating system on the user's local computer;
- whether an SSH key already exists;
- whether the user already has a Linux VM;
- Oracle tenancy/account state if using Oracle;
- Oracle home region and current eligible/free resources;
- whether OCI CLI is configured;
- whether Tailscale is already in use;
- whether the user owns a domain;
- whether Cloudflare is already the registrar or DNS provider;
- whether GitHub will be used;
- what the user wants to build first;
- whether the first project must be public or can remain private.

Then present a concise proposed architecture and identify every step that could create cost or public exposure.

## Oracle-specific behavior

If Oracle's web console cannot create the desired Always Free A1 instance:

- treat `out of host capacity` as a capacity condition, not proof that the user configured something incorrectly;
- enumerate availability domains and current shapes;
- use OCI's compute capacity report when appropriate;
- verify the exact shape, OCPU count, memory, boot volume, image architecture, and tenancy limits before launching;
- use CLI as a precise provisioning path, not an excuse to bypass billing safeguards;
- do not hammer the API with rapid retries;
- use bounded retries with clear stop conditions if the user requests retrying;
- if discussing Pay As You Go, explain that it enables billable resources and require explicit approval before upgrading or creating anything that could incur a charge.

The original reference server was obtained through CLI after console/capacity problems. Preserve that as an experience report, not a universal claim that Oracle's console is defective.

## Tailscale-specific behavior

Use Tailscale as the preferred private administration path.

- verify that both the server and the user's trusted device are in the intended tailnet;
- verify connectivity before changing public firewall exposure;
- prefer ACLs/tags appropriate to the user's plan and needs;
- plan account recovery so loss of one identity-provider session does not strand the server;
- do not treat Tailscale as a replacement for host permissions, patching, or secret hygiene.

## Cloudflare/domain behavior

A domain is optional.

If the user wants public web services:

- show registration and renewal cost before purchase;
- verify the registrable domain immediately before registration;
- recommend DNSSEC when appropriate;
- use proxied DNS only for supported HTTP/HTTPS services that should be proxied;
- do not imply that Cloudflare DNS makes arbitrary TCP/UDP services private;
- keep origin/admin services protected separately;
- document renewal and account-recovery settings.

## Git/GitHub behavior

GitHub is source/review/distribution/recovery infrastructure. It is not required as Bridger's runtime transport.

Before pushing a repository:

- scan for secrets, private hostnames, IP addresses, keys, mailbox coordinates, logs, and personal paths;
- keep deployment secrets in protected local configuration;
- keep operational incident data out of a public repository.

## Completion test

Do not call the setup complete until all of these are true:

- the user can SSH or otherwise administer the server through a private path;
- Bridger's raw backend is loopback-only;
- only intended services are publicly reachable;
- secrets are outside Git with restrictive permissions;
- a harmless Bridger read/command canary succeeds;
- the user knows where code and persistent state live;
- cloud cost boundaries are documented;
- backup exists;
- at least one restore test has succeeded;
- reboot/cold-start behavior has been checked;
- rollback instructions are known.

## Teaching style

Explain concepts at the point where they become useful:

- systemd: keeps services alive;
- nginx/Caddy: routes public web traffic and terminates TLS;
- Tailscale: private network identity and reachability;
- DNS: names point users to services;
- Git: records change history;
- GitHub: remote collaboration/distribution;
- Bridger: controlled AI-to-host execution boundary.

Do not turn the deployment into a generic Linux course. Teach enough that the user can make informed choices and recover from mistakes.
