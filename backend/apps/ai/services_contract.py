"""
Contract between the AI agent and the feature apps owned by Members 2-4.

The AI tool registry never touches another app's models. Each tool calls ONE
service function, found by dotted path in ``SERVICE_PROVIDERS`` (override in
settings with ``AI_SERVICE_PROVIDERS``). Until that function exists, the tool
returns ``NOT_AVAILABLE`` and Grok tells the user honestly.

To implement a service:
  1. Create the module named below (e.g. ``apps/listings/ai_services.py``).
  2. Define the function with exactly the signature in the matching Protocol.
  3. Return the matching TypedDict shape. Use plain JSON types (str, int,
     float, bool, None, list, dict); dates/decimals as ISO strings / numbers.
  4. Never return another user's email, phone number, exact coordinates or
     street address. Use ``apps.locations.serializers.public_location()`` for
     locations. (The registry also strips those keys as a safety net.)
  5. Run every query AS ``user``: only return what that user may see.

The tool's ``data`` arguments are already validated by the tool's input
serializer (see ``apps/ai/tools/definitions.py``). Dates arrive as
``datetime.date``, money/quantities as ``decimal.Decimal``.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Literal, Protocol, TypedDict

NOT_AVAILABLE = {"available": False, "reason": "This feature is not implemented yet."}

# tool name -> "dotted.module.path.function_name"
SERVICE_PROVIDERS: dict[str, str] = {
    # Member 1 (implemented)
    "find_nearby_farmers": "apps.locations.services.find_nearby_farmers",
    # Member 3 (buyers, requirements, orders, messaging)
    "search_recommended_farmers": "apps.buyers.ai_services.search_recommended_farmers",
    # Member 2 (farmer profiles, produce listings)
    "search_buyer_requirements": "apps.listings.ai_services.search_buyer_requirements",
    "create_or_update_listing": "apps.listings.services.create_or_update_listing",
    # Member 4 (cooperation: groups, bulk buying, transport, equipment)
    "find_bulk_purchases": "apps.cooperation.ai_services.find_bulk_purchases",
    "calculate_cost_shares": "apps.cooperation.ai_services.calculate_cost_shares",
    "find_transport_requests": "apps.cooperation.ai_services.find_transport_requests",
    "find_farmer_groups": "apps.cooperation.ai_services.find_farmer_groups",
    "find_equipment": "apps.cooperation.ai_services.find_equipment",
}


# --- Shared shapes ----------------------------------------------------------------

class Distance(TypedDict):
    km: int | None  # rounded, None when not GPS-based
    basis: Literal["gps", "same_town", "same_municipality", "same_province", "different_province", "unknown"]
    label: str  # e.g. "≈ 12 km", "Same municipality"


class PublicLocation(TypedDict):
    """Output of apps.locations.serializers.public_location(). No coordinates."""

    province: str
    province_display: str
    municipality: str
    town: str
    distance: Distance


class NotAvailable(TypedDict):
    available: Literal[False]
    reason: str


class ResultList(TypedDict, total=False):
    """Every search service returns this envelope."""

    available: Literal[True]
    count: int
    results: list  # list of the per-tool item TypedDict below
    message: str  # optional note for the user, e.g. "Set your location first"


# --- find_nearby_farmers (Member 1, implemented in apps.locations.services) -------

class NearbyFarmer(TypedDict):
    farmer_id: int
    display_name: str
    location: PublicLocation


class FindNearbyFarmers(Protocol):
    def __call__(self, user, *, max_distance_km: int | None = None, limit: int = 10) -> ResultList: ...


# --- search_recommended_farmers (Member 3) ---------------------------------------

class FarmerMatch(TypedDict):
    farmer_id: int
    farmer_display_name: str
    listing_id: int
    produce: str
    available_quantity: float
    unit: str
    price_per_unit: float  # ZAR
    available_from: str | None  # ISO date
    location: PublicLocation  # town/municipality + approximate distance
    match_reasons: list[str]  # e.g. ["Grows potatoes", "≈ 12 km away", "Enough stock"]
    shortfall: str | None  # e.g. "Has 300 kg of the 500 kg you need"


class SearchRecommendedFarmers(Protocol):
    def __call__(
        self, user, *, produce: str, quantity: Decimal, unit: str,
        max_distance_km: int | None = None, needed_by: date | None = None, limit: int = 10,
    ) -> ResultList: ...  # results: list[FarmerMatch], best match first


# --- search_buyer_requirements (Member 2) ----------------------------------------

class BuyerRequirementMatch(TypedDict):
    requirement_id: int
    buyer_id: int
    buyer_display_name: str
    buyer_type: str  # e.g. "restaurant", "supermarket"
    produce: str
    quantity: float
    unit: str
    target_price_per_unit: float | None
    needed_by: str | None  # ISO date
    location: PublicLocation
    match_reasons: list[str]


class SearchBuyerRequirements(Protocol):
    def __call__(
        self, user, *, produce: str | None = None, max_distance_km: int | None = None, limit: int = 10,
    ) -> ResultList: ...  # results: list[BuyerRequirementMatch]


# --- create_or_update_listing (Member 2) - REQUIRES CONFIRMATION ------------------

class ListingResult(TypedDict):
    available: Literal[True]
    listing_id: int
    created: bool  # False if an existing listing was updated
    produce: str
    quantity: float
    unit: str
    price_per_unit: float
    available_from: str | None
    available_until: str | None


class CreateOrUpdateListing(Protocol):
    """Only ever called after the user confirmed. Must check that ``listing_id``
    (if given) belongs to ``user`` and raise PermissionDenied otherwise."""

    def __call__(
        self, user, *, produce: str, quantity: Decimal, unit: str, price_per_unit: Decimal,
        listing_id: int | None = None, available_from: date | None = None,
        available_until: date | None = None, notes: str = "",
    ) -> ListingResult: ...


# --- Member 4: cooperation --------------------------------------------------------

class BulkPurchaseMatch(TypedDict):
    bulk_purchase_id: int
    title: str
    item: str
    organiser_display_name: str
    unit_price: float | None
    quantity_committed: float
    quantity_target: float
    unit: str
    closes_at: str | None
    location: PublicLocation


class FindBulkPurchases(Protocol):
    def __call__(self, user, *, item: str | None = None, max_distance_km: int | None = None,
                 limit: int = 10) -> ResultList: ...  # results: list[BulkPurchaseMatch]


class CostShare(TypedDict):
    label: str
    quantity: float | None
    share_amount: float  # ZAR, rounded to cents
    share_percent: float


class CostShareResult(TypedDict):
    available: Literal[True]
    total_cost: float
    split_method: Literal["equal", "by_quantity"]
    shares: list[CostShare]  # sums exactly to total_cost


class CalculateCostShares(Protocol):
    """Pure calculation; must not save anything or commit anyone."""

    def __call__(self, user, *, total_cost: Decimal, split_method: str,
                 participants: list[dict]) -> CostShareResult: ...


class TransportRequestMatch(TypedDict):
    transport_request_id: int
    requester_display_name: str
    from_location: PublicLocation
    to_town: str
    to_municipality: str
    travel_date: str | None
    space_available: str | None
    cost_estimate: float | None


class FindTransportRequests(Protocol):
    def __call__(self, user, *, destination_town: str | None = None, travel_date: date | None = None,
                 max_distance_km: int | None = None, limit: int = 10) -> ResultList: ...


class FarmerGroupMatch(TypedDict):
    group_id: int
    name: str
    focus: str
    member_count: int
    location: PublicLocation
    is_member: bool


class FindFarmerGroups(Protocol):
    def __call__(self, user, *, focus: str | None = None, max_distance_km: int | None = None,
                 limit: int = 10) -> ResultList: ...


class EquipmentMatch(TypedDict):
    equipment_id: int
    name: str
    equipment_type: str
    owner_display_name: str
    daily_rate: float | None
    available_from: str | None
    available_until: str | None
    location: PublicLocation


class FindEquipment(Protocol):
    def __call__(self, user, *, equipment_type: str | None = None, needed_from: date | None = None,
                 needed_until: date | None = None, max_distance_km: int | None = None,
                 limit: int = 10) -> ResultList: ...
