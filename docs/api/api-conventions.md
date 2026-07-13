# API Conventions

## HTTP

- GET is read-only.
- POST creates or performs a command.
- Redirect-after-POST uses 303.
- Validation failures use 400.
- Missing authentication uses redirect for browser routes and 401 for future APIs.
- Forbidden operations use 403.
- Missing resources use 404.
- Conflicts use 409.

## Error body for future JSON API

```json
{
  "error": {
    "code": "validation_error",
    "message": "The request could not be processed.",
    "fields": {}
  }
}
```

## Security

- never return stack traces;
- never reveal account existence in password-reset responses;
- never include raw tokens in logs;
- escape all user content rendered as HTML.
