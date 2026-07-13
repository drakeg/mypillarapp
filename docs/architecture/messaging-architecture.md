# Messaging Architecture

## Purpose

Messaging unifies project requests, quick chats, admin replies, internal notes, state management, and optional customer feedback.

## Lifecycle

1. Visitor submits contact or chat input.
2. Application validates and stores a conversation.
3. A private tokenized link is generated.
4. Notification is sent when configured.
5. Customer and admin append messages.
6. Admin updates status, priority, tags, and notes.
7. Customer may optionally leave feedback.
8. Closed conversations remain available according to retention policy.

## Security

- conversation tokens must be high entropy;
- tokens are not logged;
- private links do not expose sequential IDs;
- output is escaped;
- admin-only data never appears in customer views;
- feedback cannot expose internal notes.

## Status model

- new;
- waiting_on_me;
- waiting_on_client;
- in_progress;
- closed.
