# Monitoring and Logging

## Current Sources

- `journalctl -u madmallard-app`
- `journalctl -u madmallard-caddy`
- `docker logs madmallard-app`
- `docker logs madmallard-caddy`
- EC2 system logs
- SES sending metrics
- SSM association execution history

## Minimum Checks

- EC2 instance state
- TCP 80/443 availability
- HTTPS response code
- Application container state
- Caddy container state
- Disk usage
- SQLite database presence and size
- SES send failures
- SSM association failures

## Future Improvements

Add CloudWatch alarms only when justified by value and cost. Prefer free or low-cost metrics and logs during early stages.
