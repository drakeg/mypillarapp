from __future__ import annotations

import html
import time

import portal_auth
import portal_files
import portal_history
import portal_messaging
import portal_notifications
import portal_projects
import portal_tenancy
import portal_tickets


def _esc(value: object) -> str:
    return html.escape(str(value or ''))


def _fmt_timestamp(value: object) -> str:
    try:
        return time.strftime(
            '%b %d, %Y %I:%M %p',
            time.localtime(int(value)),
        )
    except (TypeError, ValueError, OSError):
        return ''


def _page(title: str, content: str) -> str:
    return (
        '<!doctype html><html><head>'
        f'<title>{_esc(title)} - Customer Portal</title>'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        '<link rel="stylesheet" href="/assets/styles.css">'
        '</head><body class="conversation-page">'
        f'<main class="conversation-shell">{content}</main>'
        '</body></html>'
    )


def _nav() -> str:
    return (
        '<p><a href="/dashboard">← Dashboard</a> · '
        '<a href="/portal">Portal</a> · '
        '<a href="/portal/history">History</a> · '
        '<a href="/portal/messages">Messages</a> · '
        '<a href="/portal/notifications">Notifications</a> · '
        '<a href="/profile">Profile</a> · '
        '<a href="/logout">Sign out</a></p>'
    )


def scope_for_user(user) -> portal_tenancy.CustomerScope:
    return portal_tenancy.customer_scope(user)


def render_dashboard(user) -> str:
    scope = scope_for_user(user)
    projects = portal_projects.list_projects(
        scope.organization_slug,
        customer_user_id=scope.user_id,
    )
    tickets = portal_tickets.list_tickets(
        scope.organization_slug,
        customer_user_id=scope.user_id,
        visibility='customer',
    )
    files = portal_files.list_files(
        scope.organization_slug,
        customer_user_id=scope.user_id,
        visibility='customer',
    )
    deliveries = portal_notifications.list_deliveries(
        scope.organization_slug,
        customer_user_id=scope.user_id,
        limit=100,
    )
    history = portal_history.list_customer_history(scope, limit=8)

    project_rows = ''.join(
        '<li>'
        f'<a href="/portal/projects/{project.id}">'
        f'<strong>{_esc(project.title)}</strong></a>'
        f' <small>{_esc(project.status).replace("_", " ").title()}</small>'
        '</li>'
        for project in projects[:8]
    ) or '<li>No portal projects yet.</li>'

    recent_rows = ''.join(
        '<li>'
        f'<strong>{_esc(item.kind).title()}:</strong> {_esc(item.title)}'
        f' <small>{_fmt_timestamp(item.occurred_at)}</small>'
        '</li>'
        for item in history
    ) or '<li>No portal activity yet.</li>'

    return _page(
        'Customer Portal',
        _nav()
        + f'<h1>Customer Portal</h1>'
        + f'<p>Service delivery for <strong>{_esc(scope.email)}</strong>.</p>'
        + '<section class="dashboard-grid">'
        + f'<article class="dash-card"><span>Projects</span><strong>{len(projects)}</strong></article>'
        + f'<article class="dash-card"><span>Tickets</span><strong>{len(tickets)}</strong></article>'
        + f'<article class="dash-card"><span>Files</span><strong>{len(files)}</strong></article>'
        + f'<article class="dash-card"><span>Notifications</span><strong>{len(deliveries)}</strong></article>'
        + '</section>'
        + '<section class="contact-panel"><h2>Projects</h2>'
        + f'<ul>{project_rows}</ul></section>'
        + '<section class="contact-panel"><h2>Recent service history</h2>'
        + f'<ul>{recent_rows}</ul>'
        + '<p><a href="/portal/history">View complete service history</a></p>'
        + '</section>',
    )


def render_project(user, project_id: int) -> str | None:
    scope = scope_for_user(user)
    try:
        project = portal_auth.require_customer_project(scope, project_id)
    except PermissionError:
        return None
    tickets = portal_tickets.list_tickets(
        scope.organization_slug,
        customer_user_id=scope.user_id,
        project_id=project.id,
        visibility='customer',
    )
    files = portal_files.list_files(
        scope.organization_slug,
        customer_user_id=scope.user_id,
        project_id=project.id,
        visibility='customer',
    )
    ticket_rows = ''.join(
        f'<li><a href="/portal/tickets/{ticket.id}">{_esc(ticket.subject)}</a>'
        f' <small>{_esc(ticket.status).replace("_", " ").title()}</small></li>'
        for ticket in tickets
    ) or '<li>No customer-visible tickets.</li>'
    file_rows = ''.join(
        f'<li><a href="/portal/files/{file.id}">{_esc(file.name)}</a></li>'
        for file in files
    ) or '<li>No customer-visible files.</li>'
    return _page(
        project.title,
        _nav()
        + f'<h1>{_esc(project.title)}</h1>'
        + f'<p><span class="badge">{_esc(project.status).replace("_", " ").title()}</span></p>'
        + f'<p>{_esc(project.summary)}</p>'
        + f'<p class="muted">Start: {_esc(project.start_date or "Not set")} · '
        + f'Due: {_esc(project.due_date or "Not set")}</p>'
        + '<section class="contact-panel"><h2>Tickets</h2>'
        + f'<ul>{ticket_rows}</ul></section>'
        + '<section class="contact-panel"><h2>Files</h2>'
        + f'<ul>{file_rows}</ul></section>',
    )


def render_ticket(user, ticket_id: int) -> str | None:
    scope = scope_for_user(user)
    try:
        ticket = portal_auth.require_customer_ticket(scope, ticket_id)
    except PermissionError:
        return None
    files = portal_files.list_files(
        scope.organization_slug,
        customer_user_id=scope.user_id,
        ticket_id=ticket.id,
        visibility='customer',
    )
    file_rows = ''.join(
        f'<li><a href="/portal/files/{file.id}">{_esc(file.name)}</a></li>'
        for file in files
    ) or '<li>No customer-visible files.</li>'
    project_link = (
        f'<a href="/portal/projects/{ticket.project_id}">View project</a>'
        if ticket.project_id is not None else 'No linked project'
    )
    return _page(
        ticket.subject,
        _nav()
        + f'<h1>{_esc(ticket.subject)}</h1>'
        + f'<p><span class="badge">{_esc(ticket.status).replace("_", " ").title()}</span> '
        + f'<span class="badge">{_esc(ticket.priority).title()}</span></p>'
        + f'<p>{_esc(ticket.description)}</p>'
        + f'<p>{project_link}</p>'
        + '<section class="contact-panel"><h2>Files</h2>'
        + f'<ul>{file_rows}</ul></section>',
    )


def render_file(user, file_id: int) -> str | None:
    scope = scope_for_user(user)
    try:
        file = portal_auth.require_customer_file(scope, file_id)
    except PermissionError:
        return None
    source = (
        f'<p><a class="btn secondary" href="{_esc(file.source_ref)}" '
        'rel="noopener noreferrer">Open file</a></p>'
        if file.source_type == 'external_url'
        else '<p class="muted">This file is available through managed portal storage.</p>'
    )
    return _page(
        file.name,
        _nav()
        + f'<h1>{_esc(file.name)}</h1>'
        + f'<p><strong>Type:</strong> {_esc(file.mime_type or "Not specified")}</p>'
        + source,
    )


def render_notifications(user) -> str:
    scope = scope_for_user(user)
    deliveries = portal_notifications.list_deliveries(
        scope.organization_slug,
        customer_user_id=scope.user_id,
        limit=100,
    )
    rows = ''.join(
        '<article class="contact-panel">'
        f'<h2>{_esc(item.subject or item.notification_type.replace("_", " ").title())}</h2>'
        f'<p>{_esc(item.body)}</p>'
        f'<p class="muted">{_esc(item.channel).title()} · '
        f'{_esc(item.status).title()} · {_fmt_timestamp(item.created_at)}</p>'
        '</article>'
        for item in deliveries
    ) or '<section class="contact-panel"><p>No notifications yet.</p></section>'
    return _page(
        'Notifications',
        _nav() + '<h1>Notifications</h1>' + rows,
    )


def render_history(user) -> str:
    scope = scope_for_user(user)
    items = portal_history.list_customer_history(scope, limit=200)
    rows = ''.join(
        '<article class="contact-panel">'
        f'<p><strong>{_esc(item.kind).title()}</strong> · '
        f'{_esc(item.status).replace("_", " ").title()}</p>'
        f'<h2>{_esc(item.title)}</h2>'
        f'<p>{_esc(item.detail)}</p>'
        f'<p class="muted">{_fmt_timestamp(item.occurred_at)}</p>'
        '</article>'
        for item in items
    ) or '<section class="contact-panel"><p>No service history yet.</p></section>'
    return _page('Service History', _nav() + '<h1>Service History</h1>' + rows)


def render_messages(user) -> str:
    scope = scope_for_user(user)
    conversations = portal_tenancy.list_customer_history(scope)
    rows = ''.join(
        '<article class="contact-panel">'
        f'<h2>{_esc(row["subject"] or "Conversation")}</h2>'
        f'<p>{_esc(row["kind"]).replace("_", " ").title()} · '
        f'{_esc(row["status"]).replace("_", " ").title()}</p>'
        f'<p><a class="btn secondary" href="/portal/messages/{_esc(row["token"])}">Open</a></p>'
        '</article>'
        for row in conversations
    ) or '<section class="contact-panel"><p>No conversations yet.</p></section>'
    return _page('Messages', _nav() + '<h1>Messages</h1>' + rows)


def render_conversation(user, token: str) -> str | None:
    scope = scope_for_user(user)
    conversation = portal_tenancy.conversation_for_customer(scope, token)
    if conversation is None:
        return None
    messages = portal_messaging.list_customer_messages(scope, token)
    rows = ''.join(
        '<div class="msg">'
        f'<div class="msg-meta"><strong>{_esc(message["sender"])}</strong>'
        f'<span>{_fmt_timestamp(message["created_at"])}</span></div>'
        f'<p>{_esc(message["body"])}</p></div>'
        for message in messages
    ) or '<p>No messages are available.</p>'
    subject = conversation['subject'] or 'Conversation'
    return _page(
        subject,
        _nav()
        + f'<h1>{_esc(subject)}</h1>'
        + f'<section class="message-list">{rows}</section>'
        + '<form id="portalReplyForm" class="contact-panel">'
        + '<label>Add a message<textarea name="body" rows="5" required></textarea></label>'
        + '<button class="btn primary" type="submit">Send message</button>'
        + '<p id="portalReplyStatus" class="form-status"></p></form>'
        + '<script>document.getElementById("portalReplyForm").addEventListener'
        + '("submit",async e=>{e.preventDefault();const status=document.getElementById'
        + '("portalReplyStatus");status.textContent="Sending...";const body=e.target.body.value;'
        + f'const r=await fetch("/api/portal/messages/{_esc(token)}",'
        + '{method:"POST",headers:{"Content-Type":"application/json"},'
        + 'body:JSON.stringify({body})});if(r.ok){location.reload();}'
        + 'else{status.textContent="Message could not be sent.";}});</script>',
    )
