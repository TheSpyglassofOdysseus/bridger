# 4. Tailscale private networking

Tailscale is the recommended private administration network for the starter.

At the time this guide was written, Tailscale's Personal plan was listed as free for individuals with up to six users. Verify current plan terms here:

https://tailscale.com/pricing

Official Linux install guide:

https://tailscale.com/docs/install/linux

## Why add Tailscale early?

It gives the server a private identity reachable from your trusted devices without requiring you to publish every management service to the Internet.

Use it for:

- SSH/admin access;
- private dashboards;
- development previews;
- internal APIs;
- diagnostics.

Do not use it as an excuse to ignore Linux permissions or application authentication.

## Install

Tailscale currently documents:

```bash
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up
```

If you do not want to pipe a remote script to a shell, use the distribution-specific package instructions from Tailscale's official documentation instead.

## Verify

On the server:

```bash
tailscale status
tailscale ip -4
```

On your trusted computer, install Tailscale and join the same intended tailnet.

Then verify private reachability.

The repository helper:

```bash
scripts/network/verify-tailnet.sh
```

performs a local status check; it cannot prove your remote client is trustworthy.

## ACLs and tags

For a one-person setup, the default tailnet may be enough to begin. As you add people/devices/services, use Tailscale ACLs/grants/tags appropriate to your current plan.

Avoid granting a shared server broader tailnet access than it needs.

## Recovery

Write down how you would recover if:

- your identity-provider session is lost;
- your laptop is lost;
- the server key expires or is removed;
- the server is accidentally deleted from the tailnet.

Do not make Tailscale the only path you understand for disaster recovery. Keep the cloud provider's console/recovery mechanisms documented.

## Milestone

Before continuing, you should be able to administer the server through Tailscale while the Bridger raw backend remains loopback-only.
