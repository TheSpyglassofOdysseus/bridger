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

## Configure OCI CLI

Use Oracle's current installation/setup instructions rather than copying an old installer from this repository.

After setup, verify:

```bash
oci --version
oci iam region-subscription list
```

Then run the read-only helper:

```bash
scripts/oci/inspect-tenancy.sh
```

The helper does not launch or resize resources.

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
