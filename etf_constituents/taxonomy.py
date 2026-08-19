"""Unification of the Sector and Class taxonomies across issuers.

iShares uses *two* different sector vocabularies depending on the fund asset class:
a GICS-like one for equity ("Information Technology", "Consumer Discretionary")
and an ICE/Bloomberg-like one for fixed income ("Banking", "Consumer Non-Cyclical",
"Basic Industry"). Xtrackers uses GICS-like names but leaves "unknown" on bonds.
Both are mapped back to the 11 GICS sectors plus three service buckets.
"""

from __future__ import annotations

import re
import sys

# --- Canonical sectors ----------------------------------------------------------
COMMUNICATION_SERVICES = "Communication Services"
CONSUMER_DISCRETIONARY = "Consumer Discretionary"
CONSUMER_STAPLES = "Consumer Staples"
ENERGY = "Energy"
FINANCIALS = "Financials"
HEALTH_CARE = "Health Care"
INDUSTRIALS = "Industrials"
INFORMATION_TECHNOLOGY = "Information Technology"
MATERIALS = "Materials"
REAL_ESTATE = "Real Estate"
UTILITIES = "Utilities"
GOVERNMENT = "Government"
CASH_DERIVATIVES = "Cash & Derivatives"
OTHER = "Other"

# --- Canonical classes ----------------------------------------------------------
EQUITY = "Equity"
FIXED_INCOME = "Fixed Income"
CASH = "Cash"
DERIVATIVE = "Derivative"
FUND = "Fund"
COMMODITY = "Commodity"

_SECTOR_ALIASES: dict[str, str] = {
    # Canonical GICS (iShares equity, Xtrackers)
    "communication services": COMMUNICATION_SERVICES,
    "communication": COMMUNICATION_SERVICES,
    "communications": COMMUNICATION_SERVICES,
    "telecommunication services": COMMUNICATION_SERVICES,
    "telecommunications": COMMUNICATION_SERVICES,
    "media": COMMUNICATION_SERVICES,
    "media entertainment": COMMUNICATION_SERVICES,
    "consumer discretionary": CONSUMER_DISCRETIONARY,
    "consumer cyclical": CONSUMER_DISCRETIONARY,
    "consumer cyclicals": CONSUMER_DISCRETIONARY,
    "consumer services": CONSUMER_DISCRETIONARY,
    "retail": CONSUMER_DISCRETIONARY,
    "automotive": CONSUMER_DISCRETIONARY,
    "consumer staples": CONSUMER_STAPLES,
    "consumer non cyclical": CONSUMER_STAPLES,
    "consumer non cyclicals": CONSUMER_STAPLES,
    "consumer goods": CONSUMER_STAPLES,
    "food beverage tobacco": CONSUMER_STAPLES,
    "energy": ENERGY,
    "oil gas": ENERGY,
    "oil gas consumable fuels": ENERGY,
    "independent energy": ENERGY,
    "integrated energy": ENERGY,
    "oil field services": ENERGY,
    "midstream": ENERGY,
    "refining": ENERGY,
    "financials": FINANCIALS,
    "financial": FINANCIALS,
    "financial services": FINANCIALS,
    "financial other": FINANCIALS,
    "banking": FINANCIALS,
    "banks": FINANCIALS,
    "insurance": FINANCIALS,
    "life insurance": FINANCIALS,
    "property casualty": FINANCIALS,
    "brokerage asset managers exchanges": FINANCIALS,
    "brokerage": FINANCIALS,
    "finance companies": FINANCIALS,
    "diversified financials": FINANCIALS,
    "health care": HEALTH_CARE,
    "healthcare": HEALTH_CARE,
    "pharmaceuticals": HEALTH_CARE,
    "health care pharmaceuticals": HEALTH_CARE,
    "industrials": INDUSTRIALS,
    "industrial": INDUSTRIALS,
    "industrial other": INDUSTRIALS,
    "capital goods": INDUSTRIALS,
    "transportation": INDUSTRIALS,
    "aerospace defense": INDUSTRIALS,
    "airlines": INDUSTRIALS,
    "railroads": INDUSTRIALS,
    "information technology": INFORMATION_TECHNOLOGY,
    "technology": INFORMATION_TECHNOLOGY,
    "software services": INFORMATION_TECHNOLOGY,
    "electronics": INFORMATION_TECHNOLOGY,
    "semiconductors": INFORMATION_TECHNOLOGY,
    "materials": MATERIALS,
    "basic industry": MATERIALS,
    "basic materials": MATERIALS,
    "chemicals": MATERIALS,
    "metals mining": MATERIALS,
    "paper": MATERIALS,
    "building materials": MATERIALS,
    "real estate": REAL_ESTATE,
    "reits": REAL_ESTATE,
    "reit": REAL_ESTATE,
    "utilities": UTILITIES,
    "utility": UTILITIES,
    "utility other": UTILITIES,
    "electric": UTILITIES,
    "natural gas": UTILITIES,
    "water": UTILITIES,
    # Government / supranational (fixed income funds)
    "government": GOVERNMENT,
    "governments": GOVERNMENT,
    "government related": GOVERNMENT,
    "treasury": GOVERNMENT,
    "treasuries": GOVERNMENT,
    "sovereign": GOVERNMENT,
    "quasi sovereign": GOVERNMENT,
    "agency": GOVERNMENT,
    "agencies": GOVERNMENT,
    "supranational": GOVERNMENT,
    "supranationals": GOVERNMENT,
    "local authority": GOVERNMENT,
    "local government": GOVERNMENT,
    "municipal": GOVERNMENT,
    "municipals": GOVERNMENT,
    "sovereigns": GOVERNMENT,
    "foreign agencies": GOVERNMENT,
    "foreign sovereign": GOVERNMENT,
    "foreign local government": GOVERNMENT,
    # Cash and derivatives
    "cash and or derivatives": CASH_DERIVATIVES,
    "cash and derivatives": CASH_DERIVATIVES,
    "cash": CASH_DERIVATIVES,
    "cash equivalents": CASH_DERIVATIVES,
    "derivatives": CASH_DERIVATIVES,
    "money market": CASH_DERIVATIVES,
    "futures": CASH_DERIVATIVES,
    "cash collateral and margins": CASH_DERIVATIVES,
    # Securitized: no GICS counterpart
    "securitized": OTHER,
    "asset backed": OTHER,
    "covered": OTHER,
    "covered bonds": OTHER,
    "cmbs": OTHER,
    "mbs": OTHER,
    "abs": OTHER,
    "collateralized": OTHER,
    "funds": OTHER,
    "fund": OTHER,
    "unknown": OTHER,
    "other": OTHER,
    "unclassified": OTHER,
    "unclassifiable": OTHER,
    "n a": OTHER,
    "": OTHER,
    # ICB industries/supersectors (SPDR: the UK, European and real estate funds label
    # the sector column with ICB names instead of GICS ones)
    "aerospace and defense": INDUSTRIALS,
    "industrial engineering": INDUSTRIALS,
    "industrial support services": INDUSTRIALS,
    "industrial transportation": INDUSTRIALS,
    "general industrials": INDUSTRIALS,
    "construction and materials": INDUSTRIALS,
    "electronic and electrical equipment": INDUSTRIALS,
    "investment banking and brokerage services": FINANCIALS,
    "non life insurance": FINANCIALS,
    "finance and credit services": FINANCIALS,
    "closed end investments": FINANCIALS,
    "real estate investment trusts": REAL_ESTATE,
    "real estate investment and services": REAL_ESTATE,
    "real estate holding and development": REAL_ESTATE,
    "reoc": REAL_ESTATE,  # real estate operating company
    "industrial reit": REAL_ESTATE,
    "office reit": REAL_ESTATE,
    "data center reit": REAL_ESTATE,
    "self storage": REAL_ESTATE,
    "residential": REAL_ESTATE,
    "software and computer services": INFORMATION_TECHNOLOGY,
    "technology hardware and equipment": INFORMATION_TECHNOLOGY,
    "telecommunications equipment": INFORMATION_TECHNOLOGY,
    "telecommunications service providers": COMMUNICATION_SERVICES,
    "retailers": CONSUMER_DISCRETIONARY,
    "travel and leisure": CONSUMER_DISCRETIONARY,
    "hotels": CONSUMER_DISCRETIONARY,
    "leisure goods": CONSUMER_DISCRETIONARY,
    "personal goods": CONSUMER_DISCRETIONARY,
    "automobiles and parts": CONSUMER_DISCRETIONARY,
    "household goods and home construction": CONSUMER_DISCRETIONARY,
    "food producers": CONSUMER_STAPLES,
    "beverages": CONSUMER_STAPLES,
    "tobacco": CONSUMER_STAPLES,
    "personal care drug and grocery stores": CONSUMER_STAPLES,
    "pharmaceuticals and biotechnology": HEALTH_CARE,
    "medical equipment and services": HEALTH_CARE,
    "health care providers": HEALTH_CARE,
    "industrial metals and mining": MATERIALS,
    "precious metals and mining": MATERIALS,
    "industrial materials": MATERIALS,
    "oil gas and coal": ENERGY,
    "alternative energy": ENERGY,
    "electricity": UTILITIES,
    "gas water and multi utilities": UTILITIES,
    "unassigned": OTHER,
    "diversified": OTHER,
}

_CLASS_ALIASES: dict[str, str] = {
    "equity": EQUITY,
    "equities": EQUITY,
    "stock": EQUITY,
    "common stock": EQUITY,
    "preferred stock": EQUITY,
    "equity linked": EQUITY,
    "fixed income": FIXED_INCOME,
    "bond": FIXED_INCOME,
    "bonds": FIXED_INCOME,
    "debt": FIXED_INCOME,
    "credit": FIXED_INCOME,
    "cash": CASH,
    "money market": CASH,
    "cash collateral and margins": CASH,
    "cash collateral": CASH,
    "deposit": CASH,
    "futures": DERIVATIVE,
    "future": DERIVATIVE,
    "fx": DERIVATIVE,
    "forward": DERIVATIVE,
    "forwards": DERIVATIVE,
    "swap": DERIVATIVE,
    "swaps": DERIVATIVE,
    "option": DERIVATIVE,
    "options": DERIVATIVE,
    "derivative": DERIVATIVE,
    "derivatives": DERIVATIVE,
    "fund": FUND,
    "funds": FUND,
    "etf": FUND,
    "etfs": FUND,
    "mutual fund": FUND,
    "investment companies": FUND,
    "commodity": COMMODITY,
    "commodities": COMMODITY,
    "precious metals": COMMODITY,
    "other": OTHER,
    "unknown": OTHER,
    "": OTHER,
}

_PUNCT = re.compile(r"[^a-z0-9]+")

_unknown_sectors: set[str] = set()
_unknown_classes: set[str] = set()


def _key(value: str | None) -> str:
    return _PUNCT.sub(" ", (value or "").lower()).strip()


def normalize_sector(raw: str | None) -> str:
    key = _key(raw)
    if key in _SECTOR_ALIASES:
        return _SECTOR_ALIASES[key]
    if raw and raw.strip():
        _unknown_sectors.add(raw.strip())
    return OTHER


def normalize_class(raw: str | None) -> str:
    key = _key(raw)
    if key in _CLASS_ALIASES:
        return _CLASS_ALIASES[key]
    if raw and raw.strip():
        _unknown_classes.add(raw.strip())
    return OTHER


def report_unknown() -> None:
    """List the unmapped raw values on stderr, so the tables get extended."""
    if _unknown_sectors:
        print(
            "[warn] unmapped sectors (-> Other): " + ", ".join(sorted(_unknown_sectors)),
            file=sys.stderr,
        )
    if _unknown_classes:
        print(
            "[warn] unmapped asset classes (-> Other): " + ", ".join(sorted(_unknown_classes)),
            file=sys.stderr,
        )
