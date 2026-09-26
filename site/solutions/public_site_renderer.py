from __future__ import annotations

from dataclasses import dataclass
import html

import site_branding
import site_forms
import site_navigation
import site_pages
import site_services
import tenant_context


@dataclass(frozen=True)
class PublicRenderResult:
    status: int
    body: str


def _esc(value: object) -> str:
    return html.escape(str(value or ''), quote=True)


def _page_shell(title: str, body: str, *, primary: str, secondary: str) -> str:
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{_esc(title)}</title>
  <style>
    :root {{ --primary: {_esc(primary)}; --secondary: {_esc(secondary)}; }}
    body {{ font-family: system-ui, sans-serif; margin: 0; color: #1f2937; }}
    header, main, footer {{ max-width: 960px; margin: 0 auto; padding: 1.25rem; }}
    header {{ display:flex; gap:1rem; align-items:center; justify-content:space-between; }}
    nav a {{ margin-right: 1rem; }}
    .hero {{ padding: 2rem 0; }}
    .card {{ border: 1px solid #ddd; border-radius: .75rem; padding: 1rem; margin: 1rem 0; }}
    .btn {{ display:inline-block; background:var(--primary); color:white; padding:.65rem 1rem; border-radius:.5rem; text-decoration:none; }}
    .muted {{ color:#6b7280; }}
    h1,h2,h3 {{ color:var(--primary); }}
    footer {{ border-top: 1px solid #eee; margin-top: 2rem; }}
  </style>
</head>
<body>
{body}
</body>
</html>"""


def _nav_html(organization_slug: str, site_slug: str) -> str:
    items = site_navigation.list_items(
        organization_slug,
        site_slug,
        visible_only=True,
    )
    links = ''.join(
        f'<a href="{_esc(item.target)}">{_esc(item.label)}</a>'
        for item in items
    )
    return f'<nav>{links}</nav>' if links else ''


def _form_html(form) -> str:
    fields = []
    for field in form.fields:
        name = _esc(field.get('name', ''))
        label = _esc(field.get('label', ''))
        field_type = str(field.get('type', 'text'))
        required = ' required' if field.get('required') else ''
        placeholder = _esc(field.get('placeholder', ''))
        if field_type == 'textarea':
            control = f'<textarea name="{name}" placeholder="{placeholder}"{required}></textarea>'
        elif field_type == 'select':
            options = ''.join(
                f'<option value="{_esc(option)}">{_esc(option)}</option>'
                for option in field.get('options', [])
            )
            control = f'<select name="{name}"{required}>{options}</select>'
        else:
            input_type = 'email' if field_type == 'email' else 'text'
            control = (
                f'<input type="{input_type}" name="{name}" '
                f'placeholder="{placeholder}"{required}>'
            )
        fields.append(f'<label>{label}{control}</label>')
    return (
        f'<section class="card"><h2>{_esc(form.title)}</h2>'
        f'<form>{"".join(fields)}'
        f'<button type="button" disabled>{_esc(form.submit_label)}</button>'
        '<p class="muted">Form submission is not enabled on this Site Builder preview yet.</p>'
        '</form></section>'
    )


def _home(site) -> PublicRenderResult:
    branding = site_branding.get_branding(site.organization_slug, site.slug)
    if branding is None:
        return PublicRenderResult(404, '<h1>Site unavailable</h1>')

    pages = site_pages.list_pages(
        site.organization_slug,
        site.slug,
        published_only=True,
    )
    services = site_services.list_services(
        site.organization_slug,
        site.slug,
        published_only=True,
    )
    forms = site_forms.list_forms(
        site.organization_slug,
        site.slug,
        published_only=True,
    )

    logo = (
        f'<img src="{_esc(branding.logo_url)}" alt="{_esc(branding.site_name)} logo" height="48">'
        if branding.logo_url else ''
    )
    page_cards = ''.join(
        f'<article class="card"><h2>{_esc(page.title)}</h2>'
        f'<p>{_esc(page.summary)}</p>'
        f'<a class="btn" href="/pages/{_esc(page.slug)}">Read more</a></article>'
        for page in pages
    )
    service_cards = ''.join(
        f'<article class="card"><h3>{_esc(service.name)}</h3>'
        f'<p>{_esc(service.summary)}</p>'
        f'{f"<p><strong>{_esc(service.price_text)}</strong></p>" if service.price_text else ""}'
        '</article>'
        for service in services
    )
    forms_html = ''.join(_form_html(form) for form in forms)

    body = (
        f'<header>{logo}<strong>{_esc(branding.site_name)}</strong>'
        f'{_nav_html(site.organization_slug, site.slug)}</header>'
        '<main>'
        f'<section class="hero"><h1>{_esc(branding.site_name)}</h1>'
        f'<p>{_esc(branding.tagline)}</p></section>'
        f'{page_cards}'
        f'{f"<section><h2>Services</h2>{service_cards}</section>" if service_cards else ""}'
        f'{forms_html}'
        '</main>'
        f'<footer>{_esc(branding.support_email)}</footer>'
    )
    return PublicRenderResult(
        200,
        _page_shell(
            branding.site_name,
            body,
            primary=branding.primary_color,
            secondary=branding.secondary_color,
        ),
    )


def _published_page(site, slug: str) -> PublicRenderResult:
    page = site_pages.get_page(site.organization_slug, site.slug, slug)
    if not page or page.status != 'published':
        return PublicRenderResult(404, '<h1>Page not found</h1>')

    branding = site_branding.get_branding(site.organization_slug, site.slug)
    if branding is None:
        return PublicRenderResult(404, '<h1>Site unavailable</h1>')

    body = (
        f'<header><strong>{_esc(branding.site_name)}</strong>'
        f'{_nav_html(site.organization_slug, site.slug)}</header>'
        '<main>'
        f'<p><a href="/">← Home</a></p>'
        f'<article><h1>{_esc(page.title)}</h1>'
        f'<p>{_esc(page.summary)}</p>'
        f'<div>{_esc(page.body).replace(chr(10), "<br>")}</div>'
        '</article></main>'
    )
    return PublicRenderResult(
        200,
        _page_shell(
            f'{page.title} - {branding.site_name}',
            body,
            primary=branding.primary_color,
            secondary=branding.secondary_color,
        ),
    )


def render_public_path(host: str, path: str) -> PublicRenderResult | None:
    site = tenant_context.resolve_site(host)
    if not site:
        return PublicRenderResult(404, '<h1>Site not found</h1>')

    # S3-T10 owns migration of the existing Solutions public site. Until then,
    # preserve the protected static homepage and request/customer journeys.
    if site.organization_slug == 'solutions' and site.slug == 'main':
        return None

    if site.status != 'published':
        return PublicRenderResult(
            404,
            '<h1>Site unavailable</h1><p>This site has not been published.</p>',
        )

    normalized_path = '/' + (path or '/').strip('/')
    if normalized_path == '/':
        return _home(site)
    if normalized_path.startswith('/pages/'):
        slug = normalized_path[len('/pages/'):].strip('/')
        return _published_page(site, slug)

    return PublicRenderResult(404, '<h1>Page not found</h1>')
