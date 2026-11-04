# Agent tool outputs saved to file, with read_file and grep_files

**Date:** 2026-11-04
**Feature:** Survey agent runtime

- **Saved outputs.** Every tool gained an optional `output: {to_file: true}` argument. A
  completed result was saved as pretty-printed JSON when the call asked for it, or when its
  inline JSON was over 16 KiB (`SURMAP_AGENT_MAX_INLINE_OUTPUT_BYTES`). The model then read a
  reference (path, bytes, lines, reason, preview) instead of the whole result. Detached-job
  notices were rendered the same way. Each conversation saved under
  `<cache>/agent-tool-outputs/<conversation>/` and each subagent in a folder inside it; a random
  suffix on each file name kept a restored conversation's job ids from overwriting older files.
- **File tools.** `read_file` (numbered line windows) and `grep_files` (Python `re` over
  `os.walk`, in a worker thread, with glob, ignore-case and a match limit). Neither needed a
  ripgrep binary or native wheel. Both read only the conversation's output folder plus
  `SURMAP_AGENT_READ_ROOTS`. Every path was resolved, symlinks included, and had to stay inside
  a root, and grep never followed a symlinked folder. Binary files were refused or skipped, each
  result was kept under the inline limit, and the two tools never saved their own results.
- **Considered.** The official `ripgrep` wheel has no build for Modal's `debian_slim` (glibc
  2.36), and `python-ripgrep` is an immature native binding whose walker would sit outside the
  path guard; plain `re` was chosen.
- **Code.** `surmap.agent.runtime.outputs.ToolOutputs`, `contracts.resolve_output`,
  `BoundTool.content` / `saves_large_results`, `JobRunner(outputs=…)`, `surmap.agent.files`,
  `AgentServerConfig.tool_outputs_dir` / `max_inline_output_bytes` / `read_roots`,
  `server.app.tool_outputs`.
- **Tests.** pytest: 13 saved-output, 18 file-tool, 4 server config/wiring.

Docs: [docs/agent.md](../../agent.md) (*The `output` argument*, *Saved outputs and file tools*).
