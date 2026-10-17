# Security

`quiet-run` stores the complete stdout and stderr from the child command. The
log can contain credentials, customer data, or other private values.

- The tool creates each log with mode `0600`.
- The tool refuses to replace an existing log.
- The tool does not print the child command or its arguments.
- Command arguments can still be visible in the operating system process list.
- Existing parent directories keep their current permissions.

Use a private log directory. Apply your retention and deletion rules to that
directory. Do not put credentials in the public label or log path.

To report a vulnerability, open a GitHub security advisory for this repository.
