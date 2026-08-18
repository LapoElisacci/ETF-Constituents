"""Download of constituents from the official documents of the supported issuers.

Issuers: iShares (BlackRock), Xtrackers (DWS) and Vanguard.

Every provider exposes `fetch(isin)` and returns a `Fund` whose weights are already
expressed in percentage points, leaving sector/asset class/country in the raw issuer
form: normalization happens downstream in `taxonomy` and `msci`.
"""

from __future__ import annotations

import csv
import io
import logging
import re
from dataclasses import dataclass, field

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

import taxonomy

log = logging.getLogger(__name__)

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
)
TIMEOUT = (10, 120)  # (connect, read): full exports can be slow

ISIN_RE = re.compile(r"^[A-Z]{2}[A-Z0-9]{9}[0-9]$")


class ProviderError(RuntimeError):
    """Recoverable error while downloading/parsing the constituents of a fund."""


@dataclass
class Holding:
    """A constituent, with fields still in the issuer nomenclature."""

    isin: str = ""
    ticker: str = ""
    name: str = ""
    sector_raw: str = ""
    asset_class_raw: str = ""
    country_raw: str = ""
    currency: str = ""
    weight: float = 0.0  # percentage points (5.58 = 5.58%)
    exchange: str = ""


@dataclass
class Fund:
    isin: str
    name: str
    issuer: str
    as_of: str = ""
    holdings: list[Holding] = field(default_factory=list)


def build_session() -> requests.Session:
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT, "Accept-Encoding": "gzip, deflate"})
    # 500 is not in the forcelist: DWS uses it for "unknown ISIN", retrying it
    # does not help and slows down issuer detection.
    retry = Retry(
        total=3,
        backoff_factor=0.5,
        status_forcelist=(429, 502, 503, 504),
        allowed_methods=frozenset({"GET", "POST"}),
    )
    adapter = HTTPAdapter(max_retries=retry, pool_maxsize=16)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


def is_valid_isin(value: str | None) -> bool:
    return bool(value and ISIN_RE.match(value.strip().upper()))


# ---------------------------------------------------------------------------
# iShares / BlackRock
# ---------------------------------------------------------------------------


class IsharesProvider:
    name = "iShares"

    SEARCH_URL = "https://www.ishares.com/varnish-api/core-search/search/products"
    DATA_URL = (
        "https://www.ishares.com/varnish-api/uk-retail01-product-data"
        "/product-data/api/v2/get-product-data"
    )
    # (targetSite, locale): the first one exposing a fund with the requested ISIN wins.
    SITES = (("ishares-uk", "en_GB"), ("us-ishares", "en_US"))
    MAX_CANDIDATES = 5

    def __init__(self, session: requests.Session):
        self.session = session

    def _product_data(self, portfolio_id: str, site: str, locale: str, component: str) -> dict:
        params = {
            "appType": "PRODUCT_PAGE",
            "appSubType": "ISHARES",
            "targetSite": site,
            "locale": locale,
            "userType": "individual",
            "excludeContent": "true",
            "includeConfig": "true",
            "component": component,
            "portfolioId": portfolio_id,
        }
        response = self.session.get(
            self.DATA_URL,
            params=params,
            headers={"Accept": "application/json", "x-application-id": "pp-ui-csr"},
            timeout=TIMEOUT,
        )
        response.raise_for_status()
        return response.json()

    def _search(self, isin: str, site: str, locale: str) -> list[dict]:
        response = self.session.get(
            self.SEARCH_URL,
            params={"site": site, "locale": locale, "query": isin},
            headers={"Accept": "application/json"},
            timeout=TIMEOUT,
        )
        if response.status_code != 200:
            return []
        return response.json().get("results") or []

    def resolve(self, isin: str) -> tuple[str, str, str, str] | None:
        """ISIN -> (portfolioId, fundName, targetSite, locale), or None.

        The search is fuzzy (it returns results even for an unknown ISIN), so every
        candidate must be confirmed by reading the ISIN from `keyFundFacts`.
        """
        isin = isin.strip().upper()
        for site, locale in self.SITES:
            try:
                results = self._search(isin, site, locale)
            except requests.RequestException as exc:
                log.debug("iShares search failed on %s: %s", site, exc)
                continue

            seen: set[str] = set()
            candidates: list[dict] = []
            for item in results:
                pid = str(item.get("portfolioId") or "")
                if pid and pid not in seen:
                    seen.add(pid)
                    candidates.append(item)

            for item in candidates[: self.MAX_CANDIDATES]:
                pid = str(item["portfolioId"])
                try:
                    facts = self._product_data(pid, site, locale, "keyFundFacts")
                except (requests.RequestException, ValueError) as exc:
                    log.debug("keyFundFacts failed for %s: %s", pid, exc)
                    continue
                if _key_fund_fact_isin(facts) == isin:
                    fund_name = facts.get("fundName") or item.get("fundName") or isin
                    return pid, fund_name, site, locale
        return None

    def fetch(self, isin: str) -> Fund:
        resolved = self.resolve(isin)
        if resolved is None:
            raise ProviderError(f"{isin} does not appear to be an iShares ETF")
        portfolio_id, fund_name, site, locale = resolved

        try:
            payload = self._product_data(portfolio_id, site, locale, "holdings")
        except (requests.RequestException, ValueError) as exc:
            raise ProviderError(f"iShares constituents download failed for {isin}: {exc}") from exc

        try:
            points = payload["componentsByNameMap"]["holdings"]["containersByNameMap"]["all"][
                "dataPointsByNameMap"
            ]
        except (KeyError, TypeError) as exc:
            raise ProviderError(f"unexpected holdings structure for {isin}") from exc

        def column(field_name: str, *, numeric: bool = False) -> list:
            entry = points.get(field_name) or {}
            # `formattedValue` is rounded to 2 decimals: on funds with thousands of
            # positions the accumulated error is worth whole percentage points (on IEAC
            # 101.79 against 99.9998). For numbers, `value` is the field to read.
            keys = ("value", "formattedValue") if numeric else ("formattedValue", "value")
            for key in keys:
                values = entry.get(key)
                if isinstance(values, list):
                    return values
            return []

        isins = column("isin")
        if not isins:
            raise ProviderError(f"no constituent returned for {isin}")

        tickers = column("ticker")
        names = column("issueName")
        sectors = column("sectorName")
        classes = column("assetClass")
        countries = column("countryOfRisk")
        currencies = column("marketCurrencyCode")
        weights = column("holdingPercent", numeric=True)
        exchanges = column("exchange")

        def at(values: list, index: int) -> str:
            if index < len(values):
                value = values[index]
                return "" if value is None else str(value).strip()
            return ""

        holdings = []
        for i in range(len(isins)):
            holdings.append(
                Holding(
                    isin=at(isins, i).upper(),
                    ticker=at(tickers, i),
                    name=at(names, i),
                    sector_raw=at(sectors, i),
                    asset_class_raw=at(classes, i),
                    country_raw=at(countries, i),
                    currency=at(currencies, i),
                    weight=_to_float(at(weights, i)),
                    exchange=at(exchanges, i),
                )
            )

        as_of = ""
        as_of_entry = points.get("asOfDate") or {}
        if isinstance(as_of_entry.get("formattedValue"), str):
            as_of = as_of_entry["formattedValue"]

        return Fund(isin=isin, name=fund_name, issuer=self.name, as_of=as_of, holdings=holdings)


def _key_fund_fact_isin(payload: dict) -> str:
    try:
        containers = payload["componentsByNameMap"]["keyFundFacts"]["containersByNameMap"]
    except (KeyError, TypeError):
        return ""
    for container in containers.values():
        entry = (container.get("dataPointsByNameMap") or {}).get("isin") or {}
        value = entry.get("value") or entry.get("formattedValue")
        if isinstance(value, str) and value.strip():
            return value.strip().upper()
    return ""


# ---------------------------------------------------------------------------
# Xtrackers / DWS
# ---------------------------------------------------------------------------


class XtrackersProvider:
    name = "Xtrackers"

    EXPORT_URL = "https://etf.dws.com/etfdata/export/GBR/ENG/csv/product/constituent/{isin}/"
    PRODUCT_URL = "https://etf.dws.com/en-gb/{isin}/"
    # Acronyms that must not go through .title() when rebuilding the name from the slug.
    _ACRONYMS = frozenset(
        """msci ucits etf esg sri pab usd eur gbp jpy chf sek nok aud cad em imi ac ii iii
        iv ftse stoxx dax csi jpx nikkei sdg emu us uk eu esm reit reits ai it ihs iboxx
        tips hy ig nr trn dr esgl acwi spdr sp gs cnh rmb kospi asx tsx swap ucit""".split()
    )
    EXPECTED_HEADER = "ShareClass ISIN"
    # The CSV has no asset class column: it has to be inferred (see _infer_class).
    _CASH_MARKERS = re.compile(
        r"\b(cash|deposit|repo|t[- ]?bill|treasury bill|money market|liquidity)\b", re.I
    )
    # DWS uses pseudo-ISINs for non-security positions: "_CURRENCYUSD" for currency,
    # "___ADI2TZ8S1" for index futures.
    _CURRENCY_PREFIX = "_CURRENCY"

    def __init__(self, session: requests.Session):
        self.session = session

    def _download(self, isin: str) -> str | None:
        try:
            response = self.session.get(
                self.EXPORT_URL.format(isin=isin.strip().upper()),
                headers={"Accept": "text/csv,*/*"},
                timeout=TIMEOUT,
            )
        except requests.RequestException as exc:
            log.debug("DWS download failed for %s: %s", isin, exc)
            return None
        # Unknown ISIN -> 500 with an HTML error page.
        if response.status_code != 200:
            return None
        if "csv" not in (response.headers.get("Content-Type") or "").lower():
            return None
        text = response.content.decode("utf-8-sig", errors="replace")
        if not text.lstrip().startswith(self.EXPECTED_HEADER):
            return None
        return text

    def resolve(self, isin: str) -> str | None:
        return self._download(isin)

    def resolve_name(self, isin: str) -> str:
        """Fund name, missing from the CSV export.

        The product page redirects to a slug that contains the name
        (`/en-gb/LU0397221945-portfolio-ucits-etf-1c/`), so reading the final URL is
        enough, instead of downloading and parsing the page.
        """
        try:
            response = self.session.get(
                self.PRODUCT_URL.format(isin=isin.strip().upper()), timeout=TIMEOUT
            )
        except requests.RequestException:
            return ""
        match = re.search(rf"/{re.escape(isin.strip().upper())}-([^/?#]+)", response.url)
        if not match:
            return ""
        words = match.group(1).replace("-", " ").split()
        pretty = " ".join(
            # "1c"/"1d" are share class codes; the rest are acronyms or normal words.
            w.upper() if re.fullmatch(r"\d+[a-z]", w) or w in self._ACRONYMS else w.title()
            for w in words
        )
        return f"Xtrackers {pretty}".strip()

    def fetch(self, isin: str, payload: str | None = None) -> Fund:
        text = payload if payload is not None else self._download(isin)
        if text is None:
            raise ProviderError(f"{isin} does not appear to be an Xtrackers ETF")

        rows = list(csv.DictReader(io.StringIO(text), delimiter=";"))
        default_class = self._fund_default_class(rows)

        holdings = []
        for row in rows:
            name = (row.get("Constituent Name") or "").strip()
            if not name:
                continue
            industry = (row.get("Constituent Industry Classification Name") or "").strip()
            exchange = (row.get("Constituent Main Exchange Name") or "").strip()
            holdings.append(
                Holding(
                    isin=(row.get("Constituent ISIN") or "").strip().upper(),
                    ticker="",  # not exposed by the DWS export
                    name=name,
                    sector_raw=industry,
                    asset_class_raw=self._infer_class(
                        (row.get("Constituent ISIN") or "").strip(),
                        name,
                        industry,
                        default_class,
                    ),
                    country_raw=(row.get("Constituent Country") or "").strip(),
                    currency=(row.get("Constituent Currency ISO Code") or "").strip(),
                    # The DWS export expresses weights as a fraction (0.0558 = 5.58%).
                    weight=_to_float(row.get("Constituent Weighting")) * 100.0,
                    exchange=exchange,
                )
            )

        if not holdings:
            raise ProviderError(f"no constituent returned for {isin}")

        return Fund(isin=isin, name="", issuer=self.name, as_of="", holdings=holdings)

    @staticmethod
    def _fund_default_class(rows: list[dict]) -> str:
        """Prevailing asset class of the fund, inferred from sector coverage.

        DWS populates the sector classification on equity only: on an equity ETF it
        stays "unknown" on a handful of rows, on a fixed income one on almost all of
        them. The share of classified rows therefore tells the two cases apart, and
        drives the leftover rows that do not classify themselves.
        """
        classified = sum(
            1
            for r in rows
            if (r.get("Constituent Industry Classification Name") or "").strip().lower()
            not in ("", "unknown")
        )
        return "Equity" if rows and classified / len(rows) >= 0.5 else "Fixed Income"

    def _infer_class(self, isin: str, name: str, industry: str, default_class: str) -> str:
        """The DWS export has no asset class column: it has to be inferred.

        The exchange is not usable as a signal, because DWS omits it even on listed
        securities (Roche, GSK, AIA). Any reclassification to `Fund` happens upstream,
        when the ISIN resolves as an ETF of a supported issuer.
        """
        if isin.startswith(self._CURRENCY_PREFIX):
            return "Cash"
        if isin and not is_valid_isin(isin):
            return "Derivative"  # pseudo-code: index future
        sector = taxonomy.normalize_sector(industry)
        if sector == taxonomy.CASH_DERIVATIVES or self._CASH_MARKERS.search(name):
            return "Cash"
        # In a fixed income fund the sector, when present, describes the issuer of the
        # security and not the asset class: the fund prevalence takes precedence.
        if default_class != "Equity":
            return default_class
        return "Equity"


# ---------------------------------------------------------------------------
# Vanguard
# ---------------------------------------------------------------------------


class VanguardProvider:
    """Constituents from the GraphQL endpoint behind the Vanguard product pages.

    The product page itself renders only the top ten holdings; the full list comes from
    the same `gpx/graphql` endpoint the page calls, paginated by an opaque cursor.
    """

    name = "Vanguard"

    GRAPHQL_URL = "https://www.vanguard.co.uk/gpx/graphql"
    # Sent by the site on every call; without it the endpoint replies
    # "x-consumer-id must be provided".
    CONSUMER_ID = "uk2"
    PAGE_LIMIT = 1500
    # The largest fund seen is the Global Aggregate Bond ETF at ~13600 holdings, so ten
    # pages; the cap only exists so a broken cursor cannot loop forever.
    MAX_PAGES = 40

    _PROFILE_QUERY = """
        query FundProfile($isins: [String!]) {
          funds(isins: $isins) {
            profile { portId fundFullName fundCurrency }
          }
        }
    """

    # `securityTypes` is deliberately left unset: the site filters it down to equity and
    # bond codes, which drops cash, FX and futures and leaves the weights at ~99.2%.
    # `holdings` and not `delayeredHoldings`: the latter is the issuer's own look-through
    # of a fund of funds, and nested funds are expanded upstream instead.
    # `limit` is inlined rather than passed as a variable: the schema does not declare
    # an `Int` type, so `$limit: Int` fails validation.
    _HOLDINGS_QUERY = """
        query FundsHoldingsQuery($portIds: [String!], $lastItemKey: String) {
          borHoldings(portIds: $portIds) {
            holdings(limit: %d, lastItemKey: $lastItemKey) {
              items {
                issuerName
                securityLongDescription
                isin
                ticker
                securityType
                gicsSectorDescription
                icbIndustryDescription
                marketValuePercentage
                bloombergIsoCountry
                effectiveDate
              }
              lastItemKey
            }
          }
        }
    """ % PAGE_LIMIT

    # Vanguard codes the instrument type rather than the asset class, but the prefix
    # carries it. The values are the raw words `taxonomy.normalize_class` already knows.
    _FUND_TYPES = frozenset({"EQ.ETF", "MF.MF"})
    _CLASS_BY_TYPE = {"CRNY": "Cash"}
    _CLASS_BY_PREFIX = (
        ("EQ.", "Equity"),
        ("FI.", "Fixed Income"),
        ("MM.", "Cash"),        # money market: T-bills, CDs, commercial paper
        ("CT.", "Derivative"),  # FX forwards, spots, portfolio swaps
        ("DE.", "Derivative"),  # index and commodity futures
    )

    def __init__(self, session: requests.Session):
        self.session = session

    def _graphql(self, query: str, variables: dict) -> dict:
        response = self.session.post(
            self.GRAPHQL_URL,
            json={"query": query, "variables": variables},
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
                "X-Consumer-ID": self.CONSUMER_ID,
            },
            timeout=TIMEOUT,
        )
        response.raise_for_status()
        payload = response.json()
        if payload.get("errors"):
            message = str(payload["errors"][0].get("message", ""))
            raise ProviderError(f"Vanguard GraphQL error: {message[:200]}")
        return payload.get("data") or {}

    def resolve(self, isin: str) -> dict | None:
        """ISIN -> fund profile, or None when it is not a Vanguard fund.

        One request, and an unknown ISIN comes back as an empty list, so this doubles as
        a cheap issuer probe.
        """
        try:
            data = self._graphql(self._PROFILE_QUERY, {"isins": [isin.strip().upper()]})
        except (requests.RequestException, ValueError, ProviderError) as exc:
            log.debug("Vanguard profile lookup failed for %s: %s", isin, exc)
            return None
        funds = data.get("funds") or []
        profile = (funds[0] or {}).get("profile") if funds else None
        return profile if profile and profile.get("portId") else None

    def fetch(self, isin: str, profile: dict | None = None) -> Fund:
        profile = profile if profile is not None else self.resolve(isin)
        if profile is None:
            raise ProviderError(f"{isin} does not appear to be a Vanguard ETF")
        port_id = str(profile["portId"])

        items: list[dict] = []
        last_item_key = None
        for _ in range(self.MAX_PAGES):
            try:
                data = self._graphql(
                    self._HOLDINGS_QUERY,
                    {"portIds": [port_id], "lastItemKey": last_item_key},
                )
            except (requests.RequestException, ValueError) as exc:
                raise ProviderError(
                    f"Vanguard constituents download failed for {isin}: {exc}"
                ) from exc
            containers = data.get("borHoldings") or []
            page = (containers[0] or {}).get("holdings") if containers else None
            if not page:
                break
            items.extend(page.get("items") or [])
            last_item_key = page.get("lastItemKey")
            if not last_item_key:
                break
        else:
            log.warning("Vanguard: stopped %s after %d pages", isin, self.MAX_PAGES)

        if not items:
            raise ProviderError(f"no constituent returned for {isin}")

        holdings = []
        for item in items:
            holdings.append(
                Holding(
                    isin=(item.get("isin") or "").strip().upper(),
                    ticker=(item.get("ticker") or "").strip(),
                    # Cash and FX rows carry only the long description.
                    name=(item.get("securityLongDescription") or item.get("issuerName") or "").strip(),
                    sector_raw=(
                        item.get("gicsSectorDescription") or item.get("icbIndustryDescription") or ""
                    ).strip(),
                    asset_class_raw=self._infer_class(item.get("securityType")),
                    country_raw=(item.get("bloombergIsoCountry") or "").strip(),
                    currency="",  # no per-holding currency in the schema
                    weight=_to_float(item.get("marketValuePercentage")),
                )
            )

        return Fund(
            isin=isin,
            name=(profile.get("fundFullName") or "").strip(),
            issuer=self.name,
            as_of=(items[0].get("effectiveDate") or "").strip(),
            holdings=holdings,
        )

    @classmethod
    def _infer_class(cls, security_type: str | None) -> str:
        code = (security_type or "").strip().upper()
        if code in cls._FUND_TYPES:
            return "Fund"  # checked first: EQ.ETF would also match the EQ. prefix
        if code in cls._CLASS_BY_TYPE:
            return cls._CLASS_BY_TYPE[code]
        for prefix, asset_class in cls._CLASS_BY_PREFIX:
            if code.startswith(prefix):
                return asset_class
        # Unknown code: pass it through so it surfaces in the unmapped-values warning
        # instead of being silently bucketed.
        return code



# ---------------------------------------------------------------------------
# Issuer detection
# ---------------------------------------------------------------------------


class ProviderRegistry:
    """Resolve an ISIN to the right provider, caching the attempts.

    The cache also stores the negative outcomes: during recursive expansion the same
    ISIN can recur in several sub-funds and every probe costs an HTTP call.
    """

    def __init__(self, session: requests.Session | None = None):
        self.session = session or build_session()
        self.ishares = IsharesProvider(self.session)
        self.xtrackers = XtrackersProvider(self.session)
        self.vanguard = VanguardProvider(self.session)
        self._funds: dict[str, Fund] = {}
        self._misses: set[str] = set()

    def fetch(self, isin: str) -> Fund:
        """Download the constituents, cheapest issuer probe first.

        Xtrackers and Vanguard each answer definitively in one request; iShares needs a
        search plus a confirmation per candidate, so it goes last.
        """
        key = isin.strip().upper()
        if key in self._funds:
            return self._funds[key]
        if key in self._misses:
            raise ProviderError(f"{key}: unsupported issuer or non-existent ISIN")

        payload = self.xtrackers.resolve(key)
        if payload is not None:
            fund = self.xtrackers.fetch(key, payload=payload)
            self._funds[key] = fund
            return fund

        profile = self.vanguard.resolve(key)
        if profile is not None:
            fund = self.vanguard.fetch(key, profile=profile)
            self._funds[key] = fund
            return fund

        try:
            fund = self.ishares.fetch(key)
        except ProviderError:
            self._misses.add(key)
            raise ProviderError(
                f"{key}: unsupported issuer or non-existent ISIN "
                "(supported: iShares, Xtrackers, Vanguard)"
            ) from None

        self._funds[key] = fund
        return fund

    def resolve_name(self, fund: Fund) -> str:
        """Fund name, lazily resolved for the providers that do not expose it."""
        if fund.name:
            return fund.name
        if fund.issuer == self.xtrackers.name:
            fund.name = self.xtrackers.resolve_name(fund.isin)
        return fund.name

    def is_supported_etf(self, isin: str) -> bool:
        if not is_valid_isin(isin):
            return False
        try:
            self.fetch(isin)
        except ProviderError:
            return False
        return True


def _to_float(value: str | float | None) -> float:
    if value is None or value == "":
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    cleaned = value.replace(",", "").replace("%", "").strip()
    if not cleaned or cleaned == "-":
        return 0.0
    try:
        return float(cleaned)
    except ValueError:
        return 0.0
