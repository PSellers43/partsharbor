# Demography + registration mix (AssemblyEdge Focus drill)

Static JSON for beachhead Assembly districts: **ACS 5-year** demographics and **CA SOS** voter registration party mix. Consumed by the Focus intra-district drill panel (`js/demography.js`).

## Official sources

| Layer | Source | URL |
|-------|--------|-----|
| ACS (population, age, race/ethnicity, income, tenure) | U.S. Census Bureau ACS 5-year, CA Assembly (lower chamber / CRC 2020 lines) | Default fetch: [Census Reporter API](https://api.censusreporter.org/) (`latest` → ACS 2024 5-year as of build). Optional: [Census Data API](https://api.census.gov/data/2023/acs/acs5) with free `CENSUS_API_KEY`. |
| Registration by party | CA Secretary of State **Report of Registration** — Registration by State Assembly District (XLSX) | [Feb 2025 odd-year ROR](https://www.sos.ca.gov/elections/report-registration/ror-odd-year-2025) → `assembly.xlsx` on `elections.cdn.sos.ca.gov` |

**Not included:** voter file, contact fields, precinct-level registration, or paid enrichment.

## Layout

```
data/demography/
  README.md
  scripts/build_demography_json.py
  raw/                          # downloaded SOS XLSX (gitignored if large; optional commit)
  latest/
    demography-by-district.json           # consumed by the UI
    demography-by-district-YYYY-MM-DD.json
```

## Refresh

From the AssemblyEdge static root (`admin-portal/public/admin/assemblyedge/`):

```bash
python3 data/demography/scripts/build_demography_json.py
```

Options:

```bash
# Pin a different SOS report (update as_of in script or edit output metadata after verify)
python3 data/demography/scripts/build_demography_json.py \
  --ror-url 'https://elections.cdn.sos.ca.gov/ror/ror-odd-year-2025/assembly.xlsx'

# Use a local SOS export
python3 data/demography/scripts/build_demography_json.py --ror-file /path/to/assembly.xlsx

# Prefer direct Census API (requires free key from api.census.gov/data/key_signup.html)
export CENSUS_API_KEY='your-key'
python3 data/demography/scripts/build_demography_json.py --census-api
```

After refresh, bump trust labels in the UI by committing the new `latest/demography-by-district.json` (and dated copy). No Worker deploy secrets required for local/static refresh.

## Matching notes

- ACS geography uses Census **state legislative district (lower chamber)** GEOIDs `62000US06###` (CA Assembly district number).
- SOS worksheet totals are **registered voters**, not CVAP or adult population — label accordingly in the desk UI.
- Minor parties are rolled into **Other / minor** for readability (AIP, Green, Libertarian, Peace & Freedom, Unknown, Other columns from SOS).

## Gaps

If a district row is missing ACS or registration data, the build script records entries in `gaps[]` on the JSON payload. The UI shows a labeled empty state rather than silent failure.
