from __future__ import annotations

import creator_affiliates
import creator_analytics
import creator_auth
import creator_collections
import creator_downloads
import creator_profiles
import creator_storefront


def summary(user_id:int,organization_slug:str,site_slug:str)->dict[str,int]:
    creator_auth.require_site(user_id,organization_slug,site_slug,'view')
    return {
        'links':len(creator_profiles.list_links(organization_slug,site_slug)),
        'affiliates':len(creator_affiliates.list_affiliates(organization_slug,site_slug)),
        'collections':len(creator_collections.list_collections(organization_slug,site_slug)),
        'downloads':len(creator_downloads.list_downloads(organization_slug,site_slug)),
        'products':len(creator_storefront.list_products(organization_slug,site_slug)),
        'analytics_events':len(creator_analytics.list_events(organization_slug,site_slug,limit=500)),
    }


def upsert_profile(user_id:int,organization_slug:str,site_slug:str,**kwargs):
    creator_auth.require_site(user_id,organization_slug,site_slug,'profiles')
    return creator_profiles.upsert_profile(organization_slug,site_slug,**kwargs)


def create_link(user_id:int,organization_slug:str,site_slug:str,**kwargs):
    creator_auth.require_site(user_id,organization_slug,site_slug,'links')
    return creator_profiles.create_link(organization_slug,site_slug,**kwargs)


def create_affiliate(user_id:int,organization_slug:str,site_slug:str,**kwargs):
    creator_auth.require_site(user_id,organization_slug,site_slug,'affiliates')
    return creator_affiliates.create_affiliate(organization_slug,site_slug,**kwargs)


def create_collection(user_id:int,organization_slug:str,site_slug:str,**kwargs):
    creator_auth.require_site(user_id,organization_slug,site_slug,'collections')
    return creator_collections.create_collection(organization_slug,site_slug,**kwargs)


def create_collection_item(
    user_id:int,
    organization_slug:str,
    site_slug:str,
    collection_id:int,
    **kwargs,
):
    creator_auth.require_site(user_id,organization_slug,site_slug,'collections')
    return creator_collections.create_item(
        organization_slug,site_slug,collection_id,**kwargs
    )


def create_download(user_id:int,organization_slug:str,site_slug:str,**kwargs):
    creator_auth.require_site(user_id,organization_slug,site_slug,'downloads')
    return creator_downloads.create_download(organization_slug,site_slug,**kwargs)


def create_product(user_id:int,organization_slug:str,site_slug:str,**kwargs):
    creator_auth.require_site(user_id,organization_slug,site_slug,'products')
    return creator_storefront.create_product(organization_slug,site_slug,**kwargs)


def analytics(
    user_id:int,
    organization_slug:str,
    site_slug:str,
    **kwargs,
):
    creator_auth.require_site(user_id,organization_slug,site_slug,'analytics')
    return creator_analytics.list_events(organization_slug,site_slug,**kwargs)


def require_administration(
    user_id:int,
    organization_slug:str,
    site_slug:str,
)->None:
    creator_auth.require_site(
        user_id,organization_slug,site_slug,'creator_admin'
    )
