# 1. Choose and provision compute

Bridger needs a Linux host you control. Oracle Cloud is the reference path, not a hard dependency.

## Minimum practical requirements

Use a Linux distribution with systemd and support for:

- Python 3.11 or newer;
- Node.js 22 or newer;
- Git;
- enough RAM/storage for Bridger plus whatever you build;
- outbound HTTPS;
- SSH or another recoverable administration path.

Bridger itself is small. Your applications may not be.

## Reference path: Oracle Cloud

Oracle documents Always Free compute resources in the tenancy's **home region**.

Do **not** hard-code a presumed A1 allowance from this repository. As of 2026-09-30, Oracle's own public documentation is not fully consistent: the Free Tier resource page describes one A1 allowance while Oracle's Arm Compute page describes a larger monthly A1 allowance. Treat the tenancy/console, current account entitlements, and Oracle's current billing view as the authority for what you can actually provision without charge.

Check both current Oracle references before provisioning:

https://docs.oracle.com/en-us/iaas/Content/FreeTier/freetier_topic-Always_Free_Resources.htm

https://docs.oracle.com/en-us/iaas/Content/Compute/References/arm.htm

The original Bridger reference deployment may have a different allocation from what a new tenancy receives today.

Oracle's Free Tier documentation also warns that idle Always Free compute instances may be reclaimed under Oracle's published idle-resource criteria. If continuity matters, verify the current reclamation policy and do not treat a free VM as guaranteed permanent capacity.

## Architecture warning: A1 is ARM64

`VM.Standard.A1.Flex` uses Ampere Arm processors.

Bridger v0.1 is release-certified on **ARM64 Linux**. x86_64 is an expected portability target, but should be treated as experimental until a clean x86_64 host passes the same release gate.

Before choosing A1, remember that software you later install must support `aarch64/arm64`. Python, Node.js, nginx, Tailscale, and ordinary Linux packages generally have ARM builds, but a third-party binary, container image, browser package, database extension, or vendor agent may not.

Check your host architecture with:

```bash
uname -m
```

Common results:

- `aarch64` / `arm64`: ARM64;
- `x86_64` / `amd64`: x86-64.

## Provisioning checklist

Before launching a VM, write down:

- provider;
- account/tenancy;
- region;
- availability domain or zone;
- image and architecture;
- shape/instance type;
- OCPUs/vCPUs;
- RAM;
- boot disk size;
- expected monthly price at current usage;
- whether the configuration is verified to fit a current free allowance;
- SSH public key being installed.

If any field is unknown, inspect it before clicking Create or running a launch command.

## If Oracle capacity is unavailable

Do not repeatedly click Create.

Read [02-oracle-capacity-and-cli.md](02-oracle-capacity-and-cli.md). Oracle explicitly documents temporary `out of host capacity` errors for Always Free shapes.

## Other providers

A small VPS from another provider is valid. Keep the same architecture:

```text
Linux VM -> private admin network -> Bridger -> your projects
```

The provider may change. Bridger's trust boundaries should not.
