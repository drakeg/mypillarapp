#!/usr/bin/env python3
from __future__ import annotations
import base64, getpass, hashlib, secrets, sys

def b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode('ascii').rstrip('=')

password = getpass.getpass('Admin password: ')
confirm = getpass.getpass('Confirm password: ')
if password != confirm:
    print('Passwords do not match.', file=sys.stderr)
    sys.exit(1)
if len(password) < 12:
    print('Use at least 12 characters.', file=sys.stderr)
    sys.exit(1)
salt = secrets.token_urlsafe(16)
iterations = 390000
digest = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt.encode('utf-8'), iterations)
print(f'pbkdf2_sha256${iterations}${salt}${b64url(digest)}')
