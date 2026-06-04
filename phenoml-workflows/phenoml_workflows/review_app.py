from __future__ import annotations

import json
import tempfile
from io import BytesIO
from pathlib import Path
from typing import Any

from .json_io import resolve_package_path, read_json, write_json
from .review_excel import apply_import_report, build_import_report, workbook_bytes
from .review_schema import REVIEW_FIELDS
from .review_store import DEFAULT_SPEC_PATH, item_mappings, load_spec, save_spec, update_review_fields

STAGED_DIFF_PATH = resolve_package_path("output/review_import_staged.json")


def _require_flask():
    try:
        from flask import Flask, jsonify, request, send_file
    except ImportError as error:
        raise RuntimeError(
            "Flask is required. Install with: pip install -r phenoml-workflows/requirements.txt"
        ) from error

    return Flask, jsonify, request, send_file


def _filter_mappings(spec: dict[str, Any], args: Any) -> list[dict[str, Any]]:
    q = (args.get("q") or "").strip().lower()
    status = (args.get("status") or "").strip()
    target = (args.get("target") or "").strip().upper()
    limit = int(args.get("limit") or 250)
    rows = []
    for mapping in item_mappings(spec):
        haystack = " ".join(
            str(mapping.get(field) or "")
            for field in (
                "concept_id",
                "concept_class_id",
                "concept_code",
                "concept_name",
                "storage",
                "suggested_storage",
                "omop_target",
                "omop_table",
                "omop_field",
                "naaccr_person_column",
                "proposed_extension_table",
                "proposed_extension_column",
                "person_mapping_notes",
            )
        ).lower()
        if q and q not in haystack:
            continue
        if status and mapping.get("review_status") != status:
            continue
        if target and target not in str(mapping.get("omop_table") or "").upper() and target not in str(mapping.get("mapping_kind") or "").upper():
            continue
        rows.append(mapping)
        if len(rows) >= limit:
            break
    return rows


def create_app():
    Flask, jsonify, request, send_file = _require_flask()
    app = Flask(__name__)

    @app.get("/")
    def dashboard():
        return DASHBOARD_HTML

    @app.get("/api/mappings")
    def api_mappings():
        spec = load_spec()
        rows = _filter_mappings(spec, request.args)
        return jsonify(
            {
                "rows": rows,
                "total_returned": len(rows),
                "review_fields": list(REVIEW_FIELDS),
            }
        )

    @app.patch("/api/mappings/<concept_class_id>/<concept_code>/review")
    def api_update_review(concept_class_id: str, concept_code: str):
        spec = load_spec()
        payload = request.get_json(silent=True) or {}
        try:
            result = update_review_fields(
                spec=spec,
                concept_class_id=concept_class_id,
                concept_code=concept_code,
                updates=payload,
            )
        except (KeyError, ValueError) as error:
            return jsonify({"error": str(error)}), 400
        save_spec(spec)
        return jsonify(result)

    @app.get("/excel/export")
    def excel_export():
        spec = load_spec()
        data = workbook_bytes(spec)
        return send_file(
            BytesIO(data),
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            as_attachment=True,
            download_name="naaccr_omop_mapping_review.xlsx",
        )

    @app.post("/excel/import")
    def excel_import():
        upload = request.files.get("workbook")
        if upload is None:
            return jsonify({"error": "Missing multipart file field: workbook"}), 400
        spec = load_spec()
        with tempfile.NamedTemporaryFile(suffix=".xlsx") as temp:
            upload.save(temp.name)
            report = build_import_report(spec, Path(temp.name))
        write_json(STAGED_DIFF_PATH, report)
        return jsonify(report), 200 if report["valid"] else 400

    @app.post("/excel/apply")
    def excel_apply():
        if not STAGED_DIFF_PATH.exists():
            return jsonify({"error": "No staged import diff exists."}), 400
        report = read_json(STAGED_DIFF_PATH)
        spec = load_spec(DEFAULT_SPEC_PATH)
        try:
            applied = apply_import_report(spec, report)
        except RuntimeError as error:
            return jsonify({"error": str(error), "report": report}), 400
        save_spec(spec, DEFAULT_SPEC_PATH)
        write_json(STAGED_DIFF_PATH, applied)
        return jsonify(applied)

    @app.get("/excel/diff")
    def excel_diff():
        if not STAGED_DIFF_PATH.exists():
            return jsonify({"error": "No staged import diff exists."}), 404
        return send_file(
            STAGED_DIFF_PATH,
            mimetype="application/json",
            as_attachment=True,
            download_name="naaccr_omop_mapping_review_diff.json",
        )

    return app


DASHBOARD_HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>NAACCR to OMOP Mapping Review</title>
  <style>
    body { margin: 0; font-family: Arial, sans-serif; color: #222; background: #f6f7f8; }
    header { background: #263238; color: white; padding: 14px 22px; }
    main { padding: 18px 22px; }
    .toolbar, .panel { background: white; border: 1px solid #d7dce0; border-radius: 6px; padding: 12px; margin-bottom: 14px; }
    .toolbar { display: flex; gap: 10px; align-items: center; flex-wrap: wrap; }
    input, select, button, a.button { border: 1px solid #bcc5cc; border-radius: 4px; padding: 7px 9px; font-size: 14px; }
    button, a.button { background: #285f8f; color: white; cursor: pointer; text-decoration: none; }
    button.secondary { background: #546e7a; }
    button.danger { background: #9b3d35; }
    table { width: 100%; border-collapse: collapse; background: white; font-size: 13px; }
    th, td { border: 1px solid #d7dce0; padding: 6px 7px; vertical-align: top; }
    th { background: #e9eef2; position: sticky; top: 0; z-index: 1; }
    td textarea { width: 100%; min-height: 42px; }
    .table-wrap { max-height: 68vh; overflow: auto; border: 1px solid #d7dce0; }
    .muted { color: #667; }
    .diff { white-space: pre-wrap; max-height: 260px; overflow: auto; background: #111; color: #e9f2e9; padding: 10px; border-radius: 4px; }
  </style>
</head>
<body>
  <header><h1>NAACCR to OMOP Mapping Review</h1></header>
  <main>
    <section class="toolbar">
      <input id="q" placeholder="Search concepts, codes, tables">
      <select id="status">
        <option value="">All statuses</option>
        <option>unreviewed</option><option>needs_review</option><option>approved</option><option>rejected</option><option>deferred</option>
      </select>
      <button id="refresh">Refresh</button>
      <a class="button" href="/excel/export">Download Excel</a>
      <form id="upload-form" enctype="multipart/form-data">
        <input id="workbook" name="workbook" type="file" accept=".xlsx">
        <button type="submit">Upload Excel</button>
      </form>
      <button id="apply" class="danger" disabled>Apply Import</button>
      <a class="button" href="/excel/diff">Download Diff Report</a>
    </section>
    <section class="panel">
      <strong>Import Diff</strong>
      <p class="muted">Uploading Excel stages a diff. Applying writes validated review fields to canonical JSON.</p>
      <div id="diff" class="diff">No import staged.</div>
    </section>
    <section class="table-wrap">
      <table>
        <thead>
          <tr><th>Class</th><th>Item #</th><th>Code</th><th>Name</th><th>Storage</th><th>Target</th><th>Field</th><th>Extension</th><th>Status</th><th>Reviewer Notes</th><th>Action</th></tr>
        </thead>
        <tbody id="rows"></tbody>
      </table>
    </section>
  </main>
  <script>
    async function loadRows() {
      const q = encodeURIComponent(document.getElementById('q').value);
      const status = encodeURIComponent(document.getElementById('status').value);
      const response = await fetch(`/api/mappings?q=${q}&status=${status}&limit=500`);
      const data = await response.json();
      const tbody = document.getElementById('rows');
      tbody.innerHTML = '';
      for (const row of data.rows) {
        const tr = document.createElement('tr');
        tr.innerHTML = `
          <td>${row.concept_class_id || ''}</td>
          <td>${row.concept_id || ''}</td>
          <td>${row.concept_code || ''}</td>
          <td>${row.concept_name || ''}</td>
          <td>${row.storage || row.mapping_kind || ''}</td>
          <td>${row.omop_table || row.mapping_kind || ''}</td>
          <td>${row.omop_field || row.omop_target || row.naaccr_person_column || ''}</td>
          <td>${[row.proposed_extension_table, row.proposed_extension_column].filter(Boolean).join('.')}</td>
          <td>
            <select class="review_status">
              ${['unreviewed','needs_review','approved','rejected','deferred'].map(s => `<option ${row.review_status === s ? 'selected' : ''}>${s}</option>`).join('')}
            </select>
          </td>
          <td><textarea class="review_notes">${row.review_notes || ''}</textarea></td>
          <td><button class="save">Save Review</button></td>`;
        tr.querySelector('.save').addEventListener('click', async () => {
          const payload = {
            review_status: tr.querySelector('.review_status').value,
            review_notes: tr.querySelector('.review_notes').value
          };
          const url = `/api/mappings/${encodeURIComponent(row.concept_class_id)}/${encodeURIComponent(row.concept_code)}/review`;
          const result = await fetch(url, { method: 'PATCH', headers: {'content-type':'application/json'}, body: JSON.stringify(payload) });
          if (!result.ok) alert(await result.text());
        });
        tbody.appendChild(tr);
      }
    }
    document.getElementById('refresh').addEventListener('click', loadRows);
    document.getElementById('q').addEventListener('input', () => setTimeout(loadRows, 150));
    document.getElementById('status').addEventListener('change', loadRows);
    document.getElementById('upload-form').addEventListener('submit', async (event) => {
      event.preventDefault();
      const formData = new FormData();
      formData.append('workbook', document.getElementById('workbook').files[0]);
      const response = await fetch('/excel/import', { method: 'POST', body: formData });
      const report = await response.json();
      document.getElementById('diff').textContent = JSON.stringify(report, null, 2);
      document.getElementById('apply').disabled = !report.valid;
    });
    document.getElementById('apply').addEventListener('click', async () => {
      const response = await fetch('/excel/apply', { method: 'POST' });
      const report = await response.json();
      document.getElementById('diff').textContent = JSON.stringify(report, null, 2);
      await loadRows();
    });
    loadRows();
  </script>
</body>
</html>"""


def main() -> int:
    app = create_app()
    app.run(host="127.0.0.1", port=5057, debug=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
