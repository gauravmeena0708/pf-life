# Public establishment master in the synthetic POC

A sample establishment master CSV was provided as a **field-shape example**
only. The sample file is not checked in, read by the application, included in
container images, imported into a database, or copied into the synthetic seed.
The public directory uses the invented records in `scripts/seed/synthetic.json`.

The search and profile use a small public subset inspired by the sample header:

| Sample field | POC field | Public use |
| --- | --- | --- |
| `EST_ID`, `EST_NAME` | `establishment_id`, `legal_name` | Exact code / partial name search and profile |
| `OFFICE_ID`, `CITY`, `DISTRICT_NAME`, `PIN_CODE` | `office_id`, `city`, `district`, `pincode` | Location filters and profile |
| `COVER_DATE`, `EST_STATUS`, `EST_TYPE` | `coverage_date`, `status`, `establishment_type` | Coverage and type filters / profile |
| `EXEMPTION_STATUS`, `INDUSTRY_GROUP` | `exemption_status`, `industry_group` | Filters, industry search and profile |

The API deliberately excludes PAN, CIN, full address lines, email, UAN counts,
document flags, and member identity or banking indicators from anonymous
responses. A future real-data integration would need source authority, quality,
publication rules, and privacy review before any field is exposed.
