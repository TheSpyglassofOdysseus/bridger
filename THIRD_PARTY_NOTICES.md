# Third-party notices

Bridger intentionally reuses mature MCP infrastructure instead of reimplementing it.

- `@modelcontextprotocol/sdk` 1.30.0 — MIT License.
- `@wonderwhy-er/desktop-commander` 0.2.50 — MIT License.
- `mcp-proxy` 6.7.18 — MIT License.

The packages are installed from npm and remain subject to their own copyright notices and license terms. Bridger does not vendor their source code.

## Security overrides

The npm lockfile currently overrides two transitive packages to patched versions:

- `sharp` 0.35.4
- `uuid` 11.1.1

These overrides are intentional. The publication gate verifies `npm audit --omit=dev` reports zero known vulnerabilities and performs a real MCP initialize/tools/read/process compatibility probe before release.

## Transitive deprecation notices

A fresh `npm ci` currently emits deprecation notices from several transitive packages pulled by the pinned upstream dependency graph (including older `glob`/routing/filesystem helper packages). The reviewed public candidate still reports **0 known vulnerabilities** from `npm audit --omit=dev`.

Those notices are tracked as dependency-maintenance debt rather than hidden from users. Upstream dependency upgrades should be reviewed and compatibility-tested instead of being floated automatically just to silence install output.
