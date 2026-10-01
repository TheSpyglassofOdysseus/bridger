# 6. Connect your AI

Bridger is intentionally **AI-client agnostic**. ChatGPT, Claude, Codex, and other MCP-capable clients may use different registration/authentication flows.

Those client flows change faster than Bridger should.

## Stable rule

Whatever client you use:

> The remote AI reaches an authenticated, bounded Bridger edge. The raw Desktop Commander MCP backend remains loopback-only.

Do not solve connectivity by exposing the raw MCP port to the Internet.

## Before configuring a client

Confirm:

- Bridger's local canaries work;
- Tailscale/private administration works;
- you know which Bridger endpoint the client is meant to reach;
- its credential is separate from unrelated secrets;
- the raw backend still binds only to loopback.

## ChatGPT

Use OpenAI's **current** MCP/plugin/connector documentation for the supported connection method available to your account.

Do not copy a historical tunnel registration ID, plugin ID, API key, or account-specific configuration from the reference deployment.

If the current ChatGPT connection mechanism requires a public HTTPS endpoint, expose only the intended authenticated Bridger edge through your reverse proxy/tunnel. Keep the backend on loopback.

## Other AI clients

For another MCP-capable client, use that client's current official MCP documentation.

The AI client may run:

- on your laptop and reach Bridger privately through Tailscale;
- through a supported authenticated remote MCP/tunnel mechanism;
- through another bounded adapter you deliberately configure.

## Use the AI handoff

Once the client can access the repository/context, give it [../../AI_HANDOFF.md](../../AI_HANDOFF.md).

A useful first instruction is:

```text
Read AI_HANDOFF.md, SECURITY.md, docs/THREAT-MODEL.md, and
docs/INTERACTIVE-FACADE.md. Inspect this Bridger deployment without changing
anything. Verify which listeners are public, which are Tailscale-only, which
are loopback-only, and run only harmless read/process canaries.
```

## Do not call it connected until

- authentication failure is fail-closed;
- the client can execute a harmless canary;
- a wrong/missing credential cannot;
- raw MCP remains loopback-only;
- the user knows how to revoke/rotate the remote credential.

After that, the server is useful. A domain or Passrail is optional.
