# Monitoring and Logging

## Current sources

- systemd service status;
- Docker logs;
- Caddy logs;
- application stdout/stderr;
- EC2 system metrics;
- SES metrics;
- SSM association execution history;
- Terraform output and state history.

## Minimum health checks

- EC2 running;
- ports 80/443 reachable;
- HTTPS 200;
- app container running;
- Caddy container running;
- disk usage acceptable;
- database present;
- recent logs free of repeated exceptions;
- SES not showing unexpected failures.

## Privacy

Do not log passwords, hashes, session cookies, reset/verification tokens, SSM values, or private message content unnecessarily.
