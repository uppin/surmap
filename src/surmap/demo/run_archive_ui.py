"""The page's Export and Import buttons for runs (`surmap.demo.run_archive`).

Export downloads the selected run (or the current one) as a `.surmaprun`
file from `GET /runs/<id>/export`. Import picks a `.surmaprun` file and
uploads it to `POST /runs/import`; the run list is refreshed and the first
imported run selected, ready for Load run or Replay run. A run already in
the history is reported as such, not imported twice.

The script is spliced into the page before the server formats it, so its
braces stay doubled for str.format; the markup is part of the page
template too.
"""

from __future__ import annotations

RUN_ARCHIVE_MARKUP = """    <button class="btn" id="run-export" type="button"
      title="Download the selected run (and any run it replays) as a .surmaprun file"
      >Export</button>
    <button class="btn" id="run-import" type="button"
      title="Add the runs in a .surmaprun file to this console's history">Import</button>
    <input type="file" id="run-import-file" accept=".surmaprun" hidden>"""

RUN_ARCHIVE_SCRIPT = """// --- Export / import runs as .surmaprun files (run_archive.py) ---
$('run-export').addEventListener('click', () => {{
  const runId = runSelect.value || currentRunId;
  if (!runId) {{ runInfo.textContent = 'Pick a run to export first.'; return; }}
  const link = document.createElement('a');
  link.href = `/runs/${{encodeURIComponent(runId)}}/export`;
  link.download = '';  // a download: the page stays where it is
  link.click();
}});
const runImportFile = $('run-import-file');
$('run-import').addEventListener('click', () => runImportFile.click());
runImportFile.addEventListener('change', async () => {{
  const file = runImportFile.files[0];
  if (!file) return;
  runInfo.textContent = `Importing ${{file.name}}…`;
  try {{
    const response = await fetch('/runs/import', {{
      method: 'POST', headers: {{'Content-Type': 'application/octet-stream'}}, body: file}});
    if (!response.ok) {{
      runInfo.textContent = `Import failed: ${{await response.text()}}`;
    }} else {{
      const report = await response.json();
      await refreshRuns(report.imported[0] || report.skipped[0]);
      runInfo.textContent = report.imported.length
        ? `Imported ${{report.imported.length}} run(s): pick it, then Load run or Replay run`
        : `Already in this console: ${{report.skipped.join(', ')}}`;
    }}
  }} catch (error) {{
    runInfo.textContent = `Import failed: ${{error}}`;
  }}
  runImportFile.value = '';
}});
"""
