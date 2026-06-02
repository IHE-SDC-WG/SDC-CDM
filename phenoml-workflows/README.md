# NAACCR to OMOP PhenoML Workflows

This package keeps the PhenoML-specific implementation in the same repository
as the working-group mapping spec, while isolating service credentials and SDK
usage from the neutral SQL and JSON artifacts.

## Credentials

Use environment variables or an untracked `.env` file:

```bash
PHENOML_INSTANCE_URL=https://your-phenoml-instance.example
PHENOML_CLIENT_ID=your_client_id
PHENOML_CLIENT_SECRET=your_client_secret
```

Do not commit real credentials. The root `.gitignore` ignores `.env` files.
`src/config.js` returns `null` when credentials are missing and throws the
explicit message `PhenoML credentials not configured` when a run requires them.

## Install

```bash
cd phenoml-workflows
python3.10 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

The package uses the official Python `phenoml` SDK from
`PhenoML/phenoml-python-sdk` and constructs clients with `client_id`,
`client_secret`, and `base_url`.

## Run The Local Harness

The local harness does not require credentials unless `--require-phenoml` is
passed. This lets mapping logic be tested before service execution is wired in.

```bash
PYTHONPATH=. python3 -m phenoml_workflows.run_workflow \
  --input sample/naaccr-case.example.json
```

or from the repository root:

```bash
PYTHONPATH=phenoml-workflows python3 -m phenoml_workflows.run_workflow \
  --input phenoml-workflows/sample/naaccr-case.example.json
```

## Mapping Review UI

Start the local review UI from the repository root:

```bash
PYTHONPATH=phenoml-workflows python3 -m phenoml_workflows.review_app
```

Open `http://127.0.0.1:5057/`. The dashboard includes:

- a **Download Excel** button wired to `GET /excel/export`;
- an **Upload Excel** file picker wired to `POST /excel/import`;
- a staged diff panel for reviewing workbook imports;
- an **Apply Import** button wired to `POST /excel/apply`;
- a **Download Diff Report** link wired to `GET /excel/diff`.

The UI writes only review fields into the canonical JSON spec. The mapping
fields generated from source workbooks remain unchanged.

## Excel CLI

Export the human-readable review workbook:

```bash
PYTHONPATH=phenoml-workflows python3 -m phenoml_workflows.review_excel export \
  --output phenoml-workflows/output/naaccr_omop_mapping_review.xlsx
```

Stage an import diff from a reviewed workbook:

```bash
PYTHONPATH=phenoml-workflows python3 -m phenoml_workflows.review_excel import \
  --input reviewed.xlsx \
  --patch-report phenoml-workflows/output/review_diff.json
```

Apply valid review-field changes after inspection:

```bash
PYTHONPATH=phenoml-workflows python3 -m phenoml_workflows.review_excel import \
  --input reviewed.xlsx \
  --patch-report phenoml-workflows/output/review_diff.json \
  --apply
```

Excel import matches rows by `concept_class_id + concept_code`, rejects invalid
review statuses, ignores source-column edits, and reports ignored edits in the
diff. Valid statuses are `unreviewed`, `needs_review`, `approved`, `rejected`,
and `deferred`.

The harness reads:

- `../database/naaccr_omop/naaccr_omop_extension_mapping_spec.json`
- `workflows/naaccr-to-omop.workflow.json`
- a NAACCR case JSON input

and emits OMOP-shaped row groups for:

- `episode`
- `measurement`
- `observation`
- `episode_event`
- NAACCR extension tables

## Current Scope

This is a deterministic local runner around the JSON workflow definition and
generated mapping spec. Service-backed PhenoML workflow execution can be added
behind the same config boundary using the SDK's `client.workflows` surface once
the target workflow lifecycle for this project is fixed.
