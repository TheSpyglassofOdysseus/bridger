# Hello server

A deliberately tiny first service.

By default it listens only on `127.0.0.1:8080`.

```bash
python3 server.py
curl http://127.0.0.1:8080/
```

To make it reachable directly on the Tailscale interface without binding to all interfaces, obtain the server's Tailscale IPv4 address:

```bash
tailscale ip -4
```

Then, for a temporary test:

```bash
BIND_HOST=<tailscale-ip> PORT=8080 python3 server.py
```

Verify from another trusted device on the same tailnet.

Do **not** use `BIND_HOST=0.0.0.0` merely because it is easier. On a cloud VM that can unintentionally make the process reachable on public interfaces depending on firewall rules.

Once the behavior is understood, ask your AI to create a dedicated systemd service with:

- an unprivileged service user where practical;
- explicit working directory;
- explicit Tailscale or loopback bind;
- restart policy;
- no secrets in the unit file;
- journal logging;
- documented stop/disable/rollback commands.

The purpose is to learn the service lifecycle before building something important.
