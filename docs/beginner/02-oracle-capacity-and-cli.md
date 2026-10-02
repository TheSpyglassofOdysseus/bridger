# 2. Oracle capacity and OCI CLI

This chapter exists because the original Bridger deployment could not obtain the desired server through the normal Oracle web-console flow. The successful path used OCI CLI.

That is an experience report, not proof that every console failure is a software bug.

## First: identify the failure

Oracle currently documents an `out of host capacity` error for Always Free compute. Oracle recommends trying another availability domain where the region has more than one, waiting and trying later, or considering a paid account type.

Official reference:

https://docs.oracle.com/en-us/iaas/Content/FreeTier/freetier_topic-Always_Free_Resources.htm

Do not change shapes, account type, storage, or region blindly just to make the error disappear.

## Why use OCI CLI?

OCI CLI can make the cloud state explicit. It can enumerate:

- configured region;
- tenancy/compartment identifiers;
- availability domains;
- compute shapes;
- images;
- subnets;
- capacity information;
- the exact launch request you intend to make.

Oracle also provides a compute capacity report API/CLI specifically to report host capacity within an availability domain:

https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/compute/compute-capacity-report.html

## Easiest path: Oracle Cloud Shell

For a beginner, the fastest way to get a trustworthy OCI CLI is usually **Oracle Cloud Shell**:

https://docs.oracle.com/en-us/iaas/Content/API/Concepts/cloudshellintro.htm

Cloud Shell is available from the Oracle Console, includes the OCI CLI, and is already authenticated for your account. That avoids installing Python packages or creating a local API signing key just to inspect the tenancy.

In Cloud Shell, verify:

```bash
oci --version
oci iam region-subscription list
```

Then download/run Bridger's read-only inspector:

```bash
curl -fsSLO https://raw.githubusercontent.com/TheSpyglassofOdysseus/bridger/main/scripts/oci/inspect-tenancy.sh
bash inspect-tenancy.sh
```

The helper does not create, resize, terminate, or upgrade resources.

## Local OCI CLI: best for deeper AI-driven provisioning

If your AI can safely operate a terminal on your own computer, installing OCI CLI locally can make provisioning much smoother because the AI can inspect the tenancy, compose the exact launch request, and verify the result through the same API Oracle's Console uses.

Oracle's current OCI CLI quickstart:

https://docs.oracle.com/en-us/iaas/Content/API/SDKDocs/cliinstall.htm

After installation, configure authentication with Oracle's supported setup flow, for example:

```bash
oci setup bootstrap
```

or:

```bash
oci setup config
```

Do not paste OCI private keys, API signing keys, security tokens, or the contents of `~/.oci/config` into chat or Git. The AI only needs access to the CLI in the authorized environment; it does not need the raw credential material in the conversation.

After setup:

```bash
oci --version
scripts/oci/inspect-tenancy.sh
```

## AI provisioning rule

Before the AI launches anything, it should first show you:

- detected home region;
- availability domains;
- current A1 shape visibility;
- current tenancy/service limits and existing usage;
- proposed OCPU and RAM;
- proposed boot/block storage;
- image and architecture;
- expected free/paid status under Oracle's **current** documentation;
- the exact launch command it intends to run.

As of 2026-10-01, Oracle's published Always Free A1 baseline is **2 OCPUs / 12 GB RAM**, with **200 GB total combined boot + block volume storage** in the home region. The original Bridger server used the older **4 OCPU / 24 GB / 200 GB** entitlement; do not use that historical size as the default for a new tenancy.

Only after the human approves the exact free/billing boundary should the AI create the VM.

## Capacity strategy

Use this order:

1. verify the tenancy home region;
2. list availability domains;
3. verify `VM.Standard.A1.Flex` is currently offered in the tenancy/region;
4. inspect current capacity;
5. confirm the requested OCPU/RAM/storage fits the current free allowance if free operation is the goal;
6. make one explicit launch attempt;
7. if capacity is unavailable, use a bounded retry schedule rather than rapid API polling.

## Pay As You Go is a financial boundary

Oracle says upgrading can provide access to more compute resource types while eligible Always Free resources remain free within their limits.

But a paid account type can also create billable resources.

Before upgrading:

- read Oracle's current billing terms;
- configure budget alerts and/or compartment quotas where appropriate;
- identify the exact resources you expect to remain free;
- understand boot volume, backup, public IP, egress, and other possible charges;
- get explicit human approval.

Do not let an AI perform the upgrade silently.

## Do not blindly replay launches

A timeout is not proof that a launch failed. Before resubmitting, inspect the instance list and work requests. Duplicate infrastructure is an avoidable cost and security problem.

## What to record

Keep a local/private setup note with:

- tenancy name (not secret);
- home region;
- compartment used;
- subnet/VCN used;
- instance OCID;
- shape;
- architecture;
- assigned public/private/Tailscale addresses;
- expected free/paid status at creation time.

Do not put sensitive tenancy credentials or private keys in a public repository.
