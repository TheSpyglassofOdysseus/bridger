# 8. Publish a web service intentionally

Do this only after the private path works.

## Public-service checklist

For each service you intend to publish, write down:

- hostname;
- protocol;
- external port;
- local upstream address/port;
- authentication model;
- whether Cloudflare proxying is enabled;
- TLS termination point;
- log location;
- owner/upgrade process.

If you cannot fill that out, the service is not ready to publish.

## Reverse proxy

Bridger includes an nginx example for its authenticated edge. For your own apps, nginx or Caddy can terminate HTTPS and forward traffic to a loopback application.

Prefer:

```text
Internet -> HTTPS 443 -> reverse proxy -> 127.0.0.1:application-port
```

over:

```text
Internet -> random application port -> application
```

## Optional alternative: Cloudflare Tunnel

For an intentionally public web application, Cloudflare Tunnel is another ingress pattern. The `cloudflared` daemon makes outbound connections to Cloudflare and can map a public hostname to a local service without opening an inbound application port or requiring a public origin IP.

This can reduce origin exposure, but it adds another service, credential, and external dependency. It is **not** the private administration network in this starter; Tailscale remains the recommended private path.

Use current Cloudflare Tunnel documentation if you choose this architecture rather than copying an old tunnel token/command from someone else's deployment.

## Keep management separate

Do not publicly expose:

- raw Desktop Commander MCP;
- databases;
- development servers;
- internal metrics with sensitive data;
- admin dashboards merely for convenience;
- filesystem browsers or terminals.

Use Tailscale for these unless you have a deliberate, reviewed reason not to.

## DNS verification

After adding DNS:

```bash
scripts/network/verify-dns.sh your-hostname.example.com
```

After HTTPS is configured:

```bash
scripts/network/verify-https.sh https://your-hostname.example.com/
```

These are reachability checks, not penetration tests.

## Origin firewall

If you use Cloudflare proxying for a public site, decide whether the origin should accept traffic from the entire Internet or only from appropriate sources. Cloudflare publishes IP ranges and guidance, but blindly restricting an origin can lock you out or break certificate flows depending on your architecture.

Treat origin filtering as a separate reviewed hardening step.

## Logs and privacy

Public applications attract scanners quickly.

Know:

- what requests you log;
- whether logs contain tokens/query strings/IP addresses;
- how long logs are retained;
- how logs are rotated.

Do not paste production logs into a public AI conversation without reviewing them for secrets/personal data.
