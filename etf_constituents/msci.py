"""Country -> (Region, Category) according to the MSCI Market Classification.

Category: Developed | Emerging | Frontier | Financial Center | Other
Region:   North America | Latin America | Europe | Middle East & Africa |
          Asia Pacific | Other

The table is keyed by ISO 3166-1 alpha-2 code, not by name: issuers use non-ISO names
("Croatia (Hrvatska)", "Korea (South)") and resolving them to a code before
classifying avoids having to list every variant.

Note: Region is purely geographic and says nothing about how developed a market is --
that is what Category is for. The one place where the result is not the naive geographic
answer is the CIS and the Caucasus (Kazakhstan, Uzbekistan, Georgia, Armenia, ...) plus
Turkey and Cyprus: they are transcontinental or outright Asian, but MSCI groups them
under "Frontier Markets Europe & CIS" and EM EMEA, so they follow MSCI and stay in Europe.
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

# Region is geography only: the development status of a market lives in Category.
NORTH_AMERICA = "North America"
LATIN_AMERICA = "Latin America"
EUROPE = "Europe"
MIDDLE_EAST_AFRICA = "Middle East & Africa"
ASIA_PACIFIC = "Asia Pacific"

# --- MSCI Developed Markets (23) ------------------------------------------------
_DEVELOPED = {
    "CA": NORTH_AMERICA,
    "US": NORTH_AMERICA,
    "AT": EUROPE,
    "BE": EUROPE,
    "DK": EUROPE,
    "FI": EUROPE,
    "FR": EUROPE,
    "DE": EUROPE,
    "IE": EUROPE,
    "IT": EUROPE,
    "NL": EUROPE,
    "NO": EUROPE,
    "PT": EUROPE,
    "ES": EUROPE,
    "SE": EUROPE,
    "CH": EUROPE,
    "GB": EUROPE,
    "IL": MIDDLE_EAST_AFRICA,
    "AU": ASIA_PACIFIC,
    "HK": ASIA_PACIFIC,
    "JP": ASIA_PACIFIC,
    "NZ": ASIA_PACIFIC,
    "SG": ASIA_PACIFIC,
}

# --- MSCI Emerging Markets (24) -------------------------------------------------
_EMERGING = {
    "BR": LATIN_AMERICA,
    "CL": LATIN_AMERICA,
    "CO": LATIN_AMERICA,
    "MX": LATIN_AMERICA,
    "PE": LATIN_AMERICA,
    "CZ": EUROPE,
    "GR": EUROPE,
    "HU": EUROPE,
    "PL": EUROPE,
    "TR": EUROPE,
    "EG": MIDDLE_EAST_AFRICA,
    "ZA": MIDDLE_EAST_AFRICA,
    "KW": MIDDLE_EAST_AFRICA,
    "QA": MIDDLE_EAST_AFRICA,
    "SA": MIDDLE_EAST_AFRICA,
    "AE": MIDDLE_EAST_AFRICA,
    "CN": ASIA_PACIFIC,
    "IN": ASIA_PACIFIC,
    "ID": ASIA_PACIFIC,
    "KR": ASIA_PACIFIC,
    "MY": ASIA_PACIFIC,
    "PH": ASIA_PACIFIC,
    "TW": ASIA_PACIFIC,
    "TH": ASIA_PACIFIC,
}

# --- MSCI Frontier Markets ------------------------------------------------------
_FRONTIER = {
    "HR": EUROPE,
    "EE": EUROPE,
    "IS": EUROPE,
    "KZ": EUROPE,
    "LT": EUROPE,
    "RO": EUROPE,
    "RS": EUROPE,
    "SI": EUROPE,
    "BH": MIDDLE_EAST_AFRICA,
    "JO": MIDDLE_EAST_AFRICA,
    "OM": MIDDLE_EAST_AFRICA,
    "BJ": MIDDLE_EAST_AFRICA,
    "BF": MIDDLE_EAST_AFRICA,
    "GW": MIDDLE_EAST_AFRICA,
    "CI": MIDDLE_EAST_AFRICA,
    "KE": MIDDLE_EAST_AFRICA,
    "MU": MIDDLE_EAST_AFRICA,
    "MA": MIDDLE_EAST_AFRICA,
    "NE": MIDDLE_EAST_AFRICA,
    "NG": MIDDLE_EAST_AFRICA,
    "SN": MIDDLE_EAST_AFRICA,
    "TG": MIDDLE_EAST_AFRICA,
    "TN": MIDDLE_EAST_AFRICA,
    "BD": ASIA_PACIFIC,
    "PK": ASIA_PACIFIC,
    "LK": ASIA_PACIFIC,
    "VN": ASIA_PACIFIC,
}

# --- Offshore financial centers -------------------------------------------------
# These are not MSCI-classified markets: they show up as country-of-risk because
# holdings and corporate vehicles are domiciled there, not because of a local market.
# The Caribbean ones sit in Latin America, following the usual "Latin America and the
# Caribbean" grouping; Category keeps them recognisable as Financial Center.
_FINANCIAL_CENTERS = {
    "KY": LATIN_AMERICA,       # Cayman Islands
    "BM": LATIN_AMERICA,       # Bermuda
    "VG": LATIN_AMERICA,       # British Virgin Islands
    "BS": LATIN_AMERICA,       # Bahamas
    "CW": LATIN_AMERICA,       # Curacao
    "AN": LATIN_AMERICA,       # Netherlands Antilles (retired code, still used in the data)
    "AI": LATIN_AMERICA,       # Anguilla
    "TC": LATIN_AMERICA,       # Turks and Caicos
    "VI": LATIN_AMERICA,       # US Virgin Islands
    "JE": EUROPE,
    "GG": EUROPE,
    "IM": EUROPE,
    "GI": EUROPE,
    "MC": EUROPE,
    "LU": EUROPE,
    "LI": EUROPE,
    "LR": MIDDLE_EAST_AFRICA,  # flag of convenience, shipping
    "MH": ASIA_PACIFIC,        # Marshall Islands, shipping
}

# --- MSCI Standalone / unclassified ---------------------------------------------
# Category "Other", but the geographic region is still populated.
_STANDALONE = {
    "AR": LATIN_AMERICA,
    "JM": LATIN_AMERICA,
    "TT": LATIN_AMERICA,
    "PA": LATIN_AMERICA,
    "BA": EUROPE,
    "BG": EUROPE,
    "UA": EUROPE,
    "RU": EUROPE,
    "BY": EUROPE,
    "MT": EUROPE,
    "CY": EUROPE,
    "SK": EUROPE,
    "LV": EUROPE,
    "LB": MIDDLE_EAST_AFRICA,
    "PS": MIDDLE_EAST_AFRICA,
    "ZW": MIDDLE_EAST_AFRICA,
    "GH": MIDDLE_EAST_AFRICA,
    "TZ": MIDDLE_EAST_AFRICA,
    "UG": MIDDLE_EAST_AFRICA,
    "ZM": MIDDLE_EAST_AFRICA,
    "BW": MIDDLE_EAST_AFRICA,
    "NA": MIDDLE_EAST_AFRICA,
    "MO": ASIA_PACIFIC,
    "PR": NORTH_AMERICA,   # Puerto Rico: US banks, not an MSCI market
    "FO": EUROPE,
    "GL": EUROPE,
    "AD": EUROPE,
    "SM": EUROPE,
    "AL": EUROPE,
    "MK": EUROPE,
    "ME": EUROPE,
    "XK": EUROPE,
    "KG": EUROPE,
    "TJ": EUROPE,
    "TM": EUROPE,
    "BN": ASIA_PACIFIC,
    "MV": ASIA_PACIFIC,
    "FJ": ASIA_PACIFIC,
    "NC": ASIA_PACIFIC,
    "AF": ASIA_PACIFIC,
    "BB": LATIN_AMERICA,
    "HN": LATIN_AMERICA,
    "NI": LATIN_AMERICA,
    "SV": LATIN_AMERICA,
    "SR": LATIN_AMERICA,
    "GY": LATIN_AMERICA,
    "BZ": LATIN_AMERICA,
    "CG": MIDDLE_EAST_AFRICA,
    "MW": MIDDLE_EAST_AFRICA,
    "MG": MIDDLE_EAST_AFRICA,
    "SL": MIDDLE_EAST_AFRICA,
    "GN": MIDDLE_EAST_AFRICA,
    "GM": MIDDLE_EAST_AFRICA,
    "SO": MIDDLE_EAST_AFRICA,
    "SS": MIDDLE_EAST_AFRICA,
    "ER": MIDDLE_EAST_AFRICA,
    "DJ": MIDDLE_EAST_AFRICA,
    "TD": MIDDLE_EAST_AFRICA,
    "CF": MIDDLE_EAST_AFRICA,
    "GQ": MIDDLE_EAST_AFRICA,
    "LS": MIDDLE_EAST_AFRICA,
    "SZ": MIDDLE_EAST_AFRICA,
    "CV": MIDDLE_EAST_AFRICA,
    "MR": MIDDLE_EAST_AFRICA,
    "KH": ASIA_PACIFIC,
    "MN": ASIA_PACIFIC,
    "MM": ASIA_PACIFIC,
    "LA": ASIA_PACIFIC,
    "NP": ASIA_PACIFIC,
    "PG": ASIA_PACIFIC,
    "UY": LATIN_AMERICA,
    "CR": LATIN_AMERICA,
    "DO": LATIN_AMERICA,
    "EC": LATIN_AMERICA,
    "GT": LATIN_AMERICA,
    "PY": LATIN_AMERICA,
    "BO": LATIN_AMERICA,
    "VE": LATIN_AMERICA,
    "AZ": EUROPE,
    "GE": EUROPE,
    "AM": EUROPE,
    "UZ": EUROPE,
    "IQ": MIDDLE_EAST_AFRICA,
    "IR": MIDDLE_EAST_AFRICA,
    "SY": MIDDLE_EAST_AFRICA,
    "YE": MIDDLE_EAST_AFRICA,
    "AO": MIDDLE_EAST_AFRICA,
    "CM": MIDDLE_EAST_AFRICA,
    "CD": MIDDLE_EAST_AFRICA,
    "ET": MIDDLE_EAST_AFRICA,
    "GA": MIDDLE_EAST_AFRICA,
    "ML": MIDDLE_EAST_AFRICA,
    "MZ": MIDDLE_EAST_AFRICA,
    "RW": MIDDLE_EAST_AFRICA,
    "SC": MIDDLE_EAST_AFRICA,
    "SD": MIDDLE_EAST_AFRICA,
    "DZ": MIDDLE_EAST_AFRICA,
    "LY": MIDDLE_EAST_AFRICA,
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
    # SPDR / State Street spellings
    "UAE": "AE",
    "KOREA": "KR",
    "REPUBLIC OF KOREA": "KR",
    "C I GUERNSEY": "GG",
    "C I JERSEY": "JE",
    "BRITISH VIRGIN": "VG",
    "VIRGIN ISLANDS": "VG",
    "DOMINICAN REPB": "DO",
    "TRINIDAD TOBAGO": "TT",
    "BELGIUM LUXEMBOURG": "BE",  # index label; the securities behind it are Belgian
    "SUPRA NATIONAL": None,
    "XU": None,                  # pseudo-code for the Eurobond (XS) market
    "EUROPE": None,
    "UNASSIGNED": None,
    # Amundi spellings
    "CAYMAN ISLAND": "KY",
    "SUPRANATIONALS": None,
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
