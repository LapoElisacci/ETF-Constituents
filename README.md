# ETF Constituents

Tools to analyze the real composition of an ETF portfolio.

The repo currently contains a single tool, **`etf_constituents`**: given the ISIN of an ETF it
downloads its constituents from the official issuer documents, normalizes them and exports
them to an XLSX. Normalization is the point: different issuers describe the same security
with different sectors, asset classes and country names, so without a shared vocabulary two
funds are not comparable and cannot be summed into a portfolio.

Supported issuers: **iShares** (BlackRock), **Xtrackers** (DWS) and **Vanguard**
(European UCITS range and US-domiciled ETFs alike).

## Repo layout

```
etf_constituents/
  etf_constituents.py   CLI entry point: recursive expansion, aggregation, balancing, XLSX
  providers.py          downloads per issuer and issuer detection (ProviderRegistry)
  taxonomy.py           Sector and Class normalization
  msci.py               Country -> Region/Category per the MSCI Market Classification
  requirements.txt
```

## Installation

Requires Python 3.10+ (the reference `.venv` runs 3.13).

```bash
python3 -m venv .venv
.venv/bin/pip install -r etf_constituents/requirements.txt
```

Dependencies: `requests`, `openpyxl`, `pycountry`.

## Using the CLI

```bash
.venv/bin/python etf_constituents/etf_constituents.py IE00B4L5Y983
.venv/bin/python etf_constituents/etf_constituents.py LU0397221945 -o portfolio.xlsx
.venv/bin/python etf_constituents/etf_constituents.py LU0274208692 --enrich-ticker -v
```

| Option              | Default                           | Effect                                              |
| ------------------- | --------------------------------- | --------------------------------------------------- |
| `isin` (positional) | --                                | ISIN of the ETF, validated before any network call  |
| `-o, --output`      | `{ISIN}_constituents_{date}.xlsx` | destination XLSX file                               |
| `--no-expand`       | off                               | do not expand constituents that are themselves ETFs |
| `--max-depth N`     | 3                                 | maximum expansion depth                             |
| `--enrich-ticker`   | off                               | resolve the missing Tickers via OpenFIGI            |
| `-v, --verbose`     | off                               | detailed logging                                    |

Logging goes to **stderr**, the result to a file: normalization warnings do not pollute the
output and stay visible even when redirecting.

**Exit codes**: `0` export succeeded, `1` unsupported issuer or failed download, `2` invalid
ISIN.

**`OPENFIGI_API_KEY`** (optional, only with `--enrich-ticker`): without a key OpenFIGI accepts
10 ISINs per request and 25 requests per minute; with a key it goes up to 100 ISINs per
request and 25 requests every 6 seconds. On a fund with thousands of positions that is the
difference between a few minutes and a few seconds.

## Output

Sheet **`Constituents`**, one row per security, sorted by descending weight with the balancing
row always last:

`Ticker, ISIN, Name, Sector, Class, Country, Region, Category, Currency, Weight`

`Weight` is written as an Excel percentage (`0.0000%`, so 0.0558 is rendered `5.5800%`) and the
column adds up to exactly 100%.

Sheet **`Metadata`** with the requested ISIN, fund name, issuer, as-of date of the
constituents, number of direct holdings, leaf rows before aggregation, rows in the output,
expansion and ticker-enrichment status, and the generation timestamp.

The normalized columns take values from closed sets:

| Column     | Values                                                                                                                                                                  |
| ---------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `Class`    | `Equity`, `Fixed Income`, `Cash`, `Derivative`, `Fund`, `Commodity`, `Other`                                                                                            |
| `Sector`   | the 11 GICS sectors, plus `Government`, `Cash & Derivatives`, `Other`                                                                                                   |
| `Category` | `Developed`, `Emerging`, `Frontier`, `Financial Center`, `Other`                                                                                                        |
| `Region`   | `North America`, `Latin America`, `Europe`, `Middle East & Africa`, `Asia Pacific`, `Other`                                                                             |

## How it works

The pipeline, in execution order.

**1. Issuer detection.** `ProviderRegistry` probes cheapest first: Xtrackers and Vanguard each
answer definitively in a single HTTP request, iShares needs a search plus a confirmation per
candidate. The cache also stores negative outcomes: during recursive expansion the same ISIN
recurs in several sub-funds and every attempt is a network call.

**2. Download.** The sources are the same ones that feed the official product pages.

- iShares: `core-search` resolves ISIN -> `portfolioId` (the search is fuzzy and returns
  results even for a non-existent ISIN, so every candidate is confirmed against
  `keyFundFacts`), then `get-product-data` with `component=holdings` returns the constituents.
  For numbers the `value` field is read and not `formattedValue`, which is rounded to 2
  decimals: on a fund with thousands of positions the accumulated error is worth whole
  percentage points (on IEAC, 101.79% against 99.9998%).
- Xtrackers: the CSV constituents export is addressable directly by ISIN. Weights come as a
  fraction and are converted to percentage points.
- Vanguard: the product page renders only the top ten holdings, so the full list comes from the
  GraphQL endpoint the page itself calls. `funds(isins:)` maps the ISIN to Vanguard's internal
  `portId` in one request and returns an empty list for anything that is not a Vanguard fund,
  which is what makes it cheap to probe. The holdings then come from `borHoldings`, 1500 at a
  time, following an opaque cursor. Two deliberate choices: the `securityTypes` filter the site
  applies is left unset, because it drops cash, FX and futures and leaves the weights at ~99.2%
  instead of 100%; and `holdings` is used rather than `delayeredHoldings`, which is Vanguard's
  own look-through of a fund of funds, since nested funds are expanded below instead.

**3. Normalization.** iShares uses *two* sector vocabularies (GICS-like on equity,
ICE/Bloomberg-like on fixed income: `Banking`, `Consumer Non-Cyclical`, `Basic Industry`...),
Xtrackers a third one, Vanguard reports GICS and ICB side by side (GICS is preferred, ICB is
the fallback). `taxonomy.py` maps them back to the 11 GICS sectors plus `Government`,
`Cash & Derivatives` and `Other`, and unifies the asset classes. An unmapped raw value ends up
in `Other` **with a warning on stderr**, so the tables get extended instead of degrading
silently.

As a cross-check: across the 1277 securities shared by the iShares MSCI World ETF and the
Xtrackers one, after normalization the `Class` values match 100% and the `Sector` values
diverge on 2 securities, because of real differences in the two issuers' data.

`Region` and `Category` follow the MSCI Market Classification (`msci.py`), on a static table
keyed by ISO code: issuers use non-ISO names (`Croatia (Hrvatska)`, and a `British Vergin
Islands` with a typo in the DWS export) and resolving them to a code before classifying avoids
chasing every variant. The two columns answer different questions and are kept apart: `Region`
is geography alone, `Category` is how developed the market is. The one spot where `Region` is
not the naive geographic answer is the CIS and the Caucasus, which stay in `Europe` because
that is where MSCI's "Europe & CIS" and EMEA families put them.

**4. Recursive expansion.** If a constituent is itself an ETF from a supported issuer, its row
is replaced by its own constituents, with weights rescaled on the actual child total. A
pre-filter on class, name and ISIN avoids probing the network for all the thousands of
positions of an equity fund. Cycles and depth are bounded; if the expansion fails the parent
row is kept, so the weight is not lost.

**5. Aggregation.** Rows describing the same security are merged by summing their weights,
filling empty fields from the values present in the duplicate rows.

**6. Balancing.** An `Other` row is appended to bring the total to exactly 100%. Below 0.1
percentage points the residual is issuer rounding noise and the row is added silently; above
it, it is reported with a warning.

## Known limitations

- **Xtrackers tickers**: the DWS export does not expose constituent tickers. They stay empty
  unless `--enrich-ticker` is used, which resolves them via OpenFIGI.
- **Xtrackers asset class**: the CSV has no asset class column, so it is inferred
  (pseudo-ISINs `_CURRENCY*` -> Cash and `___*` -> Derivative; for everything else the fund
  prevalence, measured on the coverage of the sector classification, which DWS only populates
  on equity). On a multi-asset ETF that is not a fund of funds the inference is less reliable.
- **Sector on Xtrackers bonds**: DWS leaves the sector classification as `unknown` on fixed
  income, so `Sector` comes out as `Other`. iShares does populate it. This is a difference in
  the source data, not in the normalization.
- **Vanguard currency**: the GraphQL schema has no per-holding currency field, so the
  `Currency` column stays empty for Vanguard funds -- the mirror image of the missing Xtrackers
  ticker, except there is no equivalent of `--enrich-ticker` to fill it in.
- **Sector on Vanguard bonds**: as with Xtrackers, part of the fixed income book carries no
  sector classification and comes out as `Other`.
- **Country**: iShares uses country-of-risk, Xtrackers the country of incorporation, Vanguard
  the Bloomberg ISO country. On the same index the three disagree on a tail of securities
  (typically companies incorporated in the Netherlands, Ireland or the Cayman Islands but
  operating in the US), so `Country` and `Region` are not strictly comparable across issuers.
- The endpoints are not documented public APIs: they are the ones used by the official
  websites and can change without notice.

## Generated files

The XLSX files produced by the CLI land in the working directory and are ignored by
`.gitignore` (`*.xlsx`): they should not be committed.
