# HTTP Endpoints

The table below describes the intended route contract. The repository source remains authoritative if implementation and documentation differ.

## Public

| Method | Route | Purpose |
|---|---|---|
| GET | `/` | Public landing page |
| POST | `/api/contact` | Submit a structured project or service request |
| POST | `/api/chat` | Start an async conversation |
| GET | `/conversation/{token}` | View a private customer conversation |
| POST | `/api/conversations/{token}/messages` | Add a customer message |
| POST | `/api/conversations/{token}/feedback` | Submit response feedback |

## Customer Authentication

| Method | Route | Purpose |
|---|---|---|
| GET/POST | `/register` | Register a customer account |
| GET/POST | `/login` | Authenticate a customer |
| GET | `/logout` | End a customer session |
| GET | `/verify-email/{token}` | Verify email ownership |
| GET/POST | `/forgot-password` | Request a reset link |
| GET/POST | `/reset-password/{token}` | Reset a password |
| GET | `/dashboard` | View the customer dashboard |
| GET/POST | `/profile` | View or update profile information |

## Admin

| Method | Route | Purpose |
|---|---|---|
| GET/POST | `/admin/login` | Authenticate a bootstrap administrator |
| GET | `/admin/logout` | End the admin session |
| GET | `/admin` | Admin dashboard |
| GET | `/admin/inbox` | Conversation inbox |
| GET | `/admin/requests` | Service requests |
| GET | `/admin/leads` | Leads |
| GET | `/admin/crm` | CRM view |
| GET | `/admin/sites` | Site registry |
| GET | `/admin/settings` | Read-only operational settings |
| GET | `/admin/conversations/{token}` | Admin conversation detail |
| POST | `/api/admin/conversations/{token}/messages` | Send an admin reply |
| POST | `/api/admin/conversations/{token}/update` | Update status, priority, tags, or notes |

## Status Codes

| Code | Use |
|---|---|
| 200 | Successful read or completed action |
| 201 | Newly created resource, when implemented |
| 303 | Redirect after authentication or form submission |
| 400 | Invalid request data |
| 401 | Missing or invalid API authentication, when used |
| 403 | Authenticated but unauthorized, or disabled admin |
| 404 | Route or resource not found |
| 409 | Duplicate or conflicting resource |
| 429 | Rate limit exceeded, when implemented |
| 500 | Unexpected application failure |
| 502 | Caddy cannot reach the application container |
