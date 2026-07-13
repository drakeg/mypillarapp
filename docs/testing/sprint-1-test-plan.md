# Sprint 1 Test Plan

## Test matrix

| ID | Requirement | Procedure | Expected |
|---|---|---|---|
| S1-T01 | Public site | Load HTTP/HTTPS and assets | HTTP redirects; HTTPS 200 |
| S1-T02 | Project request | Submit valid/invalid form | Validation works; valid request stored |
| S1-T03 | Async chat | Start chat and reopen link | Private conversation persists |
| S1-T04 | Feedback | Submit optional rating/comment | Stored once according to rules |
| S1-T05 | Registration | Register new email | Account/token created; email sent |
| S1-T06 | Verification | Open valid/expired token | Valid activates; invalid fails safely |
| S1-T07 | Login/logout | Authenticate and sign out | Session created then revoked |
| S1-T08 | Reset | Request/reset password | Non-disclosing request; token single-use |
| S1-T09 | Dashboard | Open authenticated/anonymous | Customer data shown; anonymous redirected |
| S1-T10 | Profile | Update name/password | Update persists; sessions invalidated as required |
| S1-T11 | Admin login | Sign in and follow all links | Dashboard and links work in one session |
| S1-T12 | Admin workflow | Reply, status, tags, notes, close | Changes persist and display correctly |
| S1-T13 | SES | Trigger notifications | Configured email sent or safe failure logged |
| S1-T14 | SSM | Deploy from two workstations | Same admin credentials remain effective |
| S1-T15 | Terraform | Validate/plan/apply | No unexpected replacement or duplicate declarations |
| S1-T16 | Regression | Compare protected admin behavior | No visual/route/auth regression |
| S1-T17 | Deployment | Deploy clean `main` | No manual application file edit required |

## Evidence

Record command output, screenshots where useful, deployed commit SHA, and known limitations.
