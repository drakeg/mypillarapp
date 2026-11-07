from __future__ import annotations

from dataclasses import dataclass
import html

import creator_affiliates
import creator_collections
import creator_downloads
import creator_profiles
import creator_storefront


@dataclass(frozen=True)
class CreatorPublicResult:
    status:int
    body:str


def _esc(value:object)->str:
    return html.escape(str(value or ''),quote=True)


def _money(price_cents:int|None,currency:str)->str:
    if price_cents is None:
        return ''
    return f'{_esc(currency)} {price_cents/100:.2f}'


def render_creator(site)->CreatorPublicResult:
    profile=creator_profiles.get_profile(
        site.organization_slug,site.slug,published_only=True
    )
    if profile is None:
        return CreatorPublicResult(404,'<h1>Creator page not found</h1>')

    links=creator_profiles.list_links(
        site.organization_slug,site.slug,published_only=True
    )
    affiliates=creator_affiliates.list_affiliates(
        site.organization_slug,site.slug,published_only=True
    )
    collections=creator_collections.list_collections(
        site.organization_slug,site.slug,published_only=True
    )

    avatar=(
        f'<img src="{_esc(profile.avatar_url)}" alt="{_esc(profile.display_name)}" height="96">'
        if profile.avatar_url else ''
    )
    link_html=''.join(
        f'<li><a href="{_esc(row.target)}">{_esc(row.label)}</a></li>'
        for row in links
    )
    affiliate_html=''.join(
        f'<article class="card affiliate"><h3>{_esc(row.label)}</h3>'
        f'<p><a rel="sponsored nofollow" href="{_esc(row.destination_url)}">Visit link</a></p>'
        f'<p class="muted"><strong>Affiliate disclosure:</strong> {_esc(row.disclosure_text)}</p>'
        '</article>'
        for row in affiliates
    )
    collection_html=[]
    for collection in collections:
        items=creator_collections.list_items(
            site.organization_slug,site.slug,collection.id
        )
        item_html=''.join(
            f'<li><a href="{_esc(item.target)}">{_esc(item.title)}</a></li>'
            for item in items
        )
        collection_html.append(
            f'<article class="card"><h3>{_esc(collection.title)}</h3>'
            f'<p>{_esc(collection.description)}</p>'
            f'{f"<ul>{item_html}</ul>" if item_html else ""}</article>'
        )

    body=(
        '<main>'
        f'{avatar}<h1>{_esc(profile.display_name)}</h1>'
        f'<p>{_esc(profile.bio)}</p>'
        f'{f"<section><h2>Links</h2><ul>{link_html}</ul></section>" if link_html else ""}'
        f'{f"<section><h2>Affiliate links</h2>{affiliate_html}</section>" if affiliate_html else ""}'
        f'{f"<section><h2>Collections</h2>{"".join(collection_html)}</section>" if collection_html else ""}'
        '<p><a href="/store">Storefront</a></p>'
        '</main>'
    )
    return CreatorPublicResult(200,body)


def render_store(site)->CreatorPublicResult:
    products=creator_storefront.list_products(
        site.organization_slug,site.slug,published_only=True
    )
    cards=[]
    for product in products:
        action=''
        if product.product_type=='external' and product.external_url:
            action=f'<p><a rel="nofollow" href="{_esc(product.external_url)}">View product</a></p>'
        elif product.product_type=='digital_download' and product.download_id is not None:
            download=creator_downloads.get_download(
                site.organization_slug,site.slug,product.download_id
            )
            if download is not None:
                public_url=creator_downloads.public_source(download)
                if public_url:
                    action=f'<p><a href="{_esc(public_url)}">Download</a></p>'
                else:
                    action='<p class="muted">Delivery available through the managed platform.</p>'
        cards.append(
            f'<article class="card"><h2>{_esc(product.title)}</h2>'
            f'<p>{_esc(product.description)}</p>'
            f'{f"<p><strong>{_money(product.price_cents,product.currency)}</strong></p>" if product.price_cents is not None else ""}'
            f'{action}</article>'
        )
    body=(
        '<main><p><a href="/creator">← Creator</a></p>'
        '<h1>Storefront</h1>'
        f'{"".join(cards) if cards else "<p>No published products are available.</p>"}'
        '</main>'
    )
    return CreatorPublicResult(200,body)
