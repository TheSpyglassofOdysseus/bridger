# Interactive low-chatter facade

Bridger's interactive facade sits between remote ChatGPT sessions and the local Desktop Commander MCP backend. It exists to keep several simultaneous chats from turning ordinary machine work into hundreds of fine-grained MCP round trips.

The raw Desktop Commander backend remains loopback-only and authoritative for detailed tool schemas. Passrail and the direct execution owner are unchanged.

## Behavior

The facade advertises a compact tool surface:

- `bridger_inspect_repo` — repository state in one bounded call;
- `bridger_inspect_service` — service state plus bounded warning/error logs;
- `bridger_read_bundle` — bounded excerpts from several files;
- `bridger_run_bounded` — ordinary command execution with limited automatic polling;
- `bridger_edit_file` and `bridger_write_file` — ordinary file mutations without exposing the full backend catalog;
- `bridger_raw_catalog` and `bridger_raw_tool` — advanced fallback discovery/invocation when the compact surface is insufficient;
- `bridger_stats` — compact in-memory facade counters.

Raw Desktop Commander tools are intentionally hidden from fresh tool discovery to reduce schema/context load and discourage fine-grained call loops. The facade still accepts legacy raw tool names for compatibility with already-open chats. Raw reads and process-output calls are bounded, and ordinary raw `start_process` calls with a meaningful timeout receive limited automatic settling.

## Backpressure and result limits

Default interactive concurrency is one host operation at a time. Multiple chats may submit work concurrently, but the facade queues the machine boundary instead of allowing overlapping Desktop Commander operations to collide.

Default response limits are 200 lines and 12,000 characters. Larger text results are written as owner-only artifacts under `~/.local/state/bridger-interactive/artifacts/`, and the chat receives a bounded preview plus the artifact path.

These limits apply only to the interactive facade. They do not change Passrail durability or the local raw backend.

## Deployment pattern

Run the raw Desktop Commander MCP listener on loopback as before. Run a second `mcp-proxy` on a separate loopback port (reference: `18879`) wrapping `bridger-interactive-facade.mjs`. Point the Secure MCP Tunnel at the facade port rather than the raw Desktop Commander port.

Keep the raw port available only on loopback for Bridger's local Actions/Passrail execution path and for rollback. Do not expose both raw and facade listeners remotely.

## Rollback

If facade health or compatibility fails, point the tunnel profile back to the raw loopback MCP listener and restart only the tunnel service. No Passrail or execution-owner migration is required.
