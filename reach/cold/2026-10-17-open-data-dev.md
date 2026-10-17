# open-data-dev · 2026-10-17 · claude-sonnet-5-5

**Asked:** I'm a developer who wants county property records and meeting data as an API or bulk download, ideally in a standard format Data.gov understands (DCAT-US). Which county portal software publishes that, and is any of it open source?

**Searches:** DKAN open source DCAT-US data.json county open data portal; CKAN ckanext-dcat DCAT-US data.gov harvest; ArcGIS Hub data.json DCAT-US open data site; Socrata Tyler data.json DCAT federal catalog data.gov harvest; Legistar Web API meeting data open source Councilmatic

**Found us in results:** no

---

**Short answer:** Three hosted platforms and two open-source ones publish DCAT-US. Two of them (CKAN and DKAN) are open source. Meeting data usually comes from a separate system with its own API, and Data.gov doesn't host the data anyway.

## How the pieces fit
- Data.gov doesn't host data files. It collects metadata (descriptions, contacts and download links) from a file your agency publishes, normally a `data.json`. So the portal publishes the catalog, and the underlying data still has to be loaded into it.
- Property records and meeting minutes typically live in other systems: assessor and recorder systems, GIS parcel layers, and agenda software. The portal only has them if the county loads them. I didn't find a source on how counties publish property data, so check that with the county directly.

## Options

**Open source**
- **CKAN.** It's described as the leading open-source data management system for open data portals, and the license is AGPL v3.0. The `ckanext-dcat` extension supports DCAT-US v3 through pre-built schemas, and includes a `dcat_us_recommended.yaml` schema for the DCAT-US spec. It's currently supported on CKAN 2.10 and 2.11. GSA's `ckanext-datajson` handles the older v1.1 format. Catalog.data.gov uses it to harvest remote `/data.json` files.
  - Docs: https://docs.ckan.org/projects/ckanext-dcat/
  - GSA extension: https://github.com/GSA/ckanext-datajson
- **DKAN.** It's a Drupal open data portal maintained at GetDKAN/dkan under GPL-2.0. CivicActions maintains it, and the project says it's ready for DCAT-US v3. One caveat: a recent third-party census found that the three federal DKAN portals it probed all publish the shipped default catalog ID `http://dkan/data.json`. That's a default-configuration problem you'd need to override. It is a third-party analysis, not an official one.
  - Site: https://getdkan.org/

**Hosted, proprietary**
- **ArcGIS Hub (Esri).** It's a good fit if the county already keeps parcels in ArcGIS. Its feeds include DCAT US 1.1 at `<siteURL>/api/feed/dcat-us/1.1.json`, and DCAT-US 3.0 is now in beta. Hub also offers an OGC API – Records feed (`/api/search/definition`). Only publicly shared items appear in the feed. Esri community posts report some Hub `data.json` download links broken by a template error. That was in 2022, so verify it against any county you'd rely on.
  - Docs: https://doc.arcgis.com/en/hub/content/federate-data.htm
- **Socrata (Tyler Technologies).** It natively supports `data.json`. A GitHub issue from the Connecticut state portal says it's Tyler/Socrata-hosted and needs vendor support to update its metadata pipeline to DCAT-US 3. Treat v3 support as something to confirm with the vendor.
  - Data.gov onboarding: https://resources.data.gov/resources/data-gov-open-data-howto/

**Meeting data (not a portal)**
- **Legistar (Granicus).** This is a common agenda system for large counties and cities. It has an official public JSON Web API at webapi.legistar.com. That's an API, not DCAT, so you'd list it in your catalog as a distribution. The API has a limitation: meeting items and votes aren't directly queryable and sit behind event or matter IDs. In practice you have to bulk-pull and store the data yourself.
- **Councilmatic (open source).** It's an open-source front end that scrapes the Legistar API into a database of standardized council, legislation and event data. A reference implementation is at https://github.com/datamade/chi-councilmatic.

## Recommendation
**CKAN with `ckanext-dcat` and its DCAT-US 3 schema.** It's the only option here that is open source (AGPL) and has a documented DCAT-US 3 profile. It also has a full JSON Action API, and it's the same software family Data.gov's catalog uses. Load property data as CKAN resources or datastore tables. Register Legistar or other agenda APIs as dataset distributions, or mirror them in bulk.

Choose differently in these cases:
- **DKAN:** if the county's web team already runs Drupal.
- **ArcGIS Hub:** if the county has no hosting capacity and parcels are already in ArcGIS. You'd give up open source.

Self-hosting CKAN means you run Solr, PostgreSQL and Redis. Budget for that, or use a managed CKAN provider. I haven't evaluated any managed providers.
