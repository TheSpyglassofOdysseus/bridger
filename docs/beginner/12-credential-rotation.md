# 12. Rotate and revoke credentials

A deployment is not complete until you know how to remove access.

Bridger uses separate credentials for separate authority levels. Do not reuse one value for multiple roles.

## Interactive credential

`BRIDGE_ACTIONS_KEY` is high-authority machine-control access.

To rotate it:

1. generate a new high-entropy value locally without printing it into chat/logs;
2. update the protected environment file atomically;
3. restart only the service that loads that credential;
4. verify a request using the **old** credential returns `401`;
5. verify the **new** credential succeeds on a harmless read canary;
6. update the authorized client;
7. remove any temporary copy of the old/new value from shell history or scratch files.

If you cannot prove the old credential fails, do not consider the rotation complete.

## Passrail ingress credential

If you use the optional durable-work layer, rotate `BRIDGE_PASSRAIL_INGRESS_KEY` separately.

After rotation:

- the old Passrail key must not publish or query work;
- the new key must be able to perform only the narrow Passrail operations;
- the Passrail key must still fail against interactive machine-control routes.

## MCP/tunnel/client credentials

The exact connection mechanism may have its own credential, API key, OAuth client, tunnel key, or registration.

Use that provider/client's current revocation procedure. Do not copy identifiers or keys from the reference deployment.

## Emergency revocation

If a credential may be compromised:

1. revoke/replace the credential first;
2. disable the public/tunnel edge if immediate revocation is uncertain;
3. preserve logs/state needed to understand what happened;
4. inspect for unexpected changes;
5. rotate adjacent credentials if the compromised secret could have exposed them;
6. restore from known-good state if integrity is uncertain.

Do not merely remove a leaked value from Git or chat history and continue using it.

## Acceptance

Before relying on Bridger for important work, prove:

- old interactive key: rejected;
- new interactive key: harmless canary succeeds;
- old Passrail key (if enabled): rejected;
- new Passrail key: narrow operations only;
- raw MCP remains loopback-only;
- you know how to disable the remote edge entirely.

The automated test suite includes explicit old-key-rejected/new-key-accepted checks for the interactive and Passrail HTTP credentials.
