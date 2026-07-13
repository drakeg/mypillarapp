# HTTP Route Catalog

The source code remains authoritative if a route differs.

| Method | Route | Authentication | Purpose |
|---|---|---|---|
| GET | `/` | none | Public site |
| POST | `/api/contact` | none | Project request |
| POST | `/api/chat` | none | New async chat |
| GET | `/conversation/{token}` | conversation token | Customer conversation |
| POST | `/api/conversations/{token}/messages` | conversation token | Customer reply |
| POST | `/api/conversations/{token}/feedback` | conversation token | Optional feedback |
| GET/POST | `/register` | none | Customer registration |
| GET/POST | `/login` | none | Customer login |
| GET | `/logout` | customer | Customer logout |
| GET | `/verify-email/{token}` | token | Email verification |
| GET/POST | `/forgot-password` | none | Reset request |
| GET/POST | `/reset-password/{token}` | token | Password reset |
| GET | `/dashboard` | customer | Customer dashboard |
| GET/POST | `/profile` | customer | Profile/password |
| GET/POST | `/admin/login` | none | Admin login |
| GET | `/admin/logout` | admin | Admin logout |
| GET | `/admin` | admin | Admin dashboard |
| GET | `/admin/inbox` | admin | Inbox |
| GET | `/admin/requests` | admin | Service requests |
| GET | `/admin/leads` | admin | Leads |
| GET | `/admin/crm` | admin | CRM |
| GET | `/admin/sites` | admin | Sites |
| GET | `/admin/settings` | admin | Settings |
