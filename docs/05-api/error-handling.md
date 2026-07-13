# Error Handling

## Principles

- Show users a safe, useful message.
- Log enough technical detail for diagnosis.
- Never expose credentials, tokens, stack traces, filesystem paths, or AWS identifiers to public users.
- Use deterministic status codes.
- Preserve form input where safe after validation errors.

## Response Shape for Future JSON APIs

```json
{
  "error": {
    "code": "validation_error",
    "message": "The request could not be processed.",
    "fields": {
      "email": "Enter a valid email address."
    },
    "request_id": "optional-correlation-id"
  }
}
```

## Logging

Unexpected exceptions must be written to application logs with:

- timestamp;
- route;
- HTTP method;
- request correlation identifier when available;
- exception type;
- safe stack trace;
- no secrets or raw passwords.
