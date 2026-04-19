from typing import TypedDict, NotRequired


class AddressComponents(TypedDict, total=False):
    street: str
    number: str
    neighborhood: str
    city: str
    state: str
    state_code: str
    zip_code: str
    country: str
    country_code: str


class GeoPoint(TypedDict):
    lat: float
    lng: float


class GeocodeResult(TypedDict, total=False):
    lat: float
    lng: float
    formatted_address: str
    place_id: NotRequired[str | None]
    address_components: AddressComponents
    address: dict
    provider: str


class RouteResult(TypedDict, total=False):
    distance_km: float
    distance_meters: int
    duration_minutes: float
    duration_seconds: int
    polyline: str | None
    departure: dict
    arrival: dict
    fallback: bool
    provider: str
