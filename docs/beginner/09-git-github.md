# 9. Git and GitHub

Git records what changed. GitHub is an optional remote home for that history, collaboration, releases, and recovery.

Bridger does not require GitHub as its steady-state runtime command bus.

## Start with local Git

For a new project:

```bash
git init
git status
```

Before committing, create a `.gitignore` that excludes secrets, generated state, logs, caches, and large artifacts.

## Before the first push

Search for:

- API keys/tokens;
- private keys;
- passwords;
- real IP addresses/hostnames you do not want public;
- `.env` files;
- cloud credentials;
- Tailscale auth keys;
- Cloudflare API tokens;
- operational SQLite/state files;
- production logs;
- private mailbox/queue coordinates.

Removing a secret from the latest commit does not necessarily remove it from Git history. Rotate leaked credentials.

## Public vs private repository

Use a private repository until you have deliberately completed a publication review.

The Bridger core release checklist is in [../RELEASE.md](../RELEASE.md).

## Source is not state

Do not assume Git contains everything required to restore a server.

Applications may also depend on:

- databases;
- uploaded files;
- environment/secrets;
- systemd configuration;
- reverse-proxy configuration;
- certificates;
- DNS;
- cloud resources.

Document those separately and back up the durable state.
