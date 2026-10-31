from __future__ import annotations

from dataclasses import dataclass
import sqlite3

import creator_downloads
import tenant_auth
import tenant_sites


PRODUCT_TYPES = ('service','digital_download','physical','external')
PRODUCT_STATUSES = ('draft','published','archived')


@dataclass(frozen=True)
class StorefrontProduct:
    id: int
    site_id: int
    organization_slug: str
    site_slug: str
    title: str
    description: str
    product_type: str
    price_cents: int | None
    currency: str
    download_id: int | None
    external_url: str
    position: int
    status: str
    created_at: int
    updated_at: int


def ensure_schema() -> None:
    creator_downloads.ensure_schema()
    with tenant_auth.db() as conn:
        conn.execute(
            '''
            CREATE TABLE IF NOT EXISTS creator_products (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                site_id INTEGER NOT NULL,
                title TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                product_type TEXT NOT NULL,
                price_cents INTEGER,
                currency TEXT NOT NULL DEFAULT 'USD',
                download_id INTEGER,
                external_url TEXT NOT NULL DEFAULT '',
                position INTEGER NOT NULL DEFAULT 0,
                status TEXT NOT NULL DEFAULT 'draft',
                created_at INTEGER NOT NULL,
                updated_at INTEGER NOT NULL,
                CHECK(product_type IN ('service','digital_download','physical','external')),
                CHECK(price_cents IS NULL OR price_cents >= 0),
                CHECK(status IN ('draft','published','archived')),
                FOREIGN KEY(site_id)
                    REFERENCES site_builder_sites(id) ON DELETE CASCADE,
                FOREIGN KEY(download_id)
                    REFERENCES creator_downloads(id) ON DELETE SET NULL
            )
            '''
        )
        conn.execute(
            'CREATE INDEX IF NOT EXISTS idx_creator_products_site_status_position '
            'ON creator_products(site_id,status,position,id)'
        )
        conn.commit()


def _site(organization_slug: str, site_slug: str):
    site=tenant_sites.get_site(organization_slug,site_slug)
    if site is None:
        raise ValueError('Site not found.')
    return site


def _text(value: str, *, field: str, limit: int, required: bool=False) -> str:
    clean=(value or '').strip()
    if required and not clean:
        raise ValueError(f'{field} is required.')
    if len(clean)>limit:
        raise ValueError(f'{field} must be {limit} characters or fewer.')
    return clean


def _product_type(value: str) -> str:
    clean=(value or '').strip().lower()
    if clean not in PRODUCT_TYPES:
        raise ValueError(f'Unknown product type: {clean}')
    return clean


def _status(value: str) -> str:
    clean=(value or '').strip().lower()
    if clean not in PRODUCT_STATUSES:
        raise ValueError(f'Unknown product status: {clean}')
    return clean


def _price(value: int | None) -> int | None:
    if value is None:
        return None
    if isinstance(value,bool):
        raise ValueError('Price must be a non-negative integer number of cents.')
    try:
        clean=int(value)
    except (TypeError,ValueError) as exc:
        raise ValueError('Price must be a non-negative integer number of cents.') from exc
    if clean<0:
        raise ValueError('Price must be a non-negative integer number of cents.')
    return clean


def _currency(value: str) -> str:
    clean=(value or 'USD').strip().upper()
    if len(clean)!=3 or not clean.isalpha():
        raise ValueError('Currency must be a three-letter ISO code.')
    return clean


def _position(value: int) -> int:
    if isinstance(value,bool):
        raise ValueError('Product position must be an integer.')
    try:
        clean=int(value)
    except (TypeError,ValueError) as exc:
        raise ValueError('Product position must be an integer.') from exc
    if clean<0:
        raise ValueError('Product position cannot be negative.')
    return clean


def _external_url(value: str) -> str:
    clean=(value or '').strip()
    if not clean:
        return ''
    return creator_downloads._source_ref('external_url',clean)


def _validate_download(site_id: int, download_id: int | None) -> None:
    if download_id is None:
        return
    with tenant_auth.db() as conn:
        row=conn.execute(
            'SELECT id FROM creator_downloads WHERE id=? AND site_id=?',
            (int(download_id),site_id),
        ).fetchone()
    if row is None:
        raise ValueError('Product download must belong to the same site.')


def _validate_type_relationships(
    product_type: str,
    download_id: int | None,
    external_url: str,
) -> None:
    if product_type=='digital_download' and download_id is None:
        raise ValueError('Digital-download products require a download record.')
    if product_type!='digital_download' and download_id is not None:
        raise ValueError('Only digital-download products may link a download record.')
    if product_type=='external' and not external_url:
        raise ValueError('External products require an external URL.')
    if product_type!='external' and external_url:
        raise ValueError('Only external products may define an external URL.')


def create_product(
    organization_slug: str,
    site_slug: str,
    *,
    title: str,
    product_type: str,
    description: str='',
    price_cents: int | None=None,
    currency: str='USD',
    download_id: int | None=None,
    external_url: str='',
    position: int=0,
    status: str='draft',
) -> StorefrontProduct:
    site=_site(organization_slug,site_slug)
    if site.status=='archived':
        raise ValueError('Archived sites cannot be updated.')
    ensure_schema()
    clean_type=_product_type(product_type)
    clean_url=_external_url(external_url)
    _validate_download(site.id,download_id)
    _validate_type_relationships(clean_type,download_id,clean_url)
    now=tenant_auth.now()
    with tenant_auth.db() as conn:
        cur=conn.execute(
            '''
            INSERT INTO creator_products(
                site_id,title,description,product_type,price_cents,currency,
                download_id,external_url,position,status,created_at,updated_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
            ''',
            (
                site.id,
                _text(title,field='Product title',limit=200,required=True),
                _text(description,field='Product description',limit=4000),
                clean_type,
                _price(price_cents),
                _currency(currency),
                download_id,
                clean_url,
                _position(position),
                _status(status),
                now,now,
            ),
        )
        conn.commit()
        row=_select(conn,site.id,int(cur.lastrowid))
    return _from_row(row)


def get_product(organization_slug: str,site_slug: str,product_id: int) -> StorefrontProduct | None:
    site=tenant_sites.get_site(organization_slug,site_slug)
    if site is None:
        return None
    ensure_schema()
    with tenant_auth.db() as conn:
        row=_select(conn,site.id,int(product_id))
    return _from_row(row) if row else None


def list_products(
    organization_slug: str,
    site_slug: str,
    *,
    published_only: bool=False,
    include_archived: bool=False,
) -> list[StorefrontProduct]:
    site=tenant_sites.get_site(organization_slug,site_slug)
    if site is None:
        return []
    ensure_schema()
    sql='''
        SELECT p.*,o.slug AS organization_slug,s.slug AS site_slug
        FROM creator_products p
        JOIN site_builder_sites s ON s.id=p.site_id
        JOIN auth_organizations o ON o.id=s.organization_id
        WHERE p.site_id=?
    '''
    params:[object]=[site.id]
    if published_only:
        sql+=" AND p.status='published'"
    elif not include_archived:
        sql+=" AND p.status!='archived'"
    sql+=' ORDER BY p.position,p.id'
    with tenant_auth.db() as conn:
        rows=conn.execute(sql,params).fetchall()
    return [_from_row(row) for row in rows]


def update_product(
    organization_slug: str,
    site_slug: str,
    product_id: int,
    **changes,
) -> StorefrontProduct | None:
    site=tenant_sites.get_site(organization_slug,site_slug)
    if site is None:
        return None
    if site.status=='archived':
        raise ValueError('Archived sites cannot be updated.')
    existing=get_product(organization_slug,site_slug,product_id)
    if existing is None:
        return None
    if existing.status=='archived':
        raise ValueError('Archived products cannot be updated.')

    allowed={'title','description','product_type','price_cents','currency','download_id','external_url','position','status'}
    unknown=set(changes)-allowed
    if unknown:
        raise ValueError(f'Unknown product fields: {sorted(unknown)}')

    values={
        'title':existing.title,
        'description':existing.description,
        'product_type':existing.product_type,
        'price_cents':existing.price_cents,
        'currency':existing.currency,
        'download_id':existing.download_id,
        'external_url':existing.external_url,
        'position':existing.position,
        'status':existing.status,
    }
    values.update(changes)
    clean_type=_product_type(values['product_type'])
    clean_url=_external_url(values['external_url'])
    _validate_download(site.id,values['download_id'])
    _validate_type_relationships(clean_type,values['download_id'],clean_url)

    with tenant_auth.db() as conn:
        conn.execute(
            '''
            UPDATE creator_products
            SET title=?,description=?,product_type=?,price_cents=?,currency=?,
                download_id=?,external_url=?,position=?,status=?,updated_at=?
            WHERE site_id=? AND id=?
            ''',
            (
                _text(values['title'],field='Product title',limit=200,required=True),
                _text(values['description'],field='Product description',limit=4000),
                clean_type,
                _price(values['price_cents']),
                _currency(values['currency']),
                values['download_id'],
                clean_url,
                _position(values['position']),
                _status(values['status']),
                tenant_auth.now(),
                site.id,
                int(product_id),
            ),
        )
        conn.commit()
        row=_select(conn,site.id,int(product_id))
    return _from_row(row)


def archive_product(organization_slug: str,site_slug: str,product_id: int) -> StorefrontProduct | None:
    existing=get_product(organization_slug,site_slug,product_id)
    if existing is None or existing.status=='archived':
        return existing
    return update_product(
        organization_slug,site_slug,product_id,status='archived'
    )


def _select(conn: sqlite3.Connection,site_id: int,product_id: int):
    return conn.execute(
        '''
        SELECT p.*,o.slug AS organization_slug,s.slug AS site_slug
        FROM creator_products p
        JOIN site_builder_sites s ON s.id=p.site_id
        JOIN auth_organizations o ON o.id=s.organization_id
        WHERE p.site_id=? AND p.id=?
        LIMIT 1
        ''',
        (site_id,product_id),
    ).fetchone()


def _from_row(row) -> StorefrontProduct:
    return StorefrontProduct(
        id=int(row['id']),
        site_id=int(row['site_id']),
        organization_slug=str(row['organization_slug']),
        site_slug=str(row['site_slug']),
        title=str(row['title']),
        description=str(row['description']),
        product_type=str(row['product_type']),
        price_cents=int(row['price_cents']) if row['price_cents'] is not None else None,
        currency=str(row['currency']),
        download_id=int(row['download_id']) if row['download_id'] is not None else None,
        external_url=str(row['external_url']),
        position=int(row['position']),
        status=str(row['status']),
        created_at=int(row['created_at']),
        updated_at=int(row['updated_at']),
    )
