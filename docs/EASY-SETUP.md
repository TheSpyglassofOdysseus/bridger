# Bridger Easy Setup

**Goal:** go from “I use AI” to “my AI has a private server” with as few decisions as possible.

The beginner path has **five visible steps**:

1. Get a Linux server.
2. Install Bridger.
3. Create a private OpenAI tunnel.
4. Add Bridger to ChatGPT.
5. Start building.

Everything else is either automated or optional.

> **Before you spend time on setup:** confirm that the AI client you want to use supports a private/custom MCP connection. ChatGPT product access varies by plan and workspace. OpenAI’s current documentation is the source of truth for developer-mode plugins and Secure MCP Tunnel.

## 1. Get a server

You need one ARM64 Ubuntu/Debian server with SSH + sudo/root access.

The reference path is Oracle Cloud because eligible accounts may be able to use Always Free ARM compute. You do **not** need:

- a Mac mini;
- a dedicated home server;
- a paid VPS just to try the reference path;
- a custom domain.

If you already have a compatible server, skip straight to step 2.

If you do not, use [beginner/01-compute.md](beginner/01-compute.md). The server-creation step stays separate because cloud-account eligibility, capacity, and possible charges belong to the human—not the installer.

### Oracle: easiest free-server path

Useful official links:

- [Oracle Cloud Free Tier](https://docs.oracle.com/en-us/iaas/Content/FreeTier/freetier.htm)
- [Always Free resources](https://docs.oracle.com/en-us/iaas/Content/FreeTier/freetier_topic-Always_Free_Resources.htm)
- [Oracle Cloud sign-up](https://signup.oraclecloud.com/)
- [OCI Cloud Shell](https://docs.oracle.com/en-us/iaas/Content/API/Concepts/cloudshellintro.htm)
- [OCI CLI quickstart](https://docs.oracle.com/en-us/iaas/Content/API/SDKDocs/cliinstall.htm)

As of **2026-10-01**, Oracle's current Always Free documentation lists **2 A1 OCPUs / 12 GB RAM** and **200 GB total combined boot + block storage** in the tenancy's home region. The original Bridger reference server was provisioned under Oracle's older entitlement and received **4 OCPUs / 24 GB RAM / 200 GB storage**. Do not assume that older allocation applies to a new account.

For the smoothest beginner experience, open **OCI Cloud Shell** from the Oracle Console. It already includes a pre-authenticated OCI CLI, so there is nothing to install locally just to inspect the account.

Then run Bridger's read-only OCI inspector:

```bash
curl -fsSLO https://raw.githubusercontent.com/TheSpyglassofOdysseus/bridger/main/scripts/oci/inspect-tenancy.sh
bash inspect-tenancy.sh
```

If your AI can safely operate a terminal on your own computer, you can instead install/configure OCI CLI locally. That gives the AI a better path to inspect availability, compose the exact VM launch request, and verify the result. Keep the API signing keys and OCI config private; do not paste them into chat or Git.

Before anything is created, your AI should show you the actual tenancy limits, proposed OCPU/RAM/storage, home region, image, architecture, and expected free/paid status. No paid resource or account upgrade should happen without explicit human approval.

For Oracle-specific capacity and CLI guidance, continue to [beginner/02-oracle-capacity-and-cli.md](beginner/02-oracle-capacity-and-cli.md).

## 2. Install Bridger

On the server:

```bash
curl -fsSLO https://raw.githubusercontent.com/TheSpyglassofOdysseus/bridger/v0.2.1/scripts/quick-install.sh
less quick-install.sh
sudo bash quick-install.sh
```

Why download first instead of `curl | sudo bash`? Because Bridger is privileged infrastructure. You should be able to inspect the installer before giving it root access.

The installer handles:

- base Linux packages;
- a dedicated `bridger` service account;
- a private Node.js 22 runtime under `/opt/bridger-runtime` (system Node is left alone);
- the pinned Bridger MCP dependencies;
- a generated local MCP credential that is **not printed**;
- systemd services for raw MCP + the compact facade;
- loopback-only listener verification;
- authentication checks;
- Tailscale installation and your own Tailscale authorization;
- reboot-enabled services;
- a safe AI handoff file.

It does **not** create paid resources, buy a domain, open MCP ports publicly, install the advanced Passrail stack, or use anybody else’s AI credentials.

When successful, it ends with:

```text
BRIDGER READY

Server core:       installed
MCP backend:       loopback only
Compact facade:    loopback only
Tailscale:          connected
Public exposure:   none
```

Health check:

```bash
sudo /opt/bridger/scripts/quick-status.sh
```

At the end of an interactive install, Bridger asks whether you want to connect to **ChatGPT/OpenAI now**. If you say yes, it launches the tunnel wizard automatically. If you say no—or want to do it later—run the command in step 3.

## 3. Create the private OpenAI tunnel

This is the only OpenAI account-side infrastructure step.

A private Bridger server should **not** expose ports 18877 or 18879 to the Internet. OpenAI Secure MCP Tunnel gives supported OpenAI products an outbound-only path to the private MCP server.

If the installer did not already launch it, run:

```bash
sudo /opt/bridger/scripts/setup-openai-tunnel.sh
```

The wizard tells you when to open:

**https://platform.openai.com/settings/organization/tunnels**

You create a tunnel in **your own** OpenAI Platform organization/workspace and create a runtime API key with the tunnel permissions OpenAI currently requires.

The wizard then:

- downloads the latest official `openai/tunnel-client` release;
- verifies the published SHA-256 checksum;
- stores the runtime API key in a protected local file;
- stores Bridger’s local MCP key separately;
- configures the tunnel to forward to `127.0.0.1:18879/mcp`;
- sends Bridger’s local `X-API-Key` only to that local MCP origin using a file reference;
- runs `tunnel-client doctor --explain`;
- installs the tunnel as a systemd service;
- waits for OpenAI’s `/readyz` health check to pass.

No inbound MCP port is opened.

Tunnel status:

```bash
sudo /opt/bridger/scripts/tunnel-status.sh
```

## 4. Add Bridger to ChatGPT

Open:

**https://chatgpt.com/plugins**

Then:

1. create a developer-mode plugin/app;
2. choose **Tunnel** for Connection;
3. select the tunnel you just created (or paste its `tunnel_id`);
4. review the discovered Bridger tools;
5. create the connection.

OpenAI treats ChatGPT developer-mode access and Platform tunnel permissions as separate account/workspace permissions. If the tunnel does not appear, the usual causes are workspace association or missing **Tunnels Read + Use** permission.

Use OpenAI’s current documentation for account/plan-specific UI because these capabilities change independently of Bridger:

- Secure MCP Tunnel: https://developers.openai.com/api/docs/guides/secure-mcp-tunnels
- ChatGPT developer mode / MCP apps: https://help.openai.com/en/articles/12584461-developer-mode-and-full-mcp-connectors-in-chatgpt

Other MCP-capable AI clients use their own connection flow instead of steps 3–4.

## 5. Test, then build

Start with harmless checks:

> Inspect my Bridger server. Read `/etc/hostname`, inspect the Bridger services, and report whether the raw MCP backend is still loopback-only. Do not change anything.

Then give your AI:

```bash
cat /home/bridger/BRIDGER-HANDOFF.txt
```

The handoff intentionally excludes credentials.

From there you can build sites, research tools, automations, dashboards, APIs, games, or other projects on a machine that persists after the chat ends.

## What you do **not** have to do

For the beginner path, you do not have to:

- buy a Mac mini;
- keep your personal computer running;
- pay for a VPS when eligible free compute is available;
- buy a domain;
- configure nginx;
- expose MCP publicly;
- edit systemd units;
- install Node globally;
- edit tunnel YAML;
- type your MCP credential into ChatGPT;
- install Passrail;
- understand every Bridger component before getting value from it.

You **do** bring your own AI account/client. Bridger does not provide or share the maintainer’s ChatGPT account, API key, plugin credentials, credits, or usage, and it does not bypass provider limits or billing.

## If something fails

Do not start improvising public ports or disabling authentication.

Run:

```bash
sudo /opt/bridger/scripts/quick-status.sh
sudo /opt/bridger/scripts/tunnel-status.sh
```

Then give the sanitized output to your AI and point it at this repository.

The detailed material in [START_HERE.md](../START_HERE.md), [QUICKSTART.md](QUICKSTART.md), [SECURITY.md](../SECURITY.md), and the beginner chapters exists for troubleshooting and learning—not as prerequisites for the happy path.

## Remove / roll back

Safe removal keeps credentials and local state:

```bash
sudo /opt/bridger/scripts/quick-uninstall.sh
```

A destructive purge requires both `--purge` and typing `PURGE`.

Tailscale is never removed automatically because you may use it for other services.
