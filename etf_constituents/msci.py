"""Country -> (Region, Category) according to the MSCI Market Classification.

Category: Developed | Emerging | Frontier | Financial Center | Other
Region:   North America | Latin America | Developed Europe | Emerging Europe & CIS |
          Middle East | Africa | Developed Asia Pacific | Emerging Asia | Caribbean | Other

The table is keyed by ISO 3166-1 alpha-2 code, not by name: issuers use non-ISO names
("Croatia (Hrvatska)", "Korea (South)") and resolving them to a code before
classifying avoids having to list every variant.

Note: the European Frontier markets (Croatia, Estonia, Iceland, Romania, ...) fall
under the "Emerging Europe & CIS" region, which follows the MSCI
"Frontier Markets Europe & CIS" index family and does not imply the country Category.
"""

from __future__ import annotations

import re
import sys

import pycountry

DEVELOPED = "Developed"
EMERGING = "Emerging"
FRONTIER = "Frontier"
FINANCIAL_CENTER = "Financial Center"
OTHER = "Other"

NORTH_AMERICA = "North America"
LATIN_AMERICA = "Latin America"
DEVELOPED_EUROPE = "Developed Europe"
EMERGING_EUROPE = "Emerging Europe & CIS"
MIDDLE_EAST = "Middle East"
AFRICA = "Africa"
DEVELOPED_ASIA = "Developed Asia Pacific"
EMERGING_ASIA = "Emerging Asia"
CARIBBEAN = "Caribbean"

# --- MSCI Developed Markets (23) ------------------------------------------------
_DEVELOPED = {
    "CA": NORTH_AMERICA,
    "US": NORTH_AMERICA,
    "AT": DEVELOPED_EUROPE,
    "BE": DEVELOPED_EUROPE,
    "DK": DEVELOPED_EUROPE,
    "FI": DEVELOPED_EUROPE,
    "FR": DEVELOPED_EUROPE,
    "DE": DEVELOPED_EUROPE,
    "IE": DEVELOPED_EUROPE,
    "IT": DEVELOPED_EUROPE,
    "NL": DEVELOPED_EUROPE,
    "NO": DEVELOPED_EUROPE,
    "PT": DEVELOPED_EUROPE,
    "ES": DEVELOPED_EUROPE,
    "SE": DEVELOPED_EUROPE,
    "CH": DEVELOPED_EUROPE,
    "GB": DEVELOPED_EUROPE,
    "IL": MIDDLE_EAST,
    "AU": DEVELOPED_ASIA,
    "HK": DEVELOPED_ASIA,
    "JP": DEVELOPED_ASIA,
    "NZ": DEVELOPED_ASIA,
    "SG": DEVELOPED_ASIA,
}

# --- MSCI Emerging Markets (24) -------------------------------------------------
_EMERGING = {
    "BR": LATIN_AMERICA,
    "CL": LATIN_AMERICA,
    "CO": LATIN_AMERICA,
    "MX": LATIN_AMERICA,
    "PE": LATIN_AMERICA,
    "CZ": EMERGING_EUROPE,
    "GR": EMERGING_EUROPE,
    "HU": EMERGING_EUROPE,
    "PL": EMERGING_EUROPE,
    "TR": EMERGING_EUROPE,
    "EG": AFRICA,
    "ZA": AFRICA,
    "KW": MIDDLE_EAST,
    "QA": MIDDLE_EAST,
    "SA": MIDDLE_EAST,
    "AE": MIDDLE_EAST,
    "CN": EMERGING_ASIA,
    "IN": EMERGING_ASIA,
    "ID": EMERGING_ASIA,
    "KR": EMERGING_ASIA,
    "MY": EMERGING_ASIA,
    "PH": EMERGING_ASIA,
    "TW": EMERGING_ASIA,
    "TH": EMERGING_ASIA,
}

# --- MSCI Frontier Markets ------------------------------------------------------
_FRONTIER = {
    "HR": EMERGING_EUROPE,
    "EE": EMERGING_EUROPE,
    "IS": EMERGING_EUROPE,
    "KZ": EMERGING_EUROPE,
    "LT": EMERGING_EUROPE,
    "RO": EMERGING_EUROPE,
    "RS": EMERGING_EUROPE,
    "SI": EMERGING_EUROPE,
    "BH": MIDDLE_EAST,
    "JO": MIDDLE_EAST,
    "OM": MIDDLE_EAST,
    "BJ": AFRICA,
    "BF": AFRICA,
    "GW": AFRICA,
    "CI": AFRICA,
    "KE": AFRICA,
    "MU": AFRICA,
    "MA": AFRICA,
    "NE": AFRICA,
    "NG": AFRICA,
    "SN": AFRICA,
    "TG": AFRICA,
    "TN": AFRICA,
    "BD": EMERGING_ASIA,
    "PK": EMERGING_ASIA,
    "LK": EMERGING_ASIA,
    "VN": EMERGING_ASIA,
}

# --- Offshore financial centers -------------------------------------------------
# These are not MSCI-classified markets: they show up as country-of-risk because
# holdings and corporate vehicles are domiciled there, not because of a local market.
_FINANCIAL_CENTERS = {
    "KY": CARIBBEAN,   # Cayman Islands
    "BM": CARIBBEAN,   # Bermuda
    "VG": CARIBBEAN,   # British Virgin Islands
    "BS": CARIBBEAN,   # Bahamas
    "CW": CARIBBEAN,   # Curacao
    "AN": CARIBBEAN,   # Netherlands Antilles (retired code, still used in the data)
    "AI": CARIBBEAN,   # Anguilla
    "TC": CARIBBEAN,   # Turks and Caicos
    "VI": CARIBBEAN,   # US Virgin Islands
    "JE": DEVELOPED_EUROPE,
    "GG": DEVELOPED_EUROPE,
    "IM": DEVELOPED_EUROPE,
    "GI": DEVELOPED_EUROPE,
    "MC": DEVELOPED_EUROPE,
    "LU": DEVELOPED_EUROPE,
    "LI": DEVELOPED_EUROPE,
    "LR": AFRICA,      # flag of convenience, shipping
    "MH": OTHER,       # Marshall Islands, shipping
}

# --- MSCI Standalone / unclassified ---------------------------------------------
# Category "Other", but the geographic region is still populated.
_STANDALONE = {
    "AR": LATIN_AMERICA,
    "JM": CARIBBEAN,
    "TT": CARIBBEAN,
    "PA": LATIN_AMERICA,
    "BA": EMERGING_EUROPE,
    "BG": EMERGING_EUROPE,
    "UA": EMERGING_EUROPE,
    "RU": EMERGING_EUROPE,
    "BY": EMERGING_EUROPE,
    "MT": DEVELOPED_EUROPE,
    "CY": DEVELOPED_EUROPE,
    "SK": EMERGING_EUROPE,
    "LV": EMERGING_EUROPE,
    "LB": MIDDLE_EAST,
    "PS": MIDDLE_EAST,
    "ZW": AFRICA,
    "GH": AFRICA,
    "TZ": AFRICA,
    "UG": AFRICA,
    "ZM": AFRICA,
    "BW": AFRICA,
    "NA": AFRICA,
    "MO": DEVELOPED_ASIA,
    "PR": NORTH_AMERICA,   # Puerto Rico: US banks, not an MSCI market
    "FO": DEVELOPED_EUROPE,
    "GL": DEVELOPED_EUROPE,
    "AD": DEVELOPED_EUROPE,
    "SM": DEVELOPED_EUROPE,
    "AL": EMERGING_EUROPE,
    "MK": EMERGING_EUROPE,
    "ME": EMERGING_EUROPE,
    "XK": EMERGING_EUROPE,
    "KG": EMERGING_EUROPE,
    "TJ": EMERGING_EUROPE,
    "TM": EMERGING_EUROPE,
    "BN": EMERGING_ASIA,
    "MV": EMERGING_ASIA,
    "FJ": DEVELOPED_ASIA,
    "NC": DEVELOPED_ASIA,
    "AF": EMERGING_ASIA,
    "BB": CARIBBEAN,
    "HN": LATIN_AMERICA,
    "NI": LATIN_AMERICA,
    "SV": LATIN_AMERICA,
    "SR": LATIN_AMERICA,
    "GY": LATIN_AMERICA,
    "BZ": LATIN_AMERICA,
    "CG": AFRICA,
    "MW": AFRICA,
    "MG": AFRICA,
    "SL": AFRICA,
    "GN": AFRICA,
    "GM": AFRICA,
    "SO": AFRICA,
    "SS": AFRICA,
    "ER": AFRICA,
    "DJ": AFRICA,
    "TD": AFRICA,
    "CF": AFRICA,
    "GQ": AFRICA,
    "LS": AFRICA,
    "SZ": AFRICA,
    "CV": AFRICA,
    "MR": AFRICA,
    "KH": EMERGING_ASIA,
    "MN": EMERGING_ASIA,
    "MM": EMERGING_ASIA,
    "LA": EMERGING_ASIA,
    "NP": EMERGING_ASIA,
    "PG": DEVELOPED_ASIA,
    "UY": LATIN_AMERICA,
    "CR": LATIN_AMERICA,
    "DO": CARIBBEAN,
    "EC": LATIN_AMERICA,
    "GT": LATIN_AMERICA,
    "PY": LATIN_AMERICA,
    "BO": LATIN_AMERICA,
    "VE": LATIN_AMERICA,
    "AZ": EMERGING_EUROPE,
    "GE": EMERGING_EUROPE,
    "AM": EMERGING_EUROPE,
    "UZ": EMERGING_EUROPE,
    "IQ": MIDDLE_EAST,
    "IR": MIDDLE_EAST,
    "SY": MIDDLE_EAST,
    "YE": MIDDLE_EAST,
    "AO": AFRICA,
    "CM": AFRICA,
    "CD": AFRICA,
    "ET": AFRICA,
    "GA": AFRICA,
    "ML": AFRICA,
    "MZ": AFRICA,
    "RW": AFRICA,
    "SC": AFRICA,
    "SD": AFRICA,
    "DZ": AFRICA,
    "LY": AFRICA,
}

_CLASSIFICATION: dict[str, tuple[str, str]] = {}
for _table, _category in (
    (_DEVELOPED, DEVELOPED),
    (_EMERGING, EMERGING),
    (_FRONTIER, FRONTIER),
    (_FINANCIAL_CENTERS, FINANCIAL_CENTER),
    (_STANDALONE, OTHER),
):
    for _code, _region in _table.items():
        _CLASSIFICATION[_code] = (_region, _category)

# Names pycountry does not resolve, or that are not countries at all. Mapped to an
# alpha-2 code, or to None when they must be treated as "not attributable".
_NAME_ALIASES: dict[str, str | None] = {
    "CROATIA HRVATSKA": "HR",
    "KOREA SOUTH": "KR",
    "SOUTH KOREA": "KR",
    "KOREA REPUBLIC OF": "KR",
    "KOREA NORTH": None,
    "RUSSIAN FEDERATION": "RU",
    "RUSSIA": "RU",
    "TAIWAN PROVINCE OF CHINA": "TW",
    "TAIWAN": "TW",
    "VIET NAM": "VN",
    "VIETNAM": "VN",
    "CZECH REPUBLIC": "CZ",
    "CZECHIA": "CZ",
    "SLOVAK REPUBLIC": "SK",
    "SLOVAKIA": "SK",
    "TURKIYE": "TR",
    "TURKEY": "TR",
    "IVORY COAST": "CI",
    "COTE DIVOIRE": "CI",
    "COTE D IVOIRE": "CI",
    "MACAU": "MO",
    "MACAO": "MO",
    "HONG KONG SAR CHINA": "HK",
    "NETHERLANDS ANTILLES": "AN",
    "CURACAO": "CW",
    "VIRGIN ISLANDS BRITISH": "VG",
    "BRITISH VIRGIN ISLANDS": "VG",
    "BRITISH VERGIN ISLANDS": "VG",  # typo present in the DWS export
    "VIRGIN ISLANDS U S": "VI",
    "US VIRGIN ISLANDS": "VI",
    "UNITED STATES OF AMERICA": "US",
    "USA": "US",
    "UNITED KINGDOM": "GB",
    "GREAT BRITAIN": "GB",
    "CAPE VERDE": None,
    "SWAZILAND": None,
    "BURMA": "MM",
    "MYANMAR": "MM",
    "LAO PEOPLES DEMOCRATIC REPUBLIC": "LA",
    "SYRIAN ARAB REPUBLIC": "SY",
    "IRAN ISLAMIC REPUBLIC OF": "IR",
    "TANZANIA UNITED REPUBLIC OF": "TZ",
    "CONGO DEMOCRATIC REPUBLIC OF THE": "CD",
    "MOLDOVA REPUBLIC OF": None,
    "BOSNIA AND HERZEGOVINA": "BA",
    "BOSNIA HERZEGOVINA": "BA",
    "PALESTINE STATE OF": "PS",
    "PALESTINIAN TERRITORY OCCUPIED": "PS",
    "TRINIDAD AND TOBAGO": "TT",
    "UNITED ARAB EMIRATES": "AE",
    # Non-countries that issuers use as country-of-risk
    "MULT": None,           # Vanguard: multinational issuer
    "SNAT": None,           # Vanguard: supranational
    "XE": None,             # Vanguard: euro area
    "EUROPEAN UNION": None,
    "SUPRANATIONAL": None,
    "MULTINATIONAL": None,
    "CASH": None,
    "OTHER": None,
    "UNKNOWN": None,
    "N A": None,
    "NONE": None,
}

_PUNCT = re.compile(r"[^A-Z0-9]+")

_unresolved_countries: set[str] = set()


def _normalize_name(name: str) -> str:
    return _PUNCT.sub(" ", name.upper()).strip()


def resolve_country_code(country: str | None) -> str | None:
    """Country name (in any of the variants used by issuers) -> alpha-2."""
    if not country:
        return None
    raw = country.strip()
    if not raw or raw in {"-", "--"}:
        return None

    key = _normalize_name(raw)
    if not key:
        return None
    if key in _NAME_ALIASES:
        return _NAME_ALIASES[key]
    # Some sources write the ISO code directly.
    if len(key) == 2 and key in _CLASSIFICATION:
        return key

    try:
        return pycountry.countries.lookup(raw).alpha_2
    except LookupError:
        pass
    # Last resort: "Croatia (Hrvatska)" -> "Croatia"
    stripped = re.sub(r"\s*\(.*?\)\s*", " ", raw).strip()
    if stripped and stripped != raw:
        try:
            return pycountry.countries.lookup(stripped).alpha_2
        except LookupError:
            pass
    return None


def classify(country: str | None) -> tuple[str, str, str]:
    """Return (normalized_country, region, category)."""
    code = resolve_country_code(country)
    if code is None:
        raw = (country or "").strip()
        # A value explicitly aliased to None is a deliberate "not attributable", not a
        # gap in the table: reporting it every run would be noise.
        if raw not in {"", "-", "--"} and _normalize_name(raw) not in _NAME_ALIASES:
            _unresolved_countries.add(raw)
        return raw or OTHER, OTHER, OTHER

    try:
        display = pycountry.countries.get(alpha_2=code).name
    except (AttributeError, KeyError):
        display = (country or code).strip()

    region, category = _CLASSIFICATION.get(code, (OTHER, OTHER))
    if code not in _CLASSIFICATION:
        _unresolved_countries.add(f"{display} ({code})")
    return display, region, category


def report_unresolved() -> None:
    """List the unclassified countries on stderr, so the table can be extended."""
    if _unresolved_countries:
        print(
            "[warn] countries with no MSCI classification (Region/Category = Other): "
            + ", ".join(sorted(_unresolved_countries)),
            file=sys.stderr,
        )
