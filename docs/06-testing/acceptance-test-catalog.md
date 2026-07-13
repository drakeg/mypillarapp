# Acceptance Test Catalog

## AT-001 Public Contact Request

**Given** a visitor is on the public site  
**When** they submit a valid project request  
**Then** the request is stored, a private conversation is created, and configured notification email is sent.

## AT-002 Customer Registration

**Given** a new customer  
**When** they register with valid information  
**Then** an inactive account and verification token are created and an email is sent.

## AT-003 Customer Login

**Given** a verified active customer  
**When** valid credentials are submitted  
**Then** a customer session is established and `/dashboard` loads.

## AT-004 Admin Login

**Given** SSM-backed admin credentials are configured  
**When** the administrator signs in  
**Then** `/admin` shows the approved dashboard and dashboard links remain authenticated.

## AT-005 Admin Reply

**Given** an open conversation  
**When** an administrator replies  
**Then** the message is persisted, the conversation updates, and notification behavior follows configuration.

## AT-006 Deployment

**Given** valid AWS credentials and an initialized backend  
**When** Terraform apply completes  
**Then** the current site version is deployed with no manual server edits.
