# ETF Constituents

Tools to analyze the real composition of an ETF portfolio.

The repo currently contains a single tool, **`etf_constituents`**: given the ISIN of an ETF it
downloads its constituents from the official issuer documents, normalizes them and exports
them to an XLSX. Normalization is the point: different issuers describe the same security
with different sectors, asset classes and country names, so without a shared vocabulary two
funds are not comparable and cannot be summed into a portfolio.

Supported issuers: **iShares** (BlackRock), **Xtrackers** (DWS), **Vanguard**,
**SPDR** (State Street) and **Amundi** (including the absorbed Lyxor range). iShares,
Xtrackers and Vanguard cover the European UCITS range and US-domiciled ETFs alike; SPDR
covers the UCITS range only (see the limitations below). **UBS** is supported from a
workbook you download yourself, via `--holdings-file`: its holdings are not reachable
programmatically (see the limitations below).

## Disclaimer

**No warranty. No liability. Verify every figure before relying on it.**

This software is provided "as is", without warranty of any kind, express or implied, including
but not limited to the warranties of merchantability, fitness for a particular purpose and
non-infringement. In no event shall the author or copyright holder be liable for any claim,
damages or other liability, whether in an action of contract, tort or otherwise, arising from,
out of or in connection with this software or the use of or other dealings in it. To the maximum
extent permitted by applicable law, the author disclaims all liability for any direct, indirect,
incidental, special, consequential, exemplary or punitive damages, and for any trading or
investment loss, however caused.

The output is assembled from undocumented endpoints of the issuers' public websites. Those
endpoints can change, break, or return incomplete, stale or incorrect data at any time, and the
processing applied here -- sector and asset class mapping, country and region classification,
look-through of nested funds, weight rescaling and the balancing row -- introduces further
approximation. Figures may not match the issuer's official documentation and must not be assumed
to be accurate, complete or current.

Nothing produced by this tool is investment, financial, legal, accounting or tax advice, nor a
recommendation, offer or solicitation to buy or sell any security. Before relying on any figure
for any purpose, verify it against the fund's official documentation -- KID/KIID, prospectus,
annual and semi-annual reports, and the issuer's own published holdings files -- which are the
only authoritative sources.

This project is not affiliated with, endorsed by, sponsored by or otherwise connected to
BlackRock (iShares), DWS (Xtrackers), Vanguard, State Street (SPDR), Amundi (Lyxor), UBS,
MSCI, FTSE Russell, S&P, ICE, Bloomberg, OpenFIGI or any other party named in this
repository. All
trademarks, index names and fund names are the property of their respective owners and are used
here for identification only.
You are solely responsible for ensuring that your use of the third-party endpoints complies with
the applicable terms of service and with all applicable laws, including those on database and
copyright.

By using this software you accept the above and assume full responsibility for any decision taken
on the basis of its output.

## Repo layout

```
etf_constituents/
  etf_constituents.py   CLI entry point: recursive expansion, aggregation, balancing, XLSX
  providers.py          downloads per issuer and issuer detection (ProviderRegistry)
  taxonomy.py           Sector and Class normalization
  msci.py               Country -> Region/Category per the MSCI Market Classification
  currency.py           fallback Currency inferred from the country
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
| `--max-depth N`     | -1 (unlimited)                    | maximum expansion depth, negative for unlimited     |
| `--holdings-file`   | --                                | read constituents from a downloaded workbook (UBS)  |
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

A single sheet, **`Constituents`**, one row per security *per source ETF*, sorted by descending
weight with the balancing row always last:

`Ticker, ISIN, Name, Sector, Class, Country, Region, Category, Currency, Weight`

When a row comes from an expanded ETF, `Name` carries that ETF in brackets --
`Apple Inc (Vanguard FTSE All-World UCITS ETF)`. A security reached through several sub-funds
therefore appears once per sub-fund, so the same ISIN can repeat: the weights still add up to
100%, and a pivot on ISIN recovers the single aggregated line.

`Weight` is written as an Excel percentage (`0.0000%`, so 0.0558 is rendered `5.5800%`) and the
column adds up to exactly 100%.

`Currency` is taken from the issuer when it publishes one. When it does not -- Vanguard never
does -- it is inferred from the country, which fills it on about 99.99% of the weight of a
Vanguard fund. The inference is an indication, not a fact: see the limitations below.

The normalized columns take values from closed sets:

| Column     | Values                                                                                      |
| ---------- | ------------------------------------------------------------------------------------------- |
| `Class`    | `Equity`, `Fixed Income`, `Cash`, `Derivative`, `Fund`, `Commodity`, `Other`                |
| `Sector`   | the 11 GICS sectors, plus `Government`, `Cash & Derivatives`, `Other`                       |
| `Category` | `Developed`, `Emerging`, `Frontier`, `Financial Center`, `Other`                            |
| `Region`   | `North America`, `Latin America`, `Europe`, `Middle East & Africa`, `Asia Pacific`, `Other` |

## How it works

The pipeline, in execution order.

**1. Issuer detection.** `ProviderRegistry` probes cheapest first: SPDR pays for its whole fund
directory on the first probe and answers from memory afterwards, so it costs one request for the
entire run; Xtrackers and Vanguard each answer definitively in a single HTTP request; iShares needs
a search plus a confirmation per candidate, so it goes last. Amundi sits between them, at one
request per country site. The cache also stores negative outcomes: during recursive expansion
the same ISIN recurs in several sub-funds and every attempt is a network call.

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
- SPDR: State Street has no per-ISIN lookup, so the fund finder behind the product listing is
  downloaded once (it returns the whole directory in one response and the site filters it client
  side) and mapped to the daily holdings workbook of each fund. The workbook states the ISIN it
  belongs to, so it validates itself. SSGA ships five different column layouts across the range --
  equity, fixed income, a legacy variant, commodity and CLO -- that differ in both order and
  spelling (`Currency` / `Currency Local` / `Local Currency`, `Trade Country Name` /
  `Country of Issue` / `Trade Country`), so columns are located by name and not by position.
- Amundi: the product page renders its holdings from an endpoint that only returns the full
  book when the request carries a `composition.compositionFields` list; without it the field
  comes back null and the page falls back to a ten-line breakdown, which is what the issuer's
  own Excel export is built from. The field list the site sends is used verbatim. The whole
  book arrives in one response (the largest fund seen is 12136 lines) and
  `totalNumberOfInstruments` confirms nothing was truncated. Values are English whatever the
  locale requested: the localized spellings in Amundi's own export are applied client side and
  never reach the API. Two country sites are probed, FR then UK, because a fund is only listed
  where it is registered and neither list is a superset of the other.
- UBS is the exception: it is not fetched. Its holdings sit behind a GraphQL endpoint
  that validates a short-lived Azure AD token minted for the product page, and that page
  is geo-restricted, so outside the permitted regions there is no page to read the token
  out of. The endpoint carries exactly the same six columns as the **Costituenti** download
  anyway, so nothing is lost by reading the file: pass it with `--holdings-file` and the
  ISIN of the fund. The export is OOXML despite its `.xls` extension, and it follows the
  language of the site it came from, so the weight column is parsed both as `14,98683` and
  as `14.98683` and whichever reading totals 100% wins.

**3. Normalization.** iShares uses *two* sector vocabularies (GICS-like on equity,
ICE/Bloomberg-like on fixed income: `Banking`, `Consumer Non-Cyclical`, `Basic Industry`...),
Xtrackers a third one, Vanguard reports GICS and ICB side by side (GICS is preferred, ICB is
the fallback), SPDR mixes GICS on most funds with ICB industry names on the UK, European and
real estate ones, and Amundi reports GICS sectors with its own instrument-type codes
(`EQUITY_ORDINARY`, `CORPORATE`, `TREASURY_BILL`...) in place of an asset class. `taxonomy.py`
maps them back to the 11 GICS sectors plus `Government`, `Cash & Derivatives` and `Other`, and
unifies the asset classes. An unmapped raw value ends up
in `Other` **with a warning on stderr**, so the tables get extended instead of degrading
silently.

As a cross-check: across the 1277 securities shared by the iShares MSCI World ETF and the
Xtrackers one, after normalization the `Class` values match 100% and the `Sector` values
diverge on 2 securities, because of real differences in the two issuers' data. Same exercise on the
S&P 500, between the SPDR and the iShares UCITS trackers: 503 shared securities, `Country` matching
100%, `Sector` diverging on 1, and a mean weight difference of 0.004 percentage points -- which is
the one-day lag between the two holdings files, not a normalization gap. The Amundi reader was
checked against the issuer's own Excel export of the same fund on the same date: all 1274 ISINs
and weights match to floating point, plus the cash line that Amundi's export drops and this tool
keeps, which is what takes the total from 99.68% to 100%.

`Currency` comes straight from the issuer where it exists. Where it does not, `currency.py`
derives it from the country, so the column is usable rather than empty.

`Region` and `Category` follow the MSCI Market Classification (`msci.py`), on a static table
keyed by ISO code: issuers use non-ISO names (`Croatia (Hrvatska)`, and a `British Vergin
Islands` with a typo in the DWS export) and resolving them to a code before classifying avoids
chasing every variant. The two columns answer different questions and are kept apart: `Region`
is geography alone, `Category` is how developed the market is. The one spot where `Region` is
not the naive geographic answer is the CIS and the Caucasus, which stay in `Europe` because
that is where MSCI's "Europe & CIS" and EMEA families put them.

**4. Recursive expansion.** If a constituent is itself an ETF from a supported issuer, its row
is replaced by its own constituents, with weights rescaled on the actual child total, and each
resulting row is tagged with the ETF it came directly from. A pre-filter on class, name and ISIN
avoids probing the network for all the thousands of positions of an equity fund. This runs all
the way down by default: what bounds it is the cycle guard and the provider miss cache, not a
depth limit, though `--max-depth` still caps it on request. If the expansion fails the parent row
is kept, so the weight is not lost.

**5. Aggregation.** Rows describing the same security *from the same source ETF* are merged by
summing their weights, filling empty fields from the values present in the duplicate rows. The
source is part of the key on purpose: merging on ISIN alone would print one arbitrary ETF name
next to a weight that came from several.

**6. Balancing.** A `Weight balance` row is appended to bring the total to exactly 100%. Below 0.1
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
- **Inferred currency**: the Vanguard GraphQL schema has no per-holding currency field at all,
  so for Vanguard funds the whole column is derived from the country rather than read from the
  source. The country is the issuer's country of risk or of incorporation, which is not
  necessarily where the security trades: a Hong Kong listing of a mainland Chinese company comes
  out `CNY`, not `HKD`. Countries with no local market for securities -- offshore centres,
  dollarised economies -- are mapped to their de facto currency, since nothing is really priced
  in `KYD` or `MOP`. Rows with no attributable country, chiefly FX forwards and supranational
  paper, keep an empty `Currency`. Treat the column as an indication on Vanguard funds and read
  it from the issuer's own files when it matters.
- **Sector on Vanguard bonds**: as with Xtrackers, part of the fixed income book carries no
  sector classification and comes out as `Other`.
- **SPDR asset class**: the workbook has no asset class column, so it is inferred. The layout
  gives the prevailing class of the fund (only the equity one carries a sector column) and the
  rows that depart from it are the ones SSGA leaves without an ISIN: FX balances, futures and
  swaps, recognised by name.
- **Sector on SPDR bonds**: the fixed income layout has no sector column at all, so `Sector` comes
  out as `Other` on the whole book. The equity layout does carry one.
- **SPDR US range**: only the EMEA (UCITS) funds are covered. The parallel US feed publishes name,
  CUSIP and SEDOL but no ISIN, country or currency per holding, so its rows could neither be
  aggregated by ISIN nor expanded when they are themselves funds.
- **Amundi asset class**: the feed carries an instrument type rather than an asset class, so
  `Class` is derived from it (`EQUITY_ORDINARY` -> Equity, `CORPORATE`/`GOVERNMENT` -> Fixed
  Income, `TREASURY_BILL`/`CERTIFICATE_OF_DEPOSIT` -> Cash, and so on). Money market paper is
  bucketed as Cash, matching how Vanguard's `MM.` prefix is treated.
- **UBS is file-only, and thin**: the export carries just security name, ISIN, SEDOL,
  currency, price and weight. There is no sector and no asset class, so `Sector` and
  `Class` come out `Other` on every row, and no country either, so `Country` is derived
  from the ISIN prefix (`CH0012005267` -> Switzerland). That is the country of
  registration rather than of risk, which is a coarser approximation than the other five
  issuers provide -- a company registered in Ireland but operating elsewhere lands in
  Ireland. There is also no ticker, only a SEDOL; use `--enrich-ticker` if you need one.
- **Country**: iShares uses country-of-risk, Xtrackers the country of incorporation, Vanguard
  the Bloomberg ISO country, SPDR the trade country on equity and the country of issue on bonds,
  Amundi its own country-of-risk, UBS none at all (see above).
  On the same index they disagree on a tail of securities (typically companies incorporated in the
  Netherlands, Ireland or the Cayman Islands but operating in the US), so `Country` and `Region`
  are not strictly comparable across issuers.
- The endpoints are not documented public APIs: they are the ones used by the official
  websites and can change without notice.

## Generated files

The XLSX files produced by the CLI land in the working directory and are ignored by
`.gitignore` (`*.xlsx`): they should not be committed.
