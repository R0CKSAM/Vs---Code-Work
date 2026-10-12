"""
Media Reporting System - Phase 6 Advertisement Monitoring & History Endpoints
Exposes current ad intelligence, creative asset telemetry, and historical revision logs.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from database.repository import db_repo

router = APIRouter(prefix="/monitoring", tags=["Advertisement Monitoring"])


# ---------------------------------------------------------------------------
# Pydantic Response Schemas
# ---------------------------------------------------------------------------

class AdvertisementItem(BaseModel):
    id: int
    website_id: int
    website_name: Optional[str] = None
    website_key: Optional[str] = None
    section_name: Optional[str] = "Overall"
    page_url: str
    advertiser: Optional[str] = None
    brand: Optional[str] = None
    campaign: Optional[str] = None
    ad_type: str
    position: str
    image_url: Optional[str] = None
    local_image_path: Optional[str] = None
    target_url: Optional[str] = None
    ad_hash: str
    first_seen_at: str
    last_seen_at: str
    status: str
    removed_at: Optional[str] = None


class AdvertisementVersionItem(BaseModel):
    id: int
    advertisement_id: int
    version_number: int
    advertiser: Optional[str] = None
    brand: Optional[str] = None
    campaign: Optional[str] = None
    ad_type: str
    position: str
    image_url: Optional[str] = None
    local_image_path: Optional[str] = None
    target_url: Optional[str] = None
    ad_hash: str
    detected_at: str
    change_type: str


class AdvertisementHistoryResponse(BaseModel):
    advertisement: AdvertisementItem
    total_versions: int
    versions: List[AdvertisementVersionItem]


class AdvertisementKPIsResponse(BaseModel):
    total_ads: int = 0
    active_ads: int = 0
    removed_ads: int = 0
    changed_ads: int = 0
    unique_advertisers: int = 0
    unique_brands: int = 0


class AdvertisementsListResponse(BaseModel):
    count: int
    total: int
    kpis: AdvertisementKPIsResponse
    advertisements: List[AdvertisementItem]


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/advertisements/kpis", response_model=AdvertisementKPIsResponse)
async def get_ad_kpis(
    website: Optional[str] = Query(None, description="Optional website key filter"),
    identified_only: bool = Query(True, description="Count only advertisements with a verified identity"),
):
    """Returns aggregated KPI summary metrics for advertisements."""
    website_key = None if website in (None, "all", "") else website
    return db_repo.get_advertisement_kpis(
        website_key=website_key, identified_only=identified_only
    )


@router.get("/advertisements", response_model=AdvertisementsListResponse)
async def get_advertisements(
    website: Optional[str] = Query(None, description="Filter by website key (e.g. et_brand_equity, exchange4media)"),
    section: Optional[str] = Query(None, description="Filter by section"),
    status: Optional[str] = Query(None, description="Filter by status (ACTIVE, REMOVED, CHANGED, ALL)"),
    advertiser: Optional[str] = Query(None, description="Filter by advertiser name"),
    brand: Optional[str] = Query(None, description="Filter by brand name"),
    campaign: Optional[str] = Query(None, description="Filter by campaign name"),
    ad_type: Optional[str] = Query(None, description="Filter by ad type (IMAGE, BANNER, SPONSORED, IFRAME, STICKY)"),
    search: Optional[str] = Query(None, description="Full-text search query across brands, advertisers, campaigns, positions"),
    limit: int = Query(50, ge=1, le=200),
    skip: int = Query(0, ge=0),
    identified_only: bool = Query(True, description="Exclude placements without a verified advertiser or brand"),
):
    """
    Returns current advertisements tracked across media websites with filtering and pagination.
    """
    website_key = None if website in (None, "all", "") else website
    ads = db_repo.get_advertisements(
        website_key=website_key,
        section_name=section,
        status=status,
        advertiser=advertiser,
        brand=brand,
        campaign=campaign,
        ad_type=ad_type,
        search=search,
        limit=limit,
        skip=skip,
        identified_only=identified_only,
    )
    total_count = db_repo.count_advertisements(
        website_key=website_key,
        section_name=section,
        status=status,
        search=search,
        advertiser=advertiser, brand=brand, campaign=campaign, ad_type=ad_type,
        identified_only=identified_only,
    )
    kpis = db_repo.get_advertisement_kpis(
        website_key=website_key, identified_only=identified_only
    )

    formatted_ads = [AdvertisementItem(**a) for a in ads]

    return AdvertisementsListResponse(
        count=len(formatted_ads),
        total=total_count,
        kpis=AdvertisementKPIsResponse(**kpis),
        advertisements=formatted_ads,
    )


@router.get("/advertisements/{advertisement_id}", response_model=AdvertisementItem)
async def get_advertisement_detail(advertisement_id: int):
    """Returns single advertisement details by ID."""
    ad = db_repo.get_advertisement_by_id(advertisement_id)
    if not ad:
        raise HTTPException(status_code=404, detail=f"Advertisement '{advertisement_id}' not found")
    return AdvertisementItem(**ad)


@router.get("/advertisements/{advertisement_id}/history", response_model=AdvertisementHistoryResponse)
async def get_advertisement_history(advertisement_id: int):
    """Returns complete chronological creative revision history for an advertisement."""
    ad = db_repo.get_advertisement_by_id(advertisement_id)
    if not ad:
        raise HTTPException(status_code=404, detail=f"Advertisement '{advertisement_id}' not found")

    versions = db_repo.get_advertisement_versions(advertisement_id)
    formatted_versions = [AdvertisementVersionItem(**v) for v in versions]

    return AdvertisementHistoryResponse(
        advertisement=AdvertisementItem(**ad),
        total_versions=len(formatted_versions),
        versions=formatted_versions,
    )


@router.get("/{website}/advertisements", response_model=AdvertisementsListResponse)
async def get_website_advertisements(
    website: str,
    section: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    skip: int = Query(0, ge=0),
):
    """Website-specific advertisement endpoint."""
    return await get_advertisements(
        website=website,
        section=section,
        status=status,
        limit=limit,
        skip=skip,
        advertiser=None, brand=None, campaign=None, ad_type=None, search=None,
        identified_only=True,
    )
