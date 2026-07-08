# Mad Mallard Platform - Clean AWS Bootstrap

This repository is the low-cost starting point for the Mad Mallard platform.

The current goal is simple:

- keep one AWS EC2 instance,
- keep SSH available by default,
- secure the host with a standard baseline,
- serve `pillar.madmallards.com` through Caddy + HTTPS,
- deploy the actual Mad Mallard Solutions landing page through Terraform-managed SSM,
- avoid Elastic IP cost for now,
- avoid replacing the EC2 instance for normal site changes.

## Current architecture

```text
External DNS provider
  A record: pillar.madmallards.com -> EC2 public IP
      |
      v
EC2 public instance
  - Docker
  - Caddy container :80/:443
  - App container :8000
  - SSM agent
  - fail2ban/firewalld/security baseline
```

## Cost target

Approximate monthly cost during bootstrap:

| Item | Approx. monthly cost |
|---|---:|
| EC2 t3.micro | $0 if Free Tier eligible, otherwise roughly $7-10 |
| EBS gp3 20GB | roughly $1.60-$2 |
| Public IPv4 | roughly $3.60 |
| SSM documents/associations | $0 for this usage |
| Let's Encrypt via Caddy | $0 |
| Elastic IP | $0 because disabled by default |

Expected total: roughly **$5-$15/month**, depending on Free Tier eligibility.

## Important design decisions

### No Elastic IP yet

`use_elastic_ip = false` by default. That avoids the extra Elastic IP charge. The downside is that if the EC2 instance is replaced, the public IP changes and you must update DNS.

Later, when the business justifies the cost, set:

```hcl
use_elastic_ip = true
```

### Do not replace EC2 for app changes

`user_data_replace_on_change = false` by default. The instance should not be replaced for normal bootstrap/app changes.

App/site updates are now handled through **SSM App Deploy**, not user data.

### SSH remains available

SSH is useful and remains enabled by default:

```hcl
enable_ssh = true
ssh_cidr   = "0.0.0.0/0"
```

For stricter access later, set `ssh_cidr` to your current IP `/32`, or disable SSH entirely:

```hcl
enable_ssh = false
```

SSM Session Manager can still be used if IAM/SSM is working.

## Configure Terraform

Copy the example variables:

```bash
cp terraform/environments/prod/terraform.tfvars.example terraform/environments/prod/terraform.tfvars
```

Edit:

```hcl
primary_domain = "pillar.madmallards.com"
acme_email     = "greg@madmallards.com"

enable_ssh = true
ssh_cidr   = "0.0.0.0/0"
public_key = "ssh-ed25519 AAAA...your-public-key..."

use_elastic_ip              = false
user_data_replace_on_change = false
security_profile            = "standard"
```

## Deploy/update

From the repository root:

```bash
make tf-init ENV=prod
make tf-validate ENV=prod
make tf-plan ENV=prod
make tf-apply ENV=prod
```

After apply:

```bash
make tf-output ENV=prod
```

Point your external DNS A record to the Terraform `public_ip` output:

```text
pillar.madmallards.com -> public_ip
```

## Updating the visible site

The Mad Mallard Solutions page lives here:

```text
site/solutions/index.html
```

To change the live site:

```bash
edit site/solutions/index.html
make tf-plan ENV=prod
make tf-apply ENV=prod
```

Terraform updates the SSM app deployment document and association. The existing EC2 instance updates in place.

No SSH edits. No EC2 replacement. No DNS change.

## If you want to force the app deployment to run immediately

Terraform should create/update the State Manager association. If you want to force it manually:

```bash
aws ssm start-associations-once --association-ids $(cd terraform/environments/prod && terraform output -raw app_deploy_association_id)
```

Then check execution status:

```bash
aws ssm describe-association-executions \
  --association-id $(cd terraform/environments/prod && terraform output -raw app_deploy_association_id) \
  --max-results 5
```

## Verify the site

```bash
curl -I http://pillar.madmallards.com
curl -I https://pillar.madmallards.com
curl https://pillar.madmallards.com
```

Expected:

- HTTP redirects to HTTPS.
- HTTPS returns `200`.
- Browser shows the Mad Mallard Solutions landing page.

## Useful instance checks

SSH user depends on AMI:

```bash
cd terraform/environments/prod
terraform output ssh_user
terraform output public_ip
```

Amazon Linux 2023 default user is `ec2-user`.

On the instance:

```bash
madmallard-audit
systemctl status madmallard-app --no-pager -l
systemctl status madmallard-caddy --no-pager -l
docker ps -a
ss -tulpn | egrep ':80|:443|:8000'
```

## What is deployed by SSM App Deploy

The app deploy module writes:

```text
/opt/madmallard-platform/app/index.html
/opt/madmallard-platform/app/server.py
/opt/madmallard-platform/caddy/Caddyfile
/etc/systemd/system/madmallard-app.service
/etc/systemd/system/madmallard-caddy.service
```

Then it restarts:

```text
madmallard-app
madmallard-caddy
```

## Next platform steps

Once this page is live and stable:

1. Replace the temporary Python static server with the Django platform container.
2. Add tenant/business records for Mad Mallard Solutions, Mad Mallards Adventures, and Mad Mallard Personal Training.
3. Add separate themes and public pages per business.
4. Add the Pillar-style link/product/media-kit modules.
5. Add backups and later optional managed services only when revenue justifies the cost.

## Site deployment model

The live site is deployed by Terraform through SSM, but the SSM document no longer embeds the full HTML/CSS/assets. Terraform uploads `site/solutions/` to a private S3 artifact bucket, then the SSM association tells the EC2 instance to sync those files locally and restart the app/Caddy containers.

This avoids the AWS SSM 64 KiB document-size limit and updates the running instance in place. It should not replace EC2, change DNS, or require an Elastic IP.

Workflow:

```bash
# edit site/solutions/index.html or files under site/solutions/assets/
make tf-plan ENV=prod
make tf-apply ENV=prod
```

If the association does not run immediately, trigger it manually:

```bash
aws ssm start-associations-once --association-ids $(cd terraform/environments/prod && terraform output -raw app_deploy_association_id)
```

## v1.9: zero-extra-cost contact + async chat

This version adds the first near-free interactive features for `pillar.madmallards.com`:

- configurable project request form options in `site/solutions/server.py`
- SQLite lead storage on the EC2 host at `/opt/madmallard-platform/data/madmallard.sqlite3`
- asynchronous chat/conversation threads with private return links
- optional admin inbox at `/admin/inbox?token=YOUR_TOKEN`
- no RDS, Redis, paid chat tool, AI API, ALB, or WAF required

To enable the admin inbox, set an alphanumeric/token-safe value in `terraform/environments/prod/terraform.tfvars`:

```hcl
admin_token = "replace-with-a-long-random-token"
```

Leave `admin_token = ""` to keep the web inbox disabled. Leads and chat messages are still stored locally in SQLite.

Deploy site/app changes without replacing EC2:

```bash
make tf-plan ENV=prod
make tf-apply ENV=prod
```


## v2.0: SES notifications and easier admin/chat access

This version keeps the near-free architecture but adds optional Amazon SES notifications.

### Enable email notifications

SES itself should add effectively no meaningful monthly cost at this stage. If your AWS SES account is still in sandbox, **both** the sender and recipient addresses must be verified in SES.

In `terraform/environments/prod/terraform.tfvars`:

```hcl
admin_token = "use-a-long-random-admin-token"

enable_email_notifications = true
notify_email_from          = "verified-sender@madmallards.com"
notify_email_to            = "your-email@example.com"
```

Then apply:

```bash
make tf-plan ENV=prod
make tf-apply ENV=prod
```

The EC2 instance role is granted `ses:SendEmail`/`ses:SendRawEmail`, and the app container installs `boto3` only when email notifications are enabled.

### Admin inbox without remembering the long token every time

Instead of using the long query string each time, go to:

```text
https://pillar.madmallards.com/admin/login
```

Enter the admin token once. The site stores it in a secure browser cookie for 30 days. After that, use:

```text
https://pillar.madmallards.com/admin/inbox
```

### Chat links are less clunky

When a visitor starts an async chat and provides an email address, the platform emails them their private conversation link. They can return from the email instead of remembering/bookmarking the long token.

Admin notifications are also sent for:

- new project requests
- new chat conversations
- visitor replies

Admin replies will email the visitor when the visitor supplied an email address.

## SES email notifications with external DNS

DNS for `madmallards.com` is external, so Terraform creates the SES resources but does **not** create DNS records.

To enable near-free SES notifications:

```hcl
enable_email_notifications  = true
ses_domain                  = "madmallards.com"
notify_email_from           = "noreply@madmallards.com"
notify_email_to             = "your-address@example.com"
create_ses_recipient_identity = true
```

Apply Terraform:

```bash
make tf-plan ENV=prod
make tf-apply ENV=prod
make tf-output ENV=prod
```

Then copy the `ses_external_dns_records` output into your external DNS provider. It will include:

- `_amazonses.<domain>` TXT verification record
- three DKIM CNAME records
- recommended SPF TXT record
- recommended DMARC TXT record

If your SES account is still in sandbox, Terraform also creates an SES identity for `notify_email_to`. AWS will send that address a verification email; click the link before expecting test emails to arrive. Later, request SES production access so the platform can email unverified visitors their chat links.

Cost impact: SES identities and DKIM have no standing monthly charge. Sending email is usage-based and should be effectively free/pennies at this early volume.


## SES custom MAIL FROM with external DNS

This stack can create an SES custom MAIL FROM domain for better SPF/DMARC alignment while keeping your normal Outlook/Microsoft 365 mail flow intact. DNS is hosted externally, so Terraform does not create DNS records. It outputs the records you add manually.

Recommended settings:

```hcl
enable_email_notifications = true
ses_domain                 = "madmallards.com"
enable_custom_mail_from    = true
mail_from_subdomain        = "mail"
notify_email_from          = "noreply@madmallards.com"
notify_email_to            = "greg@madmallards.com"
```

After `terraform apply`, run:

```bash
make tf-output ENV=prod
```

Add the records shown in `ses_external_dns_records` at your external DNS provider. The custom MAIL FROM records will look like:

```text
MX   mail.madmallards.com   10 feedback-smtp.<region>.amazonses.com
TXT  mail.madmallards.com   v=spf1 include:amazonses.com ~all
```

Do not replace the root `madmallards.com` MX records used by Outlook/Microsoft 365. For root SPF, keep only one SPF TXT record and merge SES into your existing record if one exists, for example:

```text
v=spf1 include:spf.protection.outlook.com include:amazonses.com ~all
```

Cost impact is effectively zero at current usage; SES charges are usage-based and tiny for low-volume contact notifications.


## Messaging and near-free notifications

The live site now includes a lightweight dedicated messaging component deployed as normal site artifacts:

- SQLite-backed conversations and messages on the EC2 instance
- Project request form and async chat both create conversations
- Admin inbox at `/admin/login` and `/admin/inbox`
- Statuses: `new`, `waiting_on_me`, `waiting_on_client`, `closed`
- Priorities: `low`, `normal`, `high`
- Tags and internal notes
- SES notifications when enabled

Email notification triggers:

1. New project request: sends admin notification and visitor conversation link.
2. New chat: sends admin notification and visitor conversation link.
3. Visitor reply: sends admin notification.
4. Admin public reply: sends visitor notification.
5. Admin internal note: saved only; no visitor email.

Cost impact remains near-free: SQLite runs on the existing EC2 instance and SES is usage-based/pennies at small volume. No RDS, Redis, ALB, WAF, AI, or paid chat service is used.

## v2.4 Messaging polish

This release keeps the near-free SQLite + SES approach and improves the messaging experience:

- Polished admin inbox with status cards, filters, search, and satisfaction score.
- Conversation thread UI with timestamps and clearer status badges.
- Optional visitor feedback on replies.
- One-click feedback links in reply emails.
- Internal notes and saved reply snippets.

Deploy with:

```bash
make tf-plan ENV=prod
make tf-apply ENV=prod
```

No new AWS services are added. Costs remain essentially the same as v2.3: EC2, tiny S3 artifact storage, and SES per-email charges.


## Terraform remote state

This repo is configured to use the shared S3 state bucket with a project/environment prefix:

```text
s3://video-short-converter-terraform-state/madmallard-platform/prod/terraform.tfstate
```

The backend files live here:

```text
terraform/environments/prod/backend.tf
terraform/environments/prod/backend.hcl
```

`backend.tf` intentionally contains only:

```hcl
terraform {
  backend "s3" {}
}
```

The environment-specific backend settings are in `backend.hcl`:

```hcl
bucket       = "video-short-converter-terraform-state"
key          = "madmallard-platform/prod/terraform.tfstate"
region       = "us-east-1"
encrypt      = true
use_lockfile = true
```

This uses S3 native lock files instead of the deprecated `dynamodb_table` backend setting. No DynamoDB table is required.

### First-time migration from local state

From the repo root, run:

```bash
make tf-init-migrate ENV=prod
```

When Terraform asks whether to copy the existing local state to S3, answer `yes`.

Then verify:

```bash
make tf-output ENV=prod
terraform -chdir=terraform/environments/prod state list
aws s3 ls s3://video-short-converter-terraform-state/madmallard-platform/prod/
```

After confirming the remote state works, keep a backup of the old local state or remove it from the working tree. Do not commit `terraform.tfstate` or `terraform.tfstate.backup`.

### Normal workflow after migration

```bash
make tf-init ENV=prod
make tf-plan ENV=prod
make tf-apply ENV=prod
```

If backend settings change later, run:

```bash
make tf-init-reconfigure ENV=prod
```

## Multiple SSH keys

For multiple systems, use `ssh_public_keys` in `terraform/environments/prod/terraform.tfvars`:

```hcl
ssh_public_keys = [
  "ssh-ed25519 AAAA... greg-laptop",
  "ssh-ed25519 AAAA... greg-desktop",
]
```

Terraform still uses the first key as the EC2 launch key pair, then an SSM association installs all configured keys into the instance user's `authorized_keys` file. This updates the running instance in place and does not require replacing EC2.

After applying, you can force the key update immediately:

```bash
make tf-output ENV=prod
aws ssm start-associations-once --association-ids <ssh_keys_association_id>
```


## v2.7 admin account fix

This release restores the admin account Terraform inputs and wires them through `module.app_deploy`:

```hcl
admin_username        = "admin"
admin_password_hash   = ""
admin_session_secret  = ""
admin_token           = "your-long-token"
```

`admin_token` remains supported. The username/password/session variables are accepted by Terraform and passed to the app container so the admin login implementation can use them without unsupported-argument or undeclared-variable warnings.
## v2.8.2 admin login regression fix

The admin web login uses username/password again. The admin token remains available for internal/emergency automation only and is not shown on the login page.

Generate an admin password hash with:

```bash
python - <<'PY'
import hashlib, secrets, getpass
password = getpass.getpass('Admin password: ')
salt = secrets.token_hex(16)
iterations = 390000
digest = hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), iterations).hex()
print(f'pbkdf2_sha256${iterations}${salt}${digest}')
PY
```

Then set:

```hcl
admin_username        = "admin"
admin_password_hash   = "pbkdf2_sha256$..."
admin_session_secret  = "long-random-session-secret"
```
