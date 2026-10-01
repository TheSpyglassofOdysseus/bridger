# 3. Host baseline

A successful SSH login means the VM is reachable. It does not mean the host is hardened.

Complete this step before publishing an application.

## 1. Patch

Use the package manager appropriate to your distribution.

On Ubuntu/Debian:

```bash
sudo apt update
sudo apt upgrade
```

Review major upgrades rather than automatically accepting unrelated distribution changes.

## 2. Confirm your administration account

Prefer SSH keys over passwords.

Check:

```bash
id
sudo -l
```

Know which account will own Bridger services and which operations require administrator privileges.

## 3. Protect SSH

At minimum:

- use SSH keys;
- keep a backup of the private key somewhere other than this server;
- disable unused/default credentials;
- understand whether password authentication is enabled;
- do not expose an additional SSH port merely for convenience.

After Tailscale is working, you may choose to restrict SSH to the private path. Do not lock yourself out: keep a tested cloud-console/recovery path first.

## 4. Inspect listeners

Run:

```bash
scripts/network/check-public-ports.sh
```

Every wildcard bind such as `0.0.0.0:PORT` or `[::]:PORT` deserves an explanation.

A listener existing does not necessarily mean the cloud firewall allows Internet access, but it is the first thing to investigate.

## 5. Review both firewall layers

Cloud VMs often have at least two network-control layers:

- provider security list/security group/network firewall;
- host firewall (`nftables`, `iptables`, `ufw`, or distribution tooling).

Document which one is authoritative for your deployment.

For the private-only milestone, you normally need no public application port.

## 6. Time, disk, memory

Check:

```bash
timedatectl
df -h
free -h
```

A full disk can break logs, package upgrades, SQLite state, Git, and application writes.

## 7. Automatic security updates

Decide whether to enable your distribution's automatic security-update mechanism. This is generally useful, but it does not remove the need to monitor reboots and application compatibility.

## 8. Secrets

Never put API keys or private keys in:

- Git commits;
- shell scripts checked into Git;
- command-line arguments when a protected file/environment mechanism is available;
- public issue comments;
- screenshots shared for debugging.

The Bridger reference environment file belongs outside the repository and should have restrictive ownership/permissions.

## 9. Reboot test

Before adding lots of applications, reboot once and confirm:

- SSH/private access returns;
- expected services return;
- unexpected listeners do not appear;
- disk mounts/state are present.

A simple setup is easiest to debug now, before it becomes important.
