"""Fallback currency for holdings whose issuer does not state one.

Vanguard's schema has no per-holding currency field at all, so without this every Vanguard
row would ship an empty `Currency`. iShares and Xtrackers do publish it and are untouched:
the table below is consulted only when the source leaves the field blank.

This is an inference, not a fact. The country attached to a holding is the issuer's country
of risk or of incorporation, which is not necessarily where the security trades, so a Hong
Kong listing of a mainland Chinese company comes out CNY here rather than HKD. Where a
country has no functioning local market for securities -- the offshore centres, the
dollarised economies -- the de facto denomination currency is used instead of the nominal
one, because nothing is actually priced in KYD or MOP.
"""

from __future__ import annotations

import sys

import msci

# Euro area, including the countries that use the euro unilaterally (Kosovo, Montenegro)
# and the microstates. Bulgaria joined on 1 January 2026.
_EURO = (
    "AD AT BE BG CY DE EE ES FI FR GR HR IE IT LT LU LV MC ME MT NL PT SI SK SM XK"
).split()

# No local market to price a security in: offshore centres whose currency is pegged to or
# replaced by the dollar, US territories, and the dollarised economies.
_DOLLAR = "US PR VI TC AI KY BM BS VG MH PA EC SV ZW CW AN".split()

_BY_COUNTRY: dict[str, str] = {code: "EUR" for code in _EURO}
_BY_COUNTRY.update({code: "USD" for code in _DOLLAR})
_BY_COUNTRY.update(
    {
        # --- Europe outside the euro ---
        "GB": "GBP",
        "JE": "GBP",  # Crown dependencies: local notes, but securities are priced in GBP
        "GG": "GBP",
        "IM": "GBP",
        "GI": "GBP",
        "CH": "CHF",
        "LI": "CHF",
        "NO": "NOK",
        "SE": "SEK",
        "DK": "DKK",
        "FO": "DKK",
        "GL": "DKK",
        "IS": "ISK",
        "PL": "PLN",
        "CZ": "CZK",
        "HU": "HUF",
        "RO": "RON",
        "RS": "RSD",
        "BA": "BAM",
        "MK": "MKD",
        "AL": "ALL",
        "UA": "UAH",
        "BY": "BYN",
        "RU": "RUB",
        "TR": "TRY",
        "GE": "GEL",
        "AM": "AMD",
        "AZ": "AZN",
        # --- Central Asia ---
        "KZ": "KZT",
        "KG": "KGS",
        "TJ": "TJS",
        "TM": "TMT",
        "UZ": "UZS",
        # --- Americas ---
        "CA": "CAD",
        "MX": "MXN",
        "BR": "BRL",
        "AR": "ARS",
        "CL": "CLP",
        "CO": "COP",
        "PE": "PEN",
        "UY": "UYU",
        "PY": "PYG",
        "BO": "BOB",
        "VE": "VES",
        "CR": "CRC",
        "GT": "GTQ",
        "HN": "HNL",
        "NI": "NIO",
        "BZ": "BZD",
        "GY": "GYD",
        "SR": "SRD",
        "DO": "DOP",
        "JM": "JMD",
        "TT": "TTD",
        "BB": "BBD",
        # --- Middle East ---
        "AE": "AED",
        "SA": "SAR",
        "QA": "QAR",
        "KW": "KWD",
        "BH": "BHD",
        "OM": "OMR",
        "JO": "JOD",
        "LB": "LBP",
        "IQ": "IQD",
        "IR": "IRR",
        "SY": "SYP",
        "YE": "YER",
        "IL": "ILS",
        "PS": "ILS",
        # --- Africa ---
        "ZA": "ZAR",
        "EG": "EGP",
        "MA": "MAD",
        "TN": "TND",
        "DZ": "DZD",
        "LY": "LYD",
        "NG": "NGN",
        "GH": "GHS",
        "KE": "KES",
        "TZ": "TZS",
        "UG": "UGX",
        "ET": "ETB",
        "ZM": "ZMW",
        "MW": "MWK",
        "MZ": "MZN",
        "BW": "BWP",
        "NA": "NAD",
        "SZ": "SZL",
        "LS": "LSL",
        "MU": "MUR",
        "SC": "SCR",
        "MG": "MGA",
        "RW": "RWF",
        "CV": "CVE",
        "MR": "MRU",
        "GM": "GMD",
        "GN": "GNF",
        "SL": "SLE",
        "LR": "LRD",
        "AO": "AOA",
        "CD": "CDF",
        "SD": "SDG",
        "SS": "SSP",
        "ER": "ERN",
        "DJ": "DJF",
        "SO": "SOS",
        # West African CFA franc
        "BJ": "XOF",
        "BF": "XOF",
        "CI": "XOF",
        "GW": "XOF",
        "ML": "XOF",
        "NE": "XOF",
        "SN": "XOF",
        "TG": "XOF",
        # Central African CFA franc
        "CM": "XAF",
        "CF": "XAF",
        "TD": "XAF",
        "CG": "XAF",
        "GA": "XAF",
        "GQ": "XAF",
        # --- Asia Pacific ---
        "JP": "JPY",
        "CN": "CNY",
        "HK": "HKD",
        "MO": "HKD",  # the pataca exists, but Macau-risk equities list in Hong Kong
        "TW": "TWD",
        "KR": "KRW",
        "IN": "INR",
        "ID": "IDR",
        "MY": "MYR",
        "PH": "PHP",
        "TH": "THB",
        "SG": "SGD",
        "VN": "VND",
        "BD": "BDT",
        "PK": "PKR",
        "LK": "LKR",
        "NP": "NPR",
        "MV": "MVR",
        "MM": "MMK",
        "KH": "KHR",
        "LA": "LAK",
        "MN": "MNT",
        "BN": "BND",
        "AF": "AFN",
        "AU": "AUD",
        "NZ": "NZD",
        "FJ": "FJD",
        "PG": "PGK",
        "NC": "XPF",
    }
)
# Not countries, but issuers use the slots as such and these do imply a currency. XE is
# the euro area and only ever turns up on euro cash lines. SNAT (supranational) and MULT
# (multinational) are deliberately absent: EU and EIB paper is issued across several
# currencies, so there is nothing to infer from them.
_PSEUDO_COUNTRY = {"XE": "EUR"}

_unmapped: set[str] = set()


def from_country(country: str | None) -> str:
    """Best-effort ISO 4217 code for a country name or alpha-2 code, "" when unknown."""
    pseudo = _PSEUDO_COUNTRY.get((country or "").strip().upper())
    if pseudo:
        return pseudo
    code = msci.resolve_country_code(country)
    if code is None:
        return ""
    currency = _BY_COUNTRY.get(code)
    if currency is None:
        _unmapped.add(code)
        return ""
    return currency


def report_unmapped() -> None:
    """List on stderr the countries with no currency, so the table can be extended."""
    if _unmapped:
        print(
            "[warn] no currency for country (Currency left empty): "
            + ", ".join(sorted(_unmapped)),
            file=sys.stderr,
        )
