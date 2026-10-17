# agent-quiet-run

`agent-quiet-run` runs a noisy command and emits only two small JSON records:
one when the command starts and one when it ends. It writes the full stdout and
stderr stream to a private log.

This keeps long VPS, deployment, test, and CI waits out of a coding agent's
context. The agent can poll the wrapper without receiving repeated status
output. If the command fails, the agent can read only the needed part of the
log.

## What it does

- Writes combined stdout and stderr to a new mode-`0600` log.
- Refuses to replace an existing log.
- Returns the child command's exit status.
- Stops the child process group after a required timeout.
- Stops the child process group when the wrapper receives `SIGHUP`, `SIGTERM`,
  or an interrupt.
- Reports elapsed time, log size, and the log SHA-256 digest.
- Keeps the command and its arguments out of lifecycle output.
- Uses only the Python standard library.

The current release supports Linux and macOS with Python 3.10 or later.

## Install

Install from GitHub with `pipx`:

```sh
pipx install git+https://github.com/miningstore/agent-quiet-run.git
```

You can also clone the repository and install it in a virtual environment:

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install .
```

## Use

Put the command after `--`:

```sh
quiet-run \
  --label vps-tests \
  --log "$HOME/.local/state/agent-quiet-run/vps-tests-$(date -u +%Y%m%dT%H%M%SZ)-$$.log" \
  --timeout-seconds 1800 \
  -- ssh deploy@example-vps 'cd /srv/app && ./scripts/test.sh'
```

The wrapper prints a start record:

```json
{"label":"vps-tests","log_path":"/home/user/.local/state/agent-quiet-run/vps-tests-20261017T120000Z-321.log","pid":9021,"status":"started"}
```

It prints one completion record:

```json
{"elapsed_seconds":84.214,"exit_code":0,"interrupted":false,"label":"vps-tests","log_bytes":18890,"log_path":"/home/user/.local/state/agent-quiet-run/vps-tests-20261017T120000Z-321.log","log_sha256":"...","status":"completed","termination_signal":null,"timed_out":false}
```

The child output does not enter the wrapper's stdout or stderr.

## Agent wait pattern

Start `quiet-run` in a persistent terminal session. Let the first command wait
for no more than 30 seconds. Poll the same session every 30 to 60 seconds with
a small output limit. Unchanged polls return no text. Read the private log only
after a failure or when a specific diagnostic is necessary.

In one 2,000-line test, the child produced 18,890 bytes. The two lifecycle
records used 455 bytes. This reduced agent-visible output by 97.6% while it
kept the complete log. Results vary with labels and paths.

## Exit status

| Exit status | Meaning |
| --- | --- |
| Child status | The command completed. |
| `124` | The timeout expired. |
| `73` | The log already exists. |
| `74` | The log could not be opened. |
| `127` | The command could not start. |
| `128 + signal` | The wrapper was interrupted. |

## Moving work off GitHub Actions

This tool is a command wrapper. It is not a CI scheduler, runner, queue,
webhook receiver, secret store, cache, or artifact server.

For one trusted VPS, use it with a systemd timer or cron and your existing test
or deployment script. See [the systemd example](docs/VPS-CI.md).

For multiple repositories, webhooks, a user interface, queues, and distributed
workers, use a CI system such as [Woodpecker CI](https://woodpecker-ci.org/docs/intro)
or [Forgejo Actions](https://forgejo.org/docs/latest/user/actions/overview/).
`quiet-run` can wrap a noisy step inside either system.

## Similar tools

| Tool | Main purpose | Difference from `agent-quiet-run` |
| --- | --- | --- |
| Shell redirection | Send output to a file. | It does not define lifecycle JSON, exclusive private logs, timeout handling, process-group cleanup, or a digest. |
| [`chronic`](https://joeyh.name/code/moreutils/) | Run a command quietly unless it fails. | It is the closest small Unix tool. It is designed for human and cron output. This project keeps failure output private by default and emits bounded machine-readable lifecycle records. |
| `nohup`, `tmux`, and `systemd-run` | Keep or manage a command outside the current shell. | They manage command lifetime. They do not provide this agent-output contract. |
| [Woodpecker CI](https://woodpecker-ci.org/docs/intro) | Provide a self-hosted CI/CD platform. | It supplies webhooks, scheduling, agents, pipelines, and a user interface. This project wraps one command. |
| [Forgejo Actions](https://forgejo.org/docs/latest/user/actions/overview/) | Provide CI inside a Forgejo instance. | It supplies workflows and runners. This project does not host repositories or schedule workflows. |

The concept is deliberately small. Its useful difference is the contract for
coding agents: bounded public events, a complete private log, and predictable
cleanup.

## Test

```sh
python -m pytest
```

The repository has no GitHub Actions workflow. Run the tests locally or from
your VPS scheduler.

## License

MIT
