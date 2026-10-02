# Personal AI Server Starter architecture

The starter adds an onboarding architecture around Bridger's existing execution architecture. It does not weaken the Bridger threat model.

## Design principles

1. Private by default. Public intentionally.
2. No billable or non-refundable action without explicit human approval.
3. GitHub is source/review/distribution, not the steady-state runtime bus.
4. Administrative access belongs on loopback, Unix sockets, or a private network.
5. The user's cloud account is discovered, not assumed.
6. A provider failure should not invalidate the whole design.
7. ARM is a deployment option, not a hidden assumption.
8. Backups require restore tests.
9. Recovery and rollback are part of installation.
10. The AI is powerful tooling, not the authority for financial or high-impact choices.

## Reference topology

### Private-only setup

```text
Trusted laptop / phone
        |
     Tailscale
        |
        v
+--------------------------+
| Linux VM                 |
|                          |
| Bridger facade           |
| raw MCP: loopback only   |
| private apps             |
| Git working copies       |
| persistent state         |
+--------------------------+
```

This is the preferred first milestone. It needs no domain and no public application port.

### Public web service added intentionally

```text
Internet users
     |
 Cloudflare DNS / optional HTTP proxy
     |
  HTTPS 443
     |
 nginx or Caddy
     |
 explicitly public app
     |
+--------------------------+
| Linux VM                 |
|                          |
| private admin services --+--> Tailscale only
| Bridger raw backend -----+--> loopback only
+--------------------------+
```

Cloudflare and Tailscale solve different problems. Cloudflare can provide registrar/DNS services and proxy supported web traffic. Tailscale provides private device-to-device reachability. Neither replaces Linux permissions or application authentication.

## Runtime authority

Bridger's existing runtime architecture remains authoritative. The starter must not create a second machine-control path.

Interactive AI traffic reaches a bounded Bridger facade. Scheduled/unattended work may add [Passrail](https://github.com/TheSpyglassofOdysseus/passrail), the separate public durable-coordination project. Bridger-specific integration notes are in [`PASSRAIL.md`](PASSRAIL.md). The raw Desktop Commander backend stays on loopback.

GitHub may hold code, issues, releases, and review history. A temporary GitHub outage should not stop an already-running server from serving its applications.

## Provider boundary

Oracle Cloud is the reference provider because it offers an Always Free compute path in supported tenancies. The starter treats Oracle provisioning as one implementation of:

```text
Linux VM
+ public or routable IP as required
+ SSH key access
+ systemd
+ Python 3.11+
+ Node.js 22+
+ persistent storage
```

A VPS from another provider can replace Oracle without changing Bridger's core architecture.

## Financial boundary

The following require explicit human approval after current cost is shown:

- upgrading a cloud account to a paid account type;
- creating a resource not verified to fit current free allowances;
- increasing OCPU, RAM, disk, backups, egress, reserved IPs, or other paid capacity;
- buying or transferring a domain;
- enabling a paid Tailscale/Cloudflare/GitHub plan;
- accepting a marketplace image or software license with a charge.

Budget alerts and quotas are defense-in-depth. They do not replace understanding what is being provisioned.

## Identity and recovery boundary

A convenient SSO login can become a single point of failure. The user should know:

- how to regain Oracle account access;
- where the SSH private key is backed up;
- how to recover the Tailscale identity used by the server;
- how to recover Cloudflare/domain access;
- how to recover GitHub access;
- how to rotate Bridger credentials without rebuilding the server.

Do not store all recovery material only on the server it is meant to recover.

## Public exposure boundary

Before publishing a service, identify:

- protocol and port;
- authentication requirement;
- whether Cloudflare can proxy it;
- whether the origin must accept direct Internet traffic;
- firewall/security-list changes;
- log retention and privacy impact;
- patch/upgrade owner.

Never publish the raw MCP backend, database ports, or an administrative dashboard merely to make access convenient.

## Supply-chain boundary

The core pins its key Node dependencies and runs a release gate. Starter scripts should:

- avoid silently installing unpinned application code when practical;
- identify third-party installer scripts before running them;
- support inspection/manual package-manager installation when possible;
- validate architecture (ARM64 vs x86_64);
- keep package provenance visible.

## Done means recoverable

A working demo is not a completed deployment. Completion includes:

- reboot survival;
- config ownership/permissions checked;
- secrets absent from Git;
- intended public ports verified;
- backup completed;
- restore tested;
- rollback path documented;
- current monthly cost/free-resource assumptions recorded.
