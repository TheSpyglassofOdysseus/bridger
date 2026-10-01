# Bridger Personal AI Server Starter

Build a small Linux server that your AI can safely help operate.

This starter is for people who are comfortable using an AI assistant but may not be experienced Linux administrators. The goal is not to hide the infrastructure. The goal is to make it understandable enough that you can own it.

## The idea

- **Oracle Cloud** is the reference compute path because an Always Free or low-cost VM may be available.
- **Tailscale** is the default private network for administration and private apps.
- **Cloudflare** is the recommended domain/DNS path when you intentionally publish a web service.
- **Git + GitHub** provide source history, collaboration, releases, and recovery. GitHub is not required as Bridger's runtime message bus.
- **Bridger** is the controlled execution boundary between an authorized AI client and the Linux host.

The core rule is:

> **Private by default. Public intentionally.**

A domain is optional. You can complete the private-server path without buying one or exposing a public web service.

## Bridger is three pieces

A working Bridger setup has three required layers:

1. **Your server** — a Linux machine you control that stays available after the chat ends.
2. **Bridger MCP on that server** — the server-side program that exposes bounded tools for files, commands, repositories, and services.
3. **Your AI-side connection** — a plugin/app/connector that points your AI client at **your** Bridger MCP endpoint.

For ChatGPT today, the public Bridger repository gives you the server-side MCP software; each user connects their own plugin/app to their own endpoint. ChatGPT plugin/MCP capabilities depend on plan and workspace permissions. Other MCP-capable clients have their own connection flow.

Bridger does **not** include or share the maintainer's ChatGPT account, API keys, plugin credentials, credits, or usage.

## What you do not need

You can get meaningful use from Bridger without buying the infrastructure people often assume is necessary for persistent AI work.

- **You do not need a Mac mini or dedicated home server.** A small Linux VM can be the persistent machine.
- **You do not necessarily need a monthly server bill.** The reference path targets Oracle Always Free ARM compute when your tenancy is eligible and capacity is available.
- **You do not need to buy a domain.** Tailscale gives you private access. A free DNS/subdomain service can provide a shareable hostname; a custom domain is optional.
- **You do not need an AI-hosted machine merely to keep your server available.** Bridger puts the persistent machine on infrastructure you control. You still bring an AI account/client that supports the MCP actions you need. On ChatGPT, plugin/full-MCP availability depends on plan and workspace permissions, and Bridger does not bypass usage limits or billing.

Free tiers, AI-plan limits, and third-party terms change. Treat these as ways to reduce cost, not permanent guarantees.

## Before you begin

You need:

- a computer with a web browser and terminal;
- an SSH key or willingness to create one;
- for the v0.1 release-certified path, an ARM64 Linux server (x86_64 is experimental until independently verified);
- an Oracle Cloud account for the reference path, or another Linux VM you control;
- a Tailscale account;
- a GitHub account if you want remote source hosting;
- optionally, a Cloudflare account and a domain for public web apps.

### Billing rule

**Never let an AI create a billable cloud resource or register a domain without showing you the exact proposed resource and current price first and receiving explicit approval.**

Cloud pricing, free-tier limits, domain prices, and product terms change. The documentation in this repository explains the reference setup, but your AI should verify current provider documentation before any purchase or provisioning decision.

## Recommended path

1. Read [AI_HANDOFF.md](AI_HANDOFF.md) and give it to the AI assistant helping you.
2. Understand the architecture in [docs/STARTER-ARCHITECTURE.md](docs/STARTER-ARCHITECTURE.md).
3. Create or inspect your Linux server using [docs/beginner/01-compute.md](docs/beginner/01-compute.md).
4. If Oracle's console cannot provision the desired free shape, use [docs/beginner/02-oracle-capacity-and-cli.md](docs/beginner/02-oracle-capacity-and-cli.md).
5. Harden SSH and the host with [docs/beginner/03-host-baseline.md](docs/beginner/03-host-baseline.md).
6. Add the server and your own devices to Tailscale using [docs/beginner/04-tailscale.md](docs/beginner/04-tailscale.md).
7. Install the interactive Bridger core with [docs/beginner/05-install-bridger.md](docs/beginner/05-install-bridger.md).
8. Connect your AI using [docs/beginner/06-connect-your-ai.md](docs/beginner/06-connect-your-ai.md).
9. Verify the private path before exposing anything publicly.
10. If you want a public site or API, use [docs/beginner/07-cloudflare-domain-dns.md](docs/beginner/07-cloudflare-domain-dns.md) and [docs/beginner/08-public-web.md](docs/beginner/08-public-web.md).
11. Add Git/GitHub using [docs/beginner/09-git-github.md](docs/beginner/09-git-github.md).
12. Configure backups and prove you can restore them with [docs/beginner/10-backup-recovery.md](docs/beginner/10-backup-recovery.md).
13. Build one harmless first project with [docs/beginner/11-first-project.md](docs/beginner/11-first-project.md).
14. Prove you can revoke and rotate credentials with [docs/beginner/12-credential-rotation.md](docs/beginner/12-credential-rotation.md).

## Oracle provisioning reality

The original reference deployment encountered repeated Oracle web-console provisioning failures/capacity problems and ultimately secured the desired VM through OCI CLI.

Do **not** assume that means the console is universally broken. Oracle documents that Always Free shapes can temporarily be unavailable because of host capacity. The CLI is useful because it lets you enumerate the tenancy, availability domains, shapes, and capacity directly and make a precise launch request.

The current Oracle limits may not match the original reference deployment. Discover your current tenancy and verify current Oracle documentation before choosing CPU, memory, storage, or account type.

Upgrading an Oracle tenancy to Pay As You Go may improve access to capacity while eligible Always Free usage can remain free, but it also enables billable usage. Treat that as a financial boundary: configure budgets/quotas and require explicit approval before creating anything outside verified free limits.

## What this starter does not promise

- Oracle will always have free capacity.
- Your domain will be free.
- Cloudflare, Tailscale, Oracle, GitHub, or an AI provider will keep current pricing or product terms forever.
- Bridger makes arbitrary AI execution harmless.
- Every package supports ARM64.
- A backup is valid merely because a backup job says it succeeded.

The project is designed to fail visibly, keep powerful interfaces private, and make recovery possible.

## If you already have a Linux server

Skip Oracle provisioning. The rest of the starter is deliberately provider-agnostic. A compatible host needs Linux with systemd, Python 3.11+, Node.js 22+, enough storage for your projects, and a security posture you understand.

## When you are done

You should be able to answer all of these:

- Which services are public?
- Which services are reachable only through Tailscale or loopback?
- Where are Bridger secrets stored?
- How do you rotate them?
- What cloud resources can incur charges?
- How do you stop the server?
- How do you restore it?
- How do you roll Bridger back?
- Which Git repository is authoritative for your code?
- What would happen if GitHub, Cloudflare, Tailscale, or your AI provider were temporarily unavailable?

If you cannot answer one of those yet, treat it as unfinished setup rather than a mystery to ignore.
