# Run a small CI job on a VPS

This example uses a systemd timer. It is suitable for one trusted VPS and one
repository. Use a full CI system when you need webhooks, queues, isolated
workers, a user interface, or managed artifacts.

## 1. Prepare the project

Create `/srv/example-project/scripts/ci.sh`. The script must return a nonzero
status when a check fails.

```sh
#!/bin/sh
set -eu

git fetch --prune origin
git checkout --detach origin/main
python -m pytest
./scripts/deploy.sh
```

Set its permissions:

```sh
chmod 0755 /srv/example-project/scripts/ci.sh
```

## 2. Install the wrapper

Install `quiet-run` in a path that the service can use:

```sh
python3 -m venv /opt/agent-quiet-run
/opt/agent-quiet-run/bin/python -m pip install \
  git+https://github.com/miningstore/agent-quiet-run.git
```

Copy `examples/systemd/run-project-ci.sh` to
`/usr/local/libexec/agent-quiet-run/run-project-ci.sh`. Set mode `0755`.

## 3. Install the systemd units

Copy these files:

- `examples/systemd/quiet-ci.service` to `/etc/systemd/system/quiet-ci.service`
- `examples/systemd/quiet-ci.timer` to `/etc/systemd/system/quiet-ci.timer`

Change the service user, group, and project path for your VPS. Then enable the
timer:

```sh
systemctl daemon-reload
systemctl enable --now quiet-ci.timer
```

## 4. Check a run

The system journal contains only the start and completion JSON records:

```sh
journalctl -u quiet-ci.service -n 20 --no-pager
```

The complete command output is in `/var/lib/agent-quiet-run/`. Read a bounded
part of a failed log:

```sh
tail -n 100 /var/lib/agent-quiet-run/ci-*.log
```

## Migration checklist

Map each GitHub Actions feature before you remove a workflow:

1. Map each trigger to a timer, webhook receiver, or manual service start.
2. Store secrets in a root-owned systemd credential or environment file.
3. Add a lock when two runs must not overlap.
4. Set a timeout for each command.
5. Define log and artifact retention.
6. Add failure notifications.
7. Test failure, timeout, restart, and rollback behavior.
8. Keep the old workflow until the VPS path completes an accepted run.
