# 10. Backup and recovery

A backup job saying "success" is not the same thing as being recoverable.

## Separate three things

### Source

Git repositories and release artifacts.

### Configuration/secrets

Environment files, systemd overrides, reverse-proxy configuration, secret keys, certificates where applicable.

### Durable application state

Databases, uploads, user-created content, queues/ledgers, and other runtime state that cannot be recreated from Git.

Back them up according to their sensitivity and change rate.

## Off-host requirement

At least one useful recovery copy must live somewhere other than the VM.

A deleted/corrupted server cannot restore from a backup that existed only on that server.

## Encryption and keys

If backups are encrypted, store the recovery key separately from the backup destination and separately from the server.

Losing the key is equivalent to losing the backup.

## Restore test

At minimum:

1. choose a representative backed-up file or small state bundle;
2. restore it to a temporary location;
3. compare it with the expected content;
4. record the date and result.

For important applications, perform a full restore into a disposable environment.

## Rebuild document

You should be able to rebuild the host from:

- provider account;
- SSH/recovery credentials;
- this repository/release;
- protected configuration/secrets;
- application source;
- durable-state backup;
- DNS/domain account;
- written service inventory.

## Recovery priority

During an incident:

1. stop additional destructive changes;
2. preserve evidence/state;
3. determine whether credentials are compromised;
4. rotate compromised credentials;
5. restore a known-good version/state;
6. verify private access;
7. verify public exposure;
8. verify application correctness;
9. document what happened.

Do not let an AI repeatedly "try fixes" against irreplaceable state without snapshots/backups.
