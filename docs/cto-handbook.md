# CTO orientation handbook

Generate a portable, single-file HTML handbook and a printable PDF from repository
process definitions and a completed, verified synthetic UI recording run:

```bash
python3 scripts/cto_handbook.py
```

The output is a new timestamped directory under `artifacts/cto-handbook/` containing
`epfo-cto-handbook.html`, `epfo-cto-handbook.pdf` and `build.json`. Open the HTML in a
browser; it embeds its CSS, JavaScript, source data and original screenshot bytes.
No running portal, credentials, CDN or internet connection is needed. External
source links require internet access.

To refresh the copies linked from the frontend homepage, run:

```bash
python3 scripts/cto_handbook.py --publish-web
```

This publishes `index.html` and `epfo-cto-handbook.pdf` to
`apps/web/public/cto-handbook/`. The homepage links to
`/cto-handbook/index.html` and `/cto-handbook/epfo-cto-handbook.pdf`.

The HTML contains the process landscape, documented actor handoffs, curated POC
service ownership, a searchable role directory and glossary, fourteen process
field notes, six recorded claim journeys, integration proposals and build
provenance. The tagged PDF includes document bookmarks, the explanatory chapters,
a static process graph and its text alternative, every selected replay-step
caption and four screenshot anchors per journey.
The full selected screenshot replay lives in the HTML.

The default evidence input is
`artifacts/ui-manuals/20260930T091329986617Z/`. To select another completed run or
an explicit new output directory:

```bash
python3 scripts/cto_handbook.py --run artifacts/ui-manuals/<run-id> --output artifacts/cto-handbook/<new-name>
python3 scripts/cto_handbook.py --no-pdf
```

The curated replay definitions target the recorded baseline scenarios. A new run
must contain those scenarios and the selected screenshot anchors; review the
editorial notes and example amounts whenever the baseline changes. Never edit
original evidence to make an export pass.

Dependencies are the existing manual-generation environment (PyYAML, python-docx,
Pillow and Playwright with Chromium). Python-only HTML generation does not launch
a browser. PDF export requires a Chromium launch, which may require normal
environment approval in a restricted sandbox.

The importer requires passing JUnit case properties, completed manifests, matching
expected and observed outcomes, valid observation references and original PNG
hashes. It checks all screenshots in each manifest, including omitted repetitive
login / confirmation captures. It preserves original step numbers and excludes
repetitive authentication screens from the teaching replay.

Official source references, repository-model statements, verified synthetic
observations and integration proposals remain separate. Endpoint W/M/P/? labels
are inventory classifications, not UI-test results. Source currency and legal
applicability have not been certified. The recorded fixture is a frozen snapshot;
later edits to a working checkout do not alter what that run proved.

```bash
python3 -m pytest scripts/handbook/tests -q
python3 scripts/handbook/validate.py artifacts/cto-handbook/<run>/epfo-cto-handbook.html
```

The browser validator blocks HTTP(S), exercises the graph and replays, checks
mobile overflow and verifies embedded PNG hashes. It also exports a PDF unless
`--no-pdf` is supplied. It writes validation results and review screenshots next
to the handbook.
