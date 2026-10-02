# Architecture

Bridger is the authenticated machine-execution boundary. The interactive machine path is the core product. [Passrail](https://github.com/TheSpyglassofOdysseus/passrail) is an optional durable-coordination layer for scheduled/unattended work. Projects remain authoritative for business/project truth.

## Interactive core

```text
AI / MCP client
      |
authenticated bounded edge
      |
compact Bridger facade or Actions adapter
      |
loopback mcp-proxy
      |
Desktop Commander
      |
managed host
```

The raw Desktop Commander MCP listener stays on loopback. The compact facade reduces discovery/context load; `bridge-gpt-actions.py` retains the legacy broad interactive Actions facade for clients that need it. Its `X-Bridge-Key` is high authority.

## Optional durable/scheduled path

Passrail is not required for interactive Bridger. When enabled, the target durable path is:

```text
scheduled/app client
        |
  narrow Passrail ingress
        |
   Passrail SQLite
        |
 local executor claim
        |
 short-lived exact-request execution grant
        |
 owner-only Unix socket
        |
 Bridger execution owner + ledger
        |
 loopback Actions -> MCP -> host
        |
 execution receipt
        |
 project postcondition verification
        |
 Passrail settlement / reconciliation
```

GitHub is not required in this target runtime path. It may remain source/review/release authority.

## Narrow Passrail ingress

`bridge_passrail_ingress.py` exposes only durable work publication and per-item status retrieval. It does not expose host-control tools.

- separate `X-Passrail-Key` credential;
- explicit allowed-project set;
- accepts only `passrail-bridger-execution-v1` / `bridger-executor` work;
- direct request and risk/completion-policy validation before publication;
- consequential work requires canonical authority reference/version and reconciliation policy;
- returns a per-item HMAC status capability rather than allowing queue/database enumeration.

The ingress credential cannot authenticate legacy machine-control routes, and the legacy Bridge credential cannot authenticate Passrail routes.

## Passrail execution authority

A local worker claims `bridger-executor` work. The raw 256-bit claim token stays inside Passrail. `Rail.mint_execution_grant()` verifies the current unexpired claim and emits a short-lived HMAC grant bound to:

- Passrail item/project/message identity;
- immutable envelope hash;
- attempt number;
- concrete Bridger execution ID;
- normalized request SHA-256 + tool;
- requested risk class;
- Bridger audience;
- issued-at and expiry.

Grant expiry is capped by claim lease expiry. A stale worker cannot initiate a new dispatch after its execution authority expires.

## Local execution boundary

The direct adapter uses an owner-only Unix domain socket, not TCP. The socket is `0600`, its parent is owner-only, and Bridger validates Linux peer UID with `SO_PEERCRED`.

The existing mailbox process remains the **single execution-ledger owner** during compatibility migration. Both legacy GitHub traffic and direct Passrail traffic therefore cross one replay/ambiguity boundary rather than maintaining separate execution state machines.

## Transport-neutral execution ledger

`bridge_execution_ledger.py` owns concrete machine-attempt safety:

- durable `EXECUTING` before dispatch;
- execution identity bound to request SHA-256 + tool + optional Passrail work/attempt authorization SHA-256;
- exact authorized replay returns the terminal record rather than dispatching again;
- changed request or authority binding hard-conflicts;
- trustworthy host response -> `SUCCEEDED`;
- pre-dispatch policy/freshness rejection -> `REJECTED` without host call;
- ambiguous host call or restart with in-flight work -> `UNKNOWN_OUTCOME`;
- owner-only state and owner lock;
- one active execution owner at a time.

The legacy GitHub adapter is forbidden from adopting a ledger execution carrying a Passrail authorization binding.

## Settlement semantics

A Bridger receipt describes **one machine attempt**, not completion of the whole project work item.

- Read-only `SAFE_RETRY` work may auto-complete Passrail after a trustworthy `SUCCEEDED` receipt.
- Consequential work must be `NO_AUTO_RETRY` and requires project authority/version precheck.
- A consequential Bridger `SUCCEEDED` receipt moves Passrail to `UNKNOWN_OUTCOME` / `AWAITING_RECONCILIATION`, not directly to `DONE`.
- A project adapter must re-read canonical project truth and use explicit evidence-driven `reconcile_unknown()` before the work becomes `DONE` or known `FAILED`.
- The original ambiguity transition/receipt remains immutable in history.

Lease expiry is authority loss for **new dispatch**, not rollback of an already-started host effect.

## GitHub compatibility adapter

During migration only:

```text
Scheduled Task -> private GitHub issue -> compatibility adapter
              -> same Bridger execution ledger -> host
              -> GitHub receipt projection
```

GitHub owns request provenance/receipt delivery for this compatibility path. It does not own execution state. After the direct path is independently proven for scheduled workers, the mailbox can be disabled without changing Passrail or the execution ledger.
