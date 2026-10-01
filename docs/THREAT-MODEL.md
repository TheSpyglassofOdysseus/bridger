# Threat model

Bridger deliberately crosses from AI/client intent into powerful host filesystem and process operations. The security goal is not to call that harmless; it is to separate authorities, authenticate every boundary, bound inputs, make replay/ambiguity explicit, and keep high-value secrets off third-party runtime transports.

## Assets

- Host filesystem and processes.
- The `ubuntu` service account and its effective OS permissions.
- MCP backend key and legacy interactive `BRIDGE_ACTIONS_KEY`.
- Narrow `BRIDGE_PASSRAIL_INGRESS_KEY`.
- Local Passrail claim capabilities and database.
- Local execution-grant HMAC key.
- Execution-attempt ledger, owner lock, receipts, and project authority evidence.
- Legacy private GitHub mailbox contents while compatibility mode remains enabled.

## Trust boundaries

### Interactive compatibility path

`remote client -> TLS/auth edge -> loopback Actions/MCP -> host`

The legacy `X-Bridge-Key` is a **high-authority machine-control credential**. A holder may reach named filesystem/process actions and the generic compatibility route. Protect and rotate it accordingly. It is not the credential intended for unattended scheduled work.

### Narrow scheduled/app ingress

`remote client -> TLS edge -> Passrail ingress -> local Passrail DB`

The separate `X-Passrail-Key` can only publish allowlisted `bridger-executor` work and read an item for which the caller also holds the returned per-item status capability. The narrow Passrail OpenAPI surface contains no host-control routes. The Passrail key is deliberately rejected by legacy machine-control endpoints, and the legacy Bridge key is deliberately rejected by Passrail endpoints.

Compromise of this ingress key is still serious: an authorized caller may enqueue schema-valid work for allowlisted projects. It is a reduced capability, not a sandbox. Keep the project allowlist narrow and rotate the key on suspected exposure.

### Local Passrail -> Bridger execution boundary

`Passrail claim -> short-lived execution grant -> owner-only Unix socket -> Bridger execution owner -> loopback Actions/MCP -> host`

- Raw Passrail claim tokens terminate at Passrail and are never sent to Bridger.
- Passrail mints a short-lived HMAC grant only from a matching live claim.
- The grant binds project/work identity, immutable envelope hash, attempt, execution ID, exact normalized request digest, tool, risk class, audience, and expiry.
- Grant expiry is no later than claim lease expiry.
- Bridger verifies the grant again immediately before dispatch.
- The execution-grant key is a local owner-only file and is never exposed through remote APIs.
- The Unix socket is owner-only (`0600`), its parent directory is owner-only, and Linux `SO_PEERCRED` must report the same UID as the Bridger execution owner.
- Direct and legacy GitHub adapters share the same execution ledger. Cross-transport reuse of a Passrail-authorized execution by the GitHub adapter is rejected.

No new TCP/Tailscale listener is introduced for Passrail -> Bridger execution.

## Execution/replay defenses

- Request/tool arguments are bounded before host dispatch.
- The execution ledger persists `EXECUTING` before dispatch.
- Execution identity is bound to request digest, tool, and Passrail work/attempt authorization when applicable.
- Exact authorized replay returns the existing terminal execution instead of repeating the host effect.
- Changed request, changed work/attempt authority, or conflicting execution ID fails closed.
- Consequential host tools require `NO_AUTO_RETRY` on the direct path.
- Host-call ambiguity or process death becomes `UNKNOWN_OUTCOME`; it is never automatically replayed.
- A successful consequential machine call is not sufficient for Passrail `DONE`: project postcondition reconciliation is required.
- Passrail reconciliation preserves the original ambiguity evidence rather than rewriting history.

## GitHub compatibility boundary

The private GitHub mailbox remains a rollback/compatibility adapter during migration. GitHub owns transport provenance for that path only; it does not own execution state. The target state removes GitHub from scheduled runtime execution after direct Passrail cutover evidence passes. Git may still remain source/review/release authority.

## What this does not protect against

- A fully compromised `ubuntu` account defeats same-user local file/socket capability separation.
- A compromised legacy `BRIDGE_ACTIONS_KEY` can exercise broad machine-control authority.
- A malicious but authorized narrow-ingress caller can enqueue allowed work; grant/replay defenses stop stale/tampered/replayed authority, not malicious intent authorized by policy.
- Desktop Commander is intentionally powerful and the reference service is not an OS sandbox. Its effective permissions and local policy remain part of the blast radius.
- Lease expiry cannot roll back an action that already crossed the machine-effect boundary.
- None of these controls imply generic exactly-once execution or “zero trust.”

Use a dedicated OS account where practical, keep secrets owner-only and out of repositories/logs, minimize allowed projects/tools, preserve project-specific authority checks, and treat any public edge in front of Bridger as security-critical infrastructure.
