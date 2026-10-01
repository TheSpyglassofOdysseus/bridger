# Starter counter-review

This document records the objections that shaped the public starter. It exists so future simplification does not accidentally remove an important safety or portability property.

## 1. Do not make Oracle a hard dependency

**Risk:** The tutorial becomes unusable when Oracle capacity, eligibility, or product terms change.

**Decision:** Oracle is the flagship provisioning path. Bridger itself targets a compatible Linux host.

## 2. Do not promise the original reference VM size

**Risk:** Free-tier allowances and capacity vary over time and by tenancy.

**Decision:** Discover the user's current entitlement and verify current provider documentation. Example sizes are labeled as examples, not guarantees.

## 3. Do not call every console failure an Oracle bug

**Risk:** Capacity exhaustion can look like a provisioning failure.

**Decision:** Preserve the original CLI-success story, but distinguish documented host-capacity errors from a reproducible software defect.

## 4. Do not require a domain

**Risk:** A domain introduces cost, renewal/account recovery, DNS complexity, and temptation to expose services publicly.

**Decision:** Private Tailscale-only operation is a complete supported setup. Domain + Cloudflare is the recommended public-web path.

## 5. Do not confuse Cloudflare with a private network

**Risk:** Users may publish SSH, databases, or admin interfaces because they believe Cloudflare DNS protects them.

**Decision:** Tailscale is the private administration path. Cloudflare is registrar/DNS and, where supported, a web proxy.

## 6. Do not expose raw Bridger/Desktop Commander

**Risk:** The backend intentionally has powerful filesystem/process access.

**Decision:** Keep raw listeners on loopback. Expose only the bounded/authenticated path required by the client architecture.

## 7. Do not let AI cross financial boundaries silently

**Risk:** Cloud upgrades, domain registrations, larger disks, egress, backups, or paid software can create charges.

**Decision:** Show current price and exact proposed resource, then require explicit human approval.

## 8. Do not assume ARM compatibility

**Risk:** Oracle A1 is ARM64. Some binaries, containers, browser dependencies, native Node/Python packages, or third-party installers may be x86-only.

**Decision:** Every recipe that installs nontrivial software should state/test supported architectures and provide an alternate path.

## 9. Do not treat SSH login as host hardening

**Risk:** A newly reachable VM still needs patching, key hygiene, firewall review, least privilege, and service exposure checks.

**Decision:** The host-baseline step occurs before public application exposure.

## 10. Do not rely on Tailscale as the only security control

**Risk:** Tailnet membership does not fix overpowered local accounts, weak app auth, stale packages, or leaked secrets.

**Decision:** Tailscale reduces network exposure; Linux/application controls remain necessary.

## 11. Do not call a backup complete until restore works

**Risk:** Credentials expire, paths drift, archives omit state, or backups are encrypted with keys that were not preserved.

**Decision:** The starter requires a test restore of at least one representative file/state artifact and documents full rebuild recovery.

## 12. Do not make GitHub runtime-critical

**Risk:** Source hosting becomes a fragile command bus and outage dependency.

**Decision:** GitHub remains source, review, distribution, and optional off-host recovery.

## 13. Do not hide secrets in convenience scripts

**Risk:** Shell history, process arguments, logs, Git, and generated config can leak high-authority credentials.

**Decision:** Generate/store secrets in protected files, redact diagnostics, and document rotation.

## 14. Do not skip account recovery

**Risk:** SSO/TOTP/device loss can strand a server or domain even when the machine itself is healthy.

**Decision:** Each external control plane gets a recovery note: Oracle, Tailscale, Cloudflare/registrar, GitHub, and the AI provider.

## 15. Do not skip cold-start testing

**Risk:** A setup can work interactively but fail after reboot because of service order, missing environment, user-systemd lingering, mounts, or DNS/network timing.

**Decision:** A reboot/cold-start acceptance check is part of completion.

## 16. Do not make installer magic irreversible

**Risk:** Beginners cannot reason about or undo what a one-command installer changed.

**Decision:** Bootstrap scripts should be readable, idempotent where practical, print what they changed, and pair with uninstall/rollback guidance.

## 17. Do not publish personal infrastructure accidentally

**Risk:** Hostnames, domains, IPs, paths, tokens, operational mailbox coordinates, and incident logs can leak through a public release.

**Decision:** Publication gate includes a secret/private-coordinate scan and uses placeholders in examples.

## 18. Do not confuse "AI-readable" with "AI-authorized"

**Risk:** A clear handoff file can make an agent fast enough to do the wrong thing.

**Decision:** `AI_HANDOFF.md` defines authority boundaries, approval gates, inspection-first behavior, and completion tests.

## 19. Do not treat one Oracle documentation page as the billing authority

**Risk:** Oracle's public pages can describe different A1 monthly allowances at the same time.

**Decision:** Record the inconsistency, inspect the user's actual tenancy/account entitlements and billing view, and never select the more generous published number as a provisioning assumption.

## 20. Do not assume an Always Free VM is permanent capacity

**Risk:** Oracle documents reclamation criteria for idle Always Free compute.

**Decision:** Warn users about current idle-resource policy, keep rebuild/restore practical, and do not put irreplaceable state only on the free VM.

## 21. Do not hide registrar lock-in details

**Risk:** A user buys through Cloudflare Registrar and only later discovers the domain must use Cloudflare authoritative nameservers while registered there.

**Decision:** Explain the nameserver requirement and registrant-email verification before purchase.

## Release acceptance for the starter layer

Before calling the starter shareable:

- run the existing `scripts/check.sh` core gate;
- run `bash -n` on every shell script;
- run documentation/link sanity checks where available;
- test the release-certified path on a fresh ARM64 Linux environment;
- label x86_64 experimental until it independently passes the same clean-room gate;
- test the private-only path with no domain;
- test the public-web path with a disposable subdomain before using a production domain;
- test restore;
- test reboot;
- have a second proficient AI user follow `START_HERE.md` without access to the author's conversation history.
