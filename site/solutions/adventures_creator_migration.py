"""Explicit, non-destructive Adventures -> Sprint 6 compatibility migration.

This migration stages legacy Mad Mallards Adventures Site Builder content into
canonical Sprint 6 creator records. It is opt-in, never publishes creator
records, never changes domains/routes/site status, and never overwrites mapped
canonical records on rerun.
"""
from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlsplit

import creator_collections
import creator_profiles
import site_media
import site_navigation
import site_pages
import tenant_auth
import tenant_branding
import tenant_sites


ORGANIZATION = 'adventures'
SITE = 'main'
PAGES_COLLECTION_SLUG = 'legacy-pages'
MEDIA_COLLECTION_SLUG = 'legacy-media'


@dataclass(frozen=True)
class AdventuresMigrationResult:
    created_profile: int
    created_links: int
    created_collections: int
    created_items: int
    already_mapped: int
    preserved_canonical: int
    unsafe_records: int
    unmatched_records: int
    issues: tuple[str, ...]


def ensure_schema() -> None:
    creator_profiles.ensure_schema()
    creator_collections.ensure_schema()
    with tenant_auth.db() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS creator_legacy_mappings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                site_id INTEGER NOT NULL,
                source_type TEXT NOT NULL,
                source_id INTEGER NOT NULL,
                canonical_type TEXT NOT NULL,
                canonical_id INTEGER NOT NULL,
                created_at INTEGER NOT NULL,
                UNIQUE(site_id, source_type, source_id),
                FOREIGN KEY(site_id)
                    REFERENCES site_builder_sites(id) ON DELETE CASCADE
            )
            """
        )
        conn.execute(
            'CREATE INDEX IF NOT EXISTS idx_creator_legacy_mappings_site '
            'ON creator_legacy_mappings(site_id, source_type, source_id)'
        )
        conn.commit()


def _mapping(site_id: int, source_type: str, source_id: int):
    ensure_schema()
    with tenant_auth.db() as conn:
        return conn.execute(
            """
            SELECT canonical_type, canonical_id
            FROM creator_legacy_mappings
            WHERE site_id=? AND source_type=? AND source_id=?
            LIMIT 1
            """,
            (site_id, source_type, int(source_id)),
        ).fetchone()


def _record_mapping(
    site_id: int,
    source_type: str,
    source_id: int,
    canonical_type: str,
    canonical_id: int,
) -> None:
    ensure_schema()
    with tenant_auth.db() as conn:
        conn.execute(
            """
            INSERT OR IGNORE INTO creator_legacy_mappings(
                site_id, source_type, source_id,
                canonical_type, canonical_id, created_at
            ) VALUES(?,?,?,?,?,?)
            """,
            (
                site_id,
                source_type,
                int(source_id),
                canonical_type,
                int(canonical_id),
                tenant_auth.now(),
            ),
        )
        conn.commit()


def _safe_target(value: str) -> bool:
    clean = (value or '').strip()
    if not clean:
        return False
    if clean.startswith('/'):
        return not clean.startswith('//')
    parsed = urlsplit(clean)
    return (
        parsed.scheme.lower() == 'https'
        and bool(parsed.netloc)
        and parsed.username is None
        and parsed.password is None
    )


def _profile_seed(site) -> tuple[str, str, str]:
    branding = tenant_branding.get_branding(ORGANIZATION)
    display_name = (
        branding.site_name.strip()
        if branding and branding.site_name.strip()
        else site.name.strip()
    )
    bio = branding.tagline.strip() if branding else ''
    avatar = branding.logo_url.strip() if branding else ''
    if avatar and not _safe_target(avatar):
        avatar = ''
    return display_name, bio, avatar


def migrate_adventures_content() -> AdventuresMigrationResult:
    """Stage safe legacy Adventures records as draft canonical creator data."""
    site = tenant_sites.get_site(ORGANIZATION, SITE)
    if site is None or site.status == 'archived':
        raise ValueError('An active Adventures main site is required.')

    ensure_schema()
    site_navigation.ensure_schema()
    site_pages.ensure_schema()
    site_media.ensure_schema()

    created_profile = 0
    created_links = 0
    created_collections = 0
    created_items = 0
    already_mapped = 0
    preserved_canonical = 0
    unsafe_records = 0
    unmatched_records = 0
    issues: list[str] = []

    profile_source_id = site.id
    if _mapping(site.id, 'site_profile', profile_source_id):
        already_mapped += 1
    else:
        existing_profile = creator_profiles.get_profile(ORGANIZATION, SITE)
        if existing_profile is not None:
            preserved_canonical += 1
            issues.append(
                'profile: canonical creator profile already exists; preserved unchanged'
            )
        else:
            display_name, bio, avatar = _profile_seed(site)
            profile = creator_profiles.upsert_profile(
                ORGANIZATION,
                SITE,
                display_name=display_name,
                bio=bio,
                avatar_url=avatar,
                status='draft',
            )
            _record_mapping(
                site.id, 'site_profile', profile_source_id, 'profile', profile.site_id
            )
            created_profile += 1

    for nav in site_navigation.list_items(ORGANIZATION, SITE):
        if _mapping(site.id, 'navigation', nav.id):
            already_mapped += 1
            continue
        if not _safe_target(nav.target):
            unsafe_records += 1
            issues.append(
                f'navigation:{nav.id}: unsafe target not migrated: {nav.target}'
            )
            continue
        link = creator_profiles.create_link(
            ORGANIZATION,
            SITE,
            label=nav.label,
            target=nav.target,
            position=nav.position,
            status='draft',
        )
        _record_mapping(site.id, 'navigation', nav.id, 'link', link.id)
        created_links += 1

    page_rows = site_pages.list_pages(
        ORGANIZATION, SITE, include_archived=False
    )
    page_collection = None
    if page_rows:
        if _mapping(site.id, 'page_collection', site.id):
            already_mapped += 1
            mapping = _mapping(site.id, 'page_collection', site.id)
            if mapping:
                page_collection = creator_collections.get_collection(
                    ORGANIZATION, SITE, int(mapping['canonical_id'])
                )
        else:
            existing = next(
                (
                    c for c in creator_collections.list_collections(
                        ORGANIZATION, SITE, include_archived=True
                    )
                    if c.slug == PAGES_COLLECTION_SLUG
                ),
                None,
            )
            if existing is not None:
                preserved_canonical += 1
                unmatched_records += len(page_rows)
                issues.append(
                    'pages: legacy-pages collection already exists; legacy pages left unmatched'
                )
            else:
                page_collection = creator_collections.create_collection(
                    ORGANIZATION,
                    SITE,
                    slug=PAGES_COLLECTION_SLUG,
                    title='Legacy site pages',
                    description='Staged links to existing Adventures Site Builder pages.',
                    position=0,
                    status='draft',
                )
                _record_mapping(
                    site.id,
                    'page_collection',
                    site.id,
                    'collection',
                    page_collection.id,
                )
                created_collections += 1

        if page_collection is not None:
            for page in page_rows:
                if _mapping(site.id, 'page', page.id):
                    already_mapped += 1
                    continue
                item = creator_collections.create_item(
                    ORGANIZATION,
                    SITE,
                    page_collection.id,
                    title=page.title,
                    target='/' if page.slug == 'home' else f'/{page.slug}',
                    position=page.position,
                )
                _record_mapping(site.id, 'page', page.id, 'collection_item', item.id)
                created_items += 1

    media_rows = site_media.list_media(
        ORGANIZATION, SITE, include_archived=False
    )
    safe_media = []
    for media in media_rows:
        if _mapping(site.id, 'media', media.id):
            already_mapped += 1
            continue
        if not _safe_target(media.source):
            unsafe_records += 1
            issues.append(
                f'media:{media.id}: unsafe source not migrated: {media.source}'
            )
            continue
        safe_media.append(media)

    media_collection = None
    if safe_media:
        if _mapping(site.id, 'media_collection', site.id):
            already_mapped += 1
            mapping = _mapping(site.id, 'media_collection', site.id)
            if mapping:
                media_collection = creator_collections.get_collection(
                    ORGANIZATION, SITE, int(mapping['canonical_id'])
                )
        else:
            existing = next(
                (
                    c for c in creator_collections.list_collections(
                        ORGANIZATION, SITE, include_archived=True
                    )
                    if c.slug == MEDIA_COLLECTION_SLUG
                ),
                None,
            )
            if existing is not None:
                preserved_canonical += 1
                unmatched_records += len(safe_media)
                issues.append(
                    'media: legacy-media collection already exists; legacy media left unmatched'
                )
            else:
                media_collection = creator_collections.create_collection(
                    ORGANIZATION,
                    SITE,
                    slug=MEDIA_COLLECTION_SLUG,
                    title='Legacy media',
                    description='Staged links to existing Adventures Site Builder media.',
                    position=1,
                    status='draft',
                )
                _record_mapping(
                    site.id,
                    'media_collection',
                    site.id,
                    'collection',
                    media_collection.id,
                )
                created_collections += 1

        if media_collection is not None:
            for media in safe_media:
                item = creator_collections.create_item(
                    ORGANIZATION,
                    SITE,
                    media_collection.id,
                    title=media.alt_text.strip() or media.slug,
                    target=media.source,
                    position=0,
                )
                _record_mapping(site.id, 'media', media.id, 'collection_item', item.id)
                created_items += 1

    # Legacy navigation has no explicit affiliate/network/disclosure semantics.
    # Never infer affiliate records from labels or URLs.
    unmatched_affiliate_candidates = sum(
        1
        for nav in site_navigation.list_items(ORGANIZATION, SITE)
        if 'affiliate' in nav.label.lower()
    )
    if unmatched_affiliate_candidates:
        unmatched_records += unmatched_affiliate_candidates
        issues.append(
            f'affiliates: {unmatched_affiliate_candidates} labeled navigation record(s) '
            'require manual disclosure/network review'
        )

    return AdventuresMigrationResult(
        created_profile=created_profile,
        created_links=created_links,
        created_collections=created_collections,
        created_items=created_items,
        already_mapped=already_mapped,
        preserved_canonical=preserved_canonical,
        unsafe_records=unsafe_records,
        unmatched_records=unmatched_records,
        issues=tuple(issues),
    )
