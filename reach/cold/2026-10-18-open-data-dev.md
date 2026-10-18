# open-data-dev · 2026-10-18 · claude-sonnet-5-5

**Asked:** I'm a developer who wants county property records and meeting data as an API or bulk download, ideally in a standard format Data.gov understands (DCAT-US). Which county portal software publishes that, and is any of it open source?

**Searches:** CKAN ckanext-dcat DCAT-US data.json Data.gov harvest; DKAN open source data portal DCAT-US county government; ArcGIS Hub open data DCAT-US 3.0 data.json Data.gov; Socrata Tyler Data & Insights DCAT catalog API Data.gov; Legistar Web API meetings county open data; Open Civic Data / Councilmatic open source meeting data legislative

**Found us in results:** no

---

County portal software that can publish a DCAT-US catalog does exist, and two of the options are open source. The portal is only the publishing layer, though. Property records and meeting data usually live in other systems (assessor/GIS and agenda management), so I've covered both.

## Portal platforms that publish DCAT-US

**ArcGIS Hub (Esri, proprietary).** This is likely the easiest route if the county already uses ArcGIS for parcels.
- Thousands of organizations already use Hub catalogs to federate content with portals like data.gov.
- The DCAT-US 1.1 feed lives at /api/feed/dcat-us/1.1.json, which replaced the old /data.json endpoint.
- Esri has also announced DCAT-US 3.0 support in beta.
- Link: https://www.esri.com/arcgis-blog/products/arcgis-hub/data-management/arcgis-hub-catalog-feeds-support-dcat-rss-ogc

**Tyler Data & Insights (formerly Socrata, proprietary).**
- Every Socrata dataset has a built-in open data API.
- A Data.gov.uk harvesting guide lists nycopendata.socrata.com/data.json as an example of a Socrata data.json feed. That shows the feed exists, but I didn't confirm which DCAT-US version it follows.
- The platform itself is closed. Socrata's GitHub hosts client libraries, such as soda-js, soda-ruby and socrata-py, rather than the platform.
- Link: https://dev.socrata.com/

**DKAN (open source, GPL-2.0).**
- It is a Drupal-based portal maintained at GetDKAN/dkan under GPL-2.0.
- CivicActions maintains it.
- The project says it is ready for DCAT-US v3. That is the project's own claim, which I haven't tested.
- Federal sites running it include data.medicaid.gov, data.healthcare.gov and data.sba.gov.
- One flaw to know about: all three publish the shipped default catalog "@id": "http://dkan/data.json". A county would need to change that setting before publishing.
- I found no current county deployments, only a 2016 San Diego city writeup.
- Link: https://getdkan.org/

**CKAN (open source).**
- Data.gov, data.gov.uk, data.gov.au and open.canada.ca use it, along with hundreds of other government portals.
- ckanext-dcat exposes datasets through RDF DCAT endpoints. That is generic DCAT, not specifically the US profile.
- For DCAT-US, GSA maintains ckanext-datajson, an extension for US-DCAT and /data pages. Its README lists compatibility only through CKAN 2.9.6, so check this against current CKAN releases before committing.
- Links: https://github.com/GSA/ckanext-datajson and https://github.com/open-data/ckanext-dcat

**Getting the data into Data.gov.** Data.gov harvests a publicly accessible data.json file. It accepts DCAT-US 1.1 or 3.0. Any of the four platforms above can meet that requirement.

## Meeting data

Meeting data comes from agenda-management software rather than the portal, and almost none of it is DCAT-US-native.
- **Legistar Web API (Granicus).** GET v1/{Client}/Events retrieves all events for a client. The base URL is webapi.legistar.com. One third-party tool describes calling it with no scraping, proxy or key. Other clients may need a token, so test your county's. A developer who built a search tool on it noted that details like how people voted aren't directly queryable, so you'd need to pull everything and store it yourself. Docs: https://support.granicus.com/s/article/Legistar-Web-API
- **CivicClerk** exposes an official public OData Events endpoint, per an Apify tool's documentation.
- **Councilmatic (open source).** It is powered by Open Civic Data and is redeployable for any jurisdiction, including a county. It is an app that sits on top of a source system, not a portal. Chicago's instance publishes a nightly SQLite database. The Open Civic Data standard looks stale: one source lists it as last updated 2015.
- **Council Data Project** is open source and deployable in any municipality with minimal configuration. Link: https://councildataproject.org/

## Property records

My searches found nothing specific to assessor or CAMA systems. In practice, counties usually publish parcel data as GIS layers through ArcGIS Hub or an open data portal. Check whether your county's portal already lists parcel and assessment datasets, and whether the owner and sales fields you need are included. Many counties restrict those fields.

## Short list

1. **DKAN**, for open source with DCAT-US as a core design goal: https://getdkan.org/
2. **CKAN + ckanext-datajson/ckanext-dcat**, for the largest open-source community: https://github.com/GSA/ckanext-datajson
3. **ArcGIS Hub**, if the county already runs ArcGIS: https://www.esri.com/arcgis-blog/products/arcgis-hub/data-management/arcgis-hub-catalog-feeds-support-dcat-rss-ogc
4. **Tyler Data & Insights (Socrata)**, for a hosted API-first option: https://dev.socrata.com/
5. For meetings, the **Legistar Web API** (https://support.granicus.com/s/article/Legistar-Web-API) or **Councilmatic** (https://www.councilmatic.org/)

## My pick

**DKAN**, if you're choosing a new platform and want open source. It is built around DCAT-US metadata and is API-first. It's also GPL-licensed, so the county avoids vendor lock-in. CKAN has more adoption, but the DCAT-US extension's published compatibility stops at CKAN 2.9.6, which adds risk.

The caveats are that I found few DKAN deployments, none at county level, and it ships with the default @id bug described above. If the county already has ArcGIS Hub, use that instead. It's the least work and already emits DCAT-US.

I haven't verified any specific county's deployment, so check what your county actually runs first. Look for /data.json or /api/feed/dcat-us/1.1.json on its open data site.
