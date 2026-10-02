# 5. Install Bridger

This chapter gets the **interactive core** running. [Passrail](https://github.com/TheSpyglassofOdysseus/passrail) is optional advanced infrastructure and is not required here.

## What you are installing

The starter's first milestone is:

```text
AI client -> authenticated/bounded Bridger edge -> loopback MCP -> Desktop Commander -> Linux host
```

Keep the raw MCP backend on loopback.

## Reference layout

The public templates assume:

- service user: `bridger`
- code: `/opt/bridger`
- environment: `/etc/bridger/bridger.env`
- service home: `/home/bridger`

You may use different paths, but change them consistently.

## Install the pinned Node dependencies

From the repository:

```bash
cd /opt/bridger/selfhosted
npm ci
```

Use Node 22+ for a reproducible fresh install. Some transitive dependencies currently declare Node 22+ even though older installed trees may appear to run on Node 20.

## Configure secrets

Copy `deploy/bridge.env.example` to a protected location and replace the placeholders you actually need.

For the interactive core, the important values are:

- `BRIDGE_DC_PORT`
- `MCP_PROXY_API_KEY`
- `BRIDGE_ACTIONS_PORT`
- `BRIDGE_ACTIONS_KEY`
- `BRIDGE_ACTIONS_PUBLIC_URL` if the Actions facade will have a public HTTPS edge

Do not enable the Passrail variables merely because they exist in the example.

## Install core system services

Review the unit files before installing them:

- `deploy/bridge-mcp.service`
- `deploy/bridge-actions.service`

The raw MCP backend should bind to `127.0.0.1`.

The optional low-chatter interactive facade is documented in [../INTERACTIVE-FACADE.md](../INTERACTIVE-FACADE.md).

## Verify before remote access

Run:

```bash
scripts/check.sh
```

Then inspect listeners:

```bash
scripts/network/check-public-ports.sh
```

Do not proceed if the raw MCP listener is exposed on a wildcard/public interface.

## Harmless canaries

Before giving the AI mutating work, prove:

1. read `/etc/hostname`;
2. run a bounded `printf bridger-probe`;
3. inspect one repository;
4. inspect one systemd service.

If those work through the intended bounded interface, continue to [06-connect-your-ai.md](06-connect-your-ai.md).
