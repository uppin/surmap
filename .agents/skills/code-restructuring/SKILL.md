---
name: code-restructuring
description: Restructure code without writing any of it by hand — split an oversized file into modules, extract a method, move a symbol, rename across a codebase. Plans the split in its own Refactor changeset, then executes a reviewable JSONL plan of named refactoring intents with `restructure`, which drives TypeScript's own language service, rust-analyzer and rope. Use whenever a change is a pure restructure rather than new behaviour.
---

# Code Restructuring

Restructuring by retyping code is slow, unreviewable, and risks silent behaviour changes. TypeScript,
Rust and Python all ship correct refactoring engines — the language service, rust-analyzer and rope;
this skill reaches them.

**The rule that shapes everything here: you never write the moved or extracted code.** You write a
plan of *intents*. `surmap` resolves each intent through the language's own engine,
which produces every character of the result.

A restructure claims to preserve behaviour. That claim is only ever a **comparison between two
states**, so steps 1 and 7 — a green baseline before, the same green after — are not ceremony. Without
the "before" you have nothing to compare the "after" against, and cannot tell your split from
breakage that was already there.

Both the plan and that comparison live in a **changeset** (step 4) — `Type: Refactor`, no PRD. It is
what a reviewer reads instead of a thousand-line diff, and it is what tells `/wrap-context-docs` the
narrow thing to do at the end: a changelog entry always, dev-doc edits only where the move made the
documentation false.

## Workflow row

`/code-restructuring` follows the step contract in `.agents/skills/pr-lifecycle/SKILL.md`.
It owns both rows of the restructure preset and runs them in order, closing each before it starts the
next:

| Row | Steps here | Result on ✅ |
|---|---|---|
| **Plan** — restructure changeset, recorded baseline, `plan.jsonl` | 0–6 | the baseline counts and the commit holding the changeset and `plan.jsonl` (`312/312 green, 41 ops @ abc1234`) |
| **Restructure** — apply the plan, baseline still green | 7–8 | baseline vs after and the apply commit (`312 → 312 green @ def5678`) |

**Row TODOs** — each row seeds its own:

- Plan: executor built (0) · green baseline recorded (1) · code issues read (1.5) · dead code removed
  (2) · seams proven (3–3.5) · changeset written, with its doc hits as Wrap-row TODOs (4) · snapshot
  taken and `plan.jsonl` committed (5–6)
- Restructure: dry run clean, plan applied (7) · baseline still green, visibility report reviewed (7) ·
  resolved code issues and the spent plan deleted, changeset closed (8)

Run as a feature changeset's *Restructure Prerequisite* (`/green` step 0.5), it is part of that
changeset's Green row and closes no row of its own.

The choices this skill puts to the developer — the dead code to delete (step 2), the caller-churn
option and the outliers (steps 3–4), the hand-edited unused imports (step 7) — are made by the row
and recorded in `## Decisions & Trade-offs` as well as the summary. Halts, beyond the skill's: a red
baseline outside the known-red carve-out (step 1), a known-red test that went green (step 1), a
split the vocabulary cannot express (*When this skill is the wrong tool*), a baseline that does not
hold after the apply (step 7).

## Workflow

### 0. Build the executor and find the binary

```bash
uv run mypy
common/code-restructuring/target/release/restructure --help
```

Five plan commands: `apply`, `status`, `check`, `anchors`, `verify`. Three of them exist to be used
*before* and *after* an apply, and the workflow below says where. **The first command in a checkout
starts a background `restructure serve` for that repo** (one instance per git toplevel); later
commands reuse it, engines warm. Use `restructure daemon status` to see root, pid, idle time, and
in-flight count; `restructure daemon stop` ends the instance. Pass `--no-daemon` for an in-process run
with no socket.

What the instance means for a session:

- **It exits on its own** after 15 idle minutes (`RESTRUCTURE_IDLE_TIMEOUT=30m` before the command
  that spawns it changes that; a running instance keeps the timeout it started with), or when its
  checkout is deleted.
- **A rebuilt binary replaces it.** The instance is tied to the binary's fingerprint, so the first
  command after `uv run mypy` stops the old instance and starts a new
  one — expect one cold index after every rebuild.
- **One instance per worktree.** Each checkout gets its own instance and its own engines, so N parallel
  worktrees hold N rust-analyzers. Run `restructure daemon stop` in a worktree before removing it: the
  instance and its engines run inside it, and a worktree removal that checks for live processes
  refuses while they do.
- **Its log is the first thing to read when a run stalls**:
  `$TMPDIR/restructure-runtime-$(id -u)/<key>.log` (`restructure daemon status` prints the socket; the
  log sits beside it). It records each request's start and end, engine starts and exits, and why the
  instance stopped. `RESTRUCTURE_TRACE=1` adds whether a command reused, replaced or spawned it.

For an explicit server, use `restructure serve --socket <path>` and pass `--socket` on client
commands; `restructure daemon ping --socket <path>` checks that it answers. A named socket that does
not answer is an error — never fall back to in-process execution.

**Python needs its environment built, and the package's `do:build` is what builds it.** The Python backend spawns
a sidecar holding a rope project, in the venv `surmap` provisions for this package —
`do:build` ends by importing rope, which is what syncs it. A run that reaches a `.py` file without it
says so and names the command; nothing else in the plan is affected.

**`restructure` is not on `bin`** — only `restructure-sidecar` is, and that is the ts-morph half, not
the CLI. There is no global `restructure` to invoke, and `uv run pytest -q` does not exist. The binary
is the build artefact at `common/code-restructuring/target/release/restructure`; every `restructure …`
below means that path.

### 1. Establish a green baseline — before touching anything

```bash
uv run mypy      # must succeed
uv run pytest -q
  2>&1 | tee /tmp/baseline.txt                  # record pass/fail counts per suite
```

Write the numbers down. They are the acceptance criteria for step 7.

- **A red baseline is a stop, not a warning.** If the build fails or tests already fail, halt the
  row ⛔ with the failures — the options are to fix it or to scope around it *first*. Restructuring on top of red makes both problems unattributable.
- **One carve-out: running as another changeset's restructure prerequisite.** When this restructure
  is the `## Prerequisites` → *Restructure Prerequisite* of a feature changeset that has already been
  through `/plan-red`, the branch is red **by design** — those failing tests are the plan. The
  baseline is then *green everywhere except that changeset's own planned red tests*: list them by
  name in `## Baseline` as known-red, and hold every other suite to green. **Anything red that is not
  on that list is still a stop.** After the apply, those tests must still fail **for the same reason**
  — a planned red test that goes green during a behaviour-preserving restructure was broken, or was
  never testing the feature. Halt ⛔ and name the test either way. See the
  [`deferred-work` skill](../deferred-work/SKILL.md).
- **In a fresh worktree, build first.** Unbuilt workspace dependencies surface as a wall of
  `TS2307: Cannot find module '@/…'` that reads exactly like a restructure that broke every
  import. A package-level build (`uv run mypy`) resolves them. If you see TS2307
  after a restructure, check whether the same
  errors exist at baseline before believing you caused them.
- **Nx in a worktree caches to the main checkout.** It derives the cache dir from the git *common*
  dir, so another session pruning that cache kills your build with `ENOENT … .nx/cache/terminalOutputs/…`
  — which reads as a broken build, not a cache miss. Isolate with
  `NX_CACHE_DIRECTORY="$PWD/.nx-worktree-cache" NX_DAEMON=false`, and delete the directory afterwards.
- **Redirect long background builds to a file, never through a pipe.** `uv run mypy … | tail -25` in
  the background buffers everything until exit, so the log looks empty and the run looks dead.
- **Cheap fallback.** When the full suite is too slow, baseline at least the target package's
  `type-check`, `uv run pytest -q`,
  and the test suites of the target package and its direct consumers — and say which you used.

### 1.5. Run code-issue analysis — before choosing seams

After the green baseline (step 1) and **before** dead-code removal (step 2), run the
[`analyze-code-issues`](../analyze-code-issues/SKILL.md) skill on the target package:

```bash
uv run mypy
uv run pytest -q
code-analysis issues --path <target-dir> \
  --coverage-dir <target-dir>/coverage-unit \
  --coverage-dir <target-dir>/coverage-it \
  --coverage-dir <target-dir>/coverage-e2e
```

Put the targeting note (highest CRAP, coverage gaps, hot files, large files, intersections) into the
restructure changeset. It informs which files to split first; it does not replace step 3's
structural analysis.

**Read the package's existing record first.** `/analyze-code-issues` persists one file per verified
finding next to the package's dev docs, so some of this restructure's targets are probably already
written down — with a hand-verification note and a *what would close it* section that names the seam:

```bash
ls <package-dir>/docs/code-issues/ 2>/dev/null
grep -rl 'Restructure:\*\* required' <package-dir>/docs/code-issues/ | \
  xargs grep -L 'Status:\*\* Resolved'
```

Every open issue marked `Restructure: required` in the target package is a candidate seam, and one
this restructure declines to touch is a decision to state in `## Decisions & Trade-offs` — not an
omission. List the issues this run intends to close in the changeset, and delete them at
step 8 (`git rm`, with the new measurement in the commit message). Findings the analysis turns up that this
restructure will *not* address get their own issue files, per
[`analyze-code-issues`](../analyze-code-issues/SKILL.md) step 7.

### 2. Remove dead code first — it is not yours to move

Dead code carried through a restructure costs review attention on both sides of the diff and can
force a deletion into a change that was supposed to preserve behaviour. Find it and remove it as a
**separate step, before the plan**.

```bash
uv run pytest -q
uv run pytest -q                      # @typescript-eslint/no-unused-vars, module scope
code-analysis dead-code --path <target-dir> \
  --coverage-dir <target-dir>/coverage-unit \
  --coverage-dir <target-dir>/coverage-it \
  --coverage-dir <target-dir>/coverage-e2e
```

The targeting note from step 1.5 already carries the three buckets. **Dead** is a delete candidate;
**missing-tests** is not — those symbols are referenced from production. **Test-only** needs a
consumer check (other packages, package `exports`) before deletion.

**These tools have a blind spot that matters here: they do not see class members.** Neither
`no-unused-vars` nor `noUnusedLocals` flags an unreachable `private` method — they only reach module
scope. So dead code accumulates precisely inside the oversized classes this skill gets pointed at,
and splitting one is what finally exposes it: members become module-scope functions, the linter wakes
up, and a lint failure lands in the middle of your restructure.

`code-analysis dead-code` closes that gap for TypeScript with a `this.X` / `Class.X` reachability
pass. Prefer its **Dead** list over re-deriving the graph by hand. Confirm each dead member with
find-references before deleting — TypeScript `private` is compile-time only, so members are still
enumerable at runtime via `Object.getOwnPropertyNames`; check for reflection over the class before
assuming a private member is unobservable.

- **Record before deleting.** Write what you found and why it is unreachable into the changeset
  (`## Decisions & Trade-offs`), and list each deletion under **Decided without review** — that is
  where the developer reviews it. A whole file to delete that the changeset does not name halts the
  row ⛔ instead.
- **Encode the deletion, do not hand-apply it.** If you are driving a codemod, give it an explicit
  drop list plus a guard that *refuses* to drop anything still referenced. A deletion that can only
  succeed when the reachability claim holds is worth far more than one you eyeballed.
- Whole-repo unused-export detection (`knip`, `ts-prune`) is not installed here. Adding it needs
  developer consent — see the dependency rule in README.md. Package-scoped unused detection with a
  coverage join lives in `code-analysis dead-code` instead.

### 3. Understand the shape before proposing a split

**First confirm the vocabulary can express the split.** Read the coverage table in
`references/plan-schema.md` before provisioning anything — building the executor for a target no
operation can reach is wasted setup, and the refusal is by design rather than a gap to work around.
A file that is one large class of statics is the common case; see *When this skill is the wrong tool*.

Then use the LSP tool and search — never read a whole file just to guess at seams.

```
LSP documentSymbol   <file>            # the outline: what is in here
LSP findReferences   <file> <line> <col>  # who depends on this symbol
LSP incomingCalls    <file> <line> <col>  # call graph, for cohesion
Grep                                    # import edges the LSP will not show
```

Cluster symbols by what they actually touch. A good split leaves few edges crossing the new
boundary; if every proposed module still imports the others, the seam is wrong.

**Map the callers before you fix a boundary — the count is a decision, not a byproduct.**
`findReferences` over each symbol you intend to move gives the set of files *outside* the target that
the restructure will rewrite. That set is the difference between a four-file diff and a forty-file one,
and which one you ship is a choice you make here or discover in review.

The three languages leave you in very different positions:

- **Rust can keep every caller still.** `extract_module`'s `reexport` leaves a `pub use` in the parent,
  so a caller that reached an item by module path resolves through the facade and is never touched, and
  an item reached through its *type* needs nothing at all. See the classification below.
- **TypeScript rewrites every importer, and the plan cannot stop it.** `reexport` is Rust-only;
  `move_symbol` has no facade field, and a re-export line in the old module is *code*, which a plan may
  not contain. For TypeScript the importer set **is** the diff.
- **Python rewrites every importer too, and a facade is expressible but not by a plan.** rope updates
  each `from x import y` as part of the move. `from .new_module import symbol` left in the old module
  would keep the old path alive, and unlike Rust's `pub use` there is no field that asks for one — it
  is an import statement, which is code, so it lands in the same place TypeScript's does: a line the
  developer adds after apply, outside the plan.

That leaves three honest options for a TypeScript or Python split. The Plan row picks one — option 2
when a cheaper seam exists, otherwise option 1 — and records the pick, the importer count and the
options it declined in `## Decisions & Trade-offs` and under **Decided without review**. Option 3 is
the developer's alone, taken by editing the changeset:

1. **Accept the churn.** Every importer ends up pointing at the module that owns the symbol — the
   honest structure, and a large review surface. State the size before you generate, not after.
2. **Pick a seam with fewer importers.** The same cohesion argument often reaches a boundary whose
   external reference count is far lower. Worth one pass before accepting option 1.
3. **Keep a facade, added outside the plan.** One export line in the old module, written by the
   developer after apply — not by you, and not in the plan. It keeps the old path alive as a second way
   to reach the symbol, so say whether it is the package's permanent public surface or scaffolding you
   intend to remove.

Either way the inventory goes in the changeset: the caller files by name, or their count and the
packages they sit in. A reviewer cannot infer blast radius from a table of modules.

**In Rust, classify every item before choosing a seam.** A free function, struct, enum, static, const
or type alias is reached by a **module path**, so moving it breaks every caller that wrote that path —
those need a `reexport` facade on `extract_module`, or callers dealt with first. An inherent associated
function or method is reached through its **type**, so the `impl` carrying it moves anywhere in the
crate with no caller changing.

**Persist the analysis as Initial Discovery** (§ *Start a changeset* step 3). Pick the changeset
slug at the start of this step, **before** the first LSP / Grep / Read, and write the companion as
soon as that first pass returns — a stop before step 4 must not lose the dump.

**"Free" means free of caller churn, and that is not the same as movable.** Moving a **whole** `impl`
is free and is usually the largest single win available. **Cutting an `impl` in half is not**: the new
module is written outside the `impl`, so a member left behind that calls one that moved references a
path which never resolved from where it sits, and the operation refuses. No ordering fixes that — an
`impl` body cannot hold a `mod`, so the sibling can be moved neither first nor second. The seam has to
grow to carry the whole `impl`, or be cut where nothing crosses.

Two things that look like the same problem and are not, both of which work: a whole `impl` moving while
the parent calls its methods, and a path-reached item moving while the parent still names it — the
import pass restores the binding for the second. Do not plan around either.

`restructure check --deep <plan>` answers all of this before an index is paid. Use it (step 3.5) rather
than reasoning about it — the answer has been wrong in both directions.

**A seam is one contiguous range of whole items, so file order is the seam plan.** `extract_module`
takes a single span; scattered-but-related items cannot be grouped until something has moved them
adjacent. If the cohesion argument reaches a cluster that is spread through the file, the honest first
step is a reordering pass, not a cleverer anchor.

**A facade the tool writes is checked; a facade you write by hand is not.** `reexport` is refused
outright when the module name is already taken, when a nested item's own module would not be
re-exported with it, and when a seam would separate an attribute's string path from the item it names.
Write the `pub use` yourself and none of that applies, so check it yourself:

- **`static`s the submodules need stay in the parent**, reached through `super::`.
- **A macro's string path resolves in the item's own scope.** `#[serde(default = "default_extend")]`
  must stay in the same module as the struct — no reference query reports that site, because serde
  builds the call out of the string's *contents* and the identifier it generates has no span to find.
- **Glob re-exports collide silently.** Two `pub use m::*;` lines that both bring in the same name are
  `E0659` at the use site, not at the re-export.

**Order seams so a definition is extracted before anything that references it.** Dependency order
beats line order, and they are different axes: build a small DAG of which seams define symbols other
seams use, sort it definitions-first, and use line order only to break ties. See the placeholder note
in `references/plan-schema.md` for what a violation costs.

**Verify after every seam, not only at the end.** The per-seam gate is the same gate as step 7 — type-check,
lint, build, and tests — not a compile check alone. A `cargo check` after each Rust seam is one
illustration of that gate, not a substitute for it; on a Python split the same step-7 list means
`uv run pytest -q` and `uv run pytest -q`
after every seam, because rope writes imports on one long unsorted line and skipping lint let
hundreds of findings accumulate across a real split.

**Match references semantically from the first query, not textually.** This bites the *analysis* for a
tool-driven split, not only a hand-written one. A regex over identifiers reported phantom edges between
nearly every pair of seams on one real file, because `new` matches every `Document::new()`,
`Vec::new()` and `HashMap::new()` in it. Require a qualifier — `(self|Self|manager|TypeName)\s*(\.|::)\s*name\b`
— or ask the compiler. Retrofitting this means redoing the analysis and every conclusion drawn from it.

**Build the referencer ➜ definer table before proposing a layout.** Group every reference to each
seam's items *by which seam the reference lives in*. A seam is movable only if nothing outside it
reaches its items from a scope the new module's path will not reach:

```
REFERENCER            ->  DEFINER                 verdict
global_context_api    ->  context_construction    OK — the import pass restores the binding
context_session       ->  context_compaction      BLOCKER — cross-seam inside one impl
```

**Count with the AST, not with grep.** A `grep -c` over member-looking lines overcounts badly
(nested functions, object literals, type members), and that number tends to leak into how you frame
the work to the developer. Get the outline from `documentSymbol` or the compiler API.

Check the **public surface** before you move it. Reflection over a class
(`Object.getOwnPropertyNames`, descriptor copying, `instanceof`, subclassing) constrains what the
result may be: class statics are non-enumerable own properties and object-literal properties are
not, so "class of statics → object literal" is a behaviour change wherever anything enumerates it.

### 3.5 Prove the seams resolve — before the layout is committed

Step 4 asks for a layout you will stand behind, and step 3 only established that the *vocabulary* can
express the split. Whether it **resolves** for those particular seams is a different question, and one
real split had its committed layout revised twice for want of asking it here.

Write a throwaway plan naming one seam per *class* of seam — one `impl`, one group of free functions,
one whose items another file reaches — and check it:

```bash
restructure check plan.jsonl            # lexical only: no language engine starts, answers in milliseconds
restructure check plan.jsonl --deep     # one index, no writes, every finding at once
```

`check` reports **all** findings rather than stopping at the first, which is the difference between
fixing a plan in one pass and in as many passes as it has problems. `--deep` resolves each operation
through the same path an apply takes, so a refusal it predicts is the refusal you would get.

Only then write the layout. A seam the check refuses is a seam the changeset should not propose.

**Let the tool compute the anchors too**, rather than arithmetic on doc-comment markers. The path is
relative to the crate you run it in:

```bash
# from the package root, for a file holding `pub fn min_of` and `pub fn max_of` next to each other
restructure anchors <file.rs> --items min_of,max_of
# -> {"kind":"range","file":"<file.rs>","range":{"start":{"line":45,"character":0},"end":{"line":53,"character":0}}}
```

It emits the `anchor` object to paste straight into a plan, covering the named items with their
attached doc comments and attributes, and refuses a name the file does not define or a run with
anything between its members.

**What it covers depends on what the language's extractions act on.** In Rust an anchor spans whole
top-level items, because `extract_module` groups them. Python has no such operation — `extract_method`
and `extract_variable` act on statements *inside* a function — so there it answers with the statement
run of one named function, its leading docstring excluded, and refuses more than one item:

```bash
restructure anchors src/shapes.py --items summarise_box
# -> {"kind":"range","file":"src/shapes.py","range":{"start":{"line":430,"character":0},"end":{"line":433,"character":0}}}
```

That range is a valid `extract_method` target as emitted; narrow it if you want less than the whole
body. "Start marker → next item's marker, minus two" fails in two ways that
both produce a plausible-looking range: adjacent seams destroy each other's markers, and a doc comment
is routinely a *prefix* of another one.

### 4. Write the changeset — the plan belongs in a document

A twenty-file split is not reviewable after the fact: by then the diff is thousands of lines and the
seams are already chosen. Everything steps 1–3 produced — the recorded baseline, the dead code found,
the layout — goes into a **Type: Refactor** changeset *before* you generate anything, started per
the `pr-lifecycle` skill § *Start a changeset* (`.agents/skills/pr-lifecycle/SKILL.md`) with the restructure
preset and Plan ⏳. Entered from `/pr-wrap` step 4 or `/green` step 0.5, there is no changeset of
its own and no rows to write.
State A is distilled from the companion — do not dump LSP / Grep traces into the changeset. `/wrap-context-docs`
deletes the companion with the changeset.

Put the layout on one screen: each target module, the symbols going into it, its projected size, and
every edge that crosses a boundary.

```
svg-map-generation.ts    7 symbols  ~350 lines   → text-layout-sessions
text-layout-sessions.ts      8 symbols  ~110 lines   → svg-map-generation
tests/test_geometry.py        1 symbol   ~780 lines   ⚠ over budget, single function
```

Beside it, the caller inventory from step 3 — what the restructure rewrites *outside* the target:

```
external importers   14 files across surmap, surmap
facade               none (TypeScript; reexport is Rust-only)
```

Three things this surfaces that nothing later will:

- **Outliers no reordering can fix.** A single 780-line function busts any line budget and no
  `move_symbol` shrinks it — splitting it is behaviour work. Record it in `## Decisions & Trade-offs`
  *before* you build around it, and list it under **Decided without review** — not as a caveat buried
  in your closing summary.
- **Seams that do not hold.** If most modules still import each other, the clustering is wrong, and
  saying so here costs a paragraph instead of a regeneration.
- **Caller churn nobody agreed to.** Fourteen importers rewritten is fourteen files a reviewer has to
  read past to reach the actual split. If that number is larger than the layout would suggest, weigh
  the three options from step 3 *now* and record why the one taken won — it is the cheapest moment to
  pick a different seam.

#### Derive the wrap-time doc work now, while you still hold both names

**A restructure's documentation debt is knowable at plan time**, and it is narrow. Behaviour did not
change, so nothing in the docs that describes behaviour became wrong. What a restructure falsifies is
documentation of *internal structure*: file and module maps, "add a new X here" instructions, listings
of a class's members, code examples carrying an import path, diagrams that name files. Find those by
grepping the package's docs for every path and symbol the plan touches:

```bash
grep -rn -e 'PointsHelper' -e 'src/surmap/geometry' \
  common-testing/session-test-helpers/README.md common-testing/session-test-helpers/AGENTS.md
```

Each hit the restructure makes untrue becomes one TODO under the Wrap row, named down to the file and
section — those TODOs are what `/wrap-context-docs` executes. A hit that stays true is **not** an item:
a facade that kept `PointsHelper.convertSvgToSession` reachable leaves the README example running exactly as
written. **Zero applicable hits is a complete answer**, leaving the changelog entry as the only item;
manufacturing doc churn to look thorough is worse than leaving accurate docs alone.

Run the grep here rather than at wrap time, because here is where you hold the old names *and* the new
ones. The executor never touches prose, so after apply the docs still say the old thing, and you would
be reverse-engineering which of it had ever been true.

### 5. Take the snapshot

Every anchor is written in the coordinates of the tree *as it is now*. Hash each file the plan
touches; the executor refuses to run if any has changed since.

```bash
shasum -a 256 <file>       # -> sha256:<digest> in the header line
```

### 6. Write the plan

One JSON object per line. Line 1 is the snapshot header; every later line is one operation, applied
in order. See `references/plan-schema.md` for the full vocabulary.

**Where it lives, and for how long.** Write it to `<package-dir>/restructure/<changeset-slug>/plan.jsonl`.
The plan is a **build input, not a deliverable**: the reviewable artefact is the changeset's layout and
the applied tree, and the plan's anchors are coordinates in a tree that stops existing the moment it is
applied. Commit it only to hand it to whoever applies it — a stack's pass-2 commit, read by that node's
`/green` — and **delete it in step 8**. It never reaches `master`, and it is never on a branch that is
ready for review.

```jsonl
{"v":2,"snapshot":{"src/shapes.ts":"sha256:ab12…"}}
{"op":"move_symbol","anchor":{"kind":"position","file":"src/shapes.ts","position":{"line":26,"character":16}},"to":"src/geometry.ts","with_private_deps":true}
{"op":"extract_method","anchor":{"kind":"range","file":"src/shapes.ts","range":{"start":{"line":411,"character":4},"end":{"line":467,"character":5}}},"name":"computeBounds"}
{"op":"organize_imports","anchor":{"kind":"file","file":"src/shapes.ts"}}
```

Use `restructure anchors` or the acceptance harness (`positionAt`, `rangeOf`, `fileAnchor`) to emit
coordinates in **0-based UTF-16** (LSP). Schema v1 and `symbol` anchors are refused.

**Anchors are in original snapshot coordinates throughout.** Do not adjust for earlier operations —
the executor's ledger does that, including in files an operation did not name.

Use a **position anchor** on the declaration for rename/move/inline operations. Use a **range anchor**
for extractions. Use a **file anchor** for whole-file import passes and `move_file`.

**Resolve a range anchor's extent structurally, never by arithmetic on the next item's marker.**
"Start marker → next item's marker, minus 2" fails in two ways that both produce a plausible-looking
range: adjacent seams destroy each other's markers, so extracting the second erases where the first
ended; and a doc comment is routinely a *prefix* of another one (`/// Get page dimensions with
optional MediaBox and CropBox` inside `… CropBox from context`), so the marker matches the wrong line.
Match braces or indentation forward from a unique start anchor instead — that depends on nothing but
the seam itself.

**Splitting a file into its own directory: ask for both steps at once.** `extract_module` takes
`to_file: true`, which groups the items and gives the module its file in one operation, never naming
the intermediate `mod` keyword. Prefer it — every plan re-indexes the parts of the crate it changed, and
on a fresh instance (first command in the checkout, or after a rebuild) the first plan pays the whole
cold index; this is what makes a real split cost two plans instead of four.

Without it the split is two phases and the second runs bottom-up: phase 1 groups items into inline
`mod` blocks with `extract_module`; phase 2 gives each one its own file with `extract_module_to_file`,
one operation per module, **last module first**, because working upward keeps every un-processed anchor
at coordinates that have not moved yet.

**A file shaped as one big `impl` plus thin free-function wrappers needs staging, and the order is not
obvious.** The wrappers reference the `impl`'s methods, so:

| Plan | Operations |
|---|---|
| 1 | `extract_module` with `to_file: true` over the **free-function** seams (with `reexport: "glob"`) |
| 2 | `extract_module` with `to_file: true` over the **`impl`** seams |

Plan 1 is what unlocks plan 2: once the wrappers are real files their calls are *cross-file*, which a
single-file assist never rewrites. That dependency is real, not an artefact of plan counting — it is
why this is two plans and not one. Re-hash the file and re-derive every anchor against the tree plan 1
left, and run `uv run pytest -q:rust` after **each** plan rather than only at the end.

### 7. Dry run, apply, then prove the baseline still holds

```bash
restructure apply plan.jsonl --dry-run   # resolves every operation, writes nothing
restructure apply plan.jsonl
```

The dry run rehearses the **whole** plan, not just its first operation: each operation's edits are
folded into an in-memory overlay as well as into the coordinate ledger, so operation *N+1* resolves
against the text its predecessors would have written. Nothing reaches disk and no journal is written.

**Indexing is paid once per serve instance, and you can watch it.** The first Rust operation on that
instance waits for rust-analyzer to load the crate graph and prints the server's own progress as
`indexing:` lines; every later request on the same instance reuses that warm server and waits only for
it to catch up with the edits. A request that
gives up says so as *indexing*, names how long it waited and where the server had got to, and points
at `--indexing-budget <seconds>`. **That is a slow or loaded machine, not a defect in the plan** —
raise the budget or re-run. (A message reading `plan is malformed: rust-analyzer never finished
loading the crate graph` is from an older build; rebuild the executor.)

If it stops partway:

```bash
restructure status plan.jsonl            # completed / in_flight / pending / failed
restructure apply plan.jsonl --resume
```

If it **stalls** rather than stops, nothing waits forever: an engine silent for 120s is killed and
the request fails naming it, and a client that hears nothing — not even the server's heartbeat — for
60s gives up and prints the instance log tail. Read that log, then `restructure daemon status`
(`in_flight`, `idle`). Recover with `restructure daemon stop` and re-run, or `--no-daemon` to take the
instance out of the picture. Never kill `restructure` or a language server by pattern — another
worktree's instance matches the same pattern.

Then re-run every gate from step 1 and **compare against the recorded numbers**:

```bash
uv run pytest -q
uv run ruff check src tests                            # TypeScript only — see below; Python has `ruff` instead
uv run mypy              # must still succeed
uv run pytest -q
```

- **A crate can fail `uv run pytest -q` before and after any change.** In `stereo-ingest`,
  `--all-features` enables the `coverage` feature, whose `#![feature(coverage_attribute)]` is `E0554`
  on stable — so that failure is not yours, and `uv run pytest -q:rust` is the compile gate to use. Check
  whether a lint failure exists at baseline before believing you caused it.
- **There is no Rust equivalent of `uv run ruff check src tests`.** These crates carry no `rustfmt.toml` and are not
  rustfmt-formatted, so running rustfmt restyles code well beyond the move and destroys the one thing
  that made the diff reviewable. If relocated bodies came out inconsistently indented, fix it with a
  whitespace-only dedent, which keeps every moved line byte-identical.

#### Review the visibility report, then diff the moved lines

Two checks, and they are not interchangeable — **run both**.

**Visibility is an output of every extraction, not an implementation detail.** rust-analyzer rewrites
a relocated item to `pub(crate)`, and one real split widened **56 items** that way, six of them struct
fields whose privacy was the enforcement of an invariant:

```rust
pub(crate) document: Document,  // private - use execute_mutation for modifications
```

The comment now contradicts the code, and an invariant the compiler used to enforce is prose. So:

- Read the `visibility:` lines `restructure` prints for each operation and **account for every one**.
- Prefer seams that keep a private helper with its only caller. Cutting between the two is what forces
  the widening.
- Fix the doc comments the widening made false, in this PR (step 8).

**Then diff every moved line against `HEAD`, normalised.** Strip `pub(crate)` and whitespace and
set-compare the moved lines against the original: on the split above that reduced the whole restructure
to **11 differing lines**, all of them one requalification. It is a seconds-long, near-total proof that
behaviour held, and it should close every restructure.

Run it **alongside** the visibility review, never instead of it. Normalising `pub(crate)` away is
exactly what hides the 56 widenings — each check is blind to precisely what the other reports.

**Then close with the statement diff, which is blind to something both of the others miss.**

```bash
restructure verify --against HEAD
```

It compares every line that carries behaviour — excluding `use`, `mod` and bare wrappers, and stripping
the indentation a relocation always changes — as multisets across the whole crate. What it catches that
nothing else can is **trivia attached to no item**: rust-analyzer relocates a comment along with the
item it belongs to, and a comment belonging to nothing is simply not carried. The compiler cannot see
it, the suite cannot see it, and the moved-line diff cannot see it either, because those lines moved
nowhere. On one real split two such comments went missing and only this surfaced them.

Three checks for Rust, each blind to what the others report. Run all three. **For Python there are
two:** the visibility review and the moved-line diff still apply where extractions widen visibility;
`restructure verify --against` does not — it filters `use`/`mod`/bare wrappers and every fixture in
`verify.rs` is Rust. Run `uv run pytest -q` and
`uv run pytest -q` instead of treating verify as the third check.

**Expect two tails, and budget for them.**

- **Unused imports.** Moving code out leaves the parent importing what the moved code needed. The
  hollowed-out case — `use std::sync::{};` — is dropped for you; the rest is not, because there is no
  Rust `organize_imports` and a plan cannot delete. It is a hand edit outside the plan. **Make it as
  its own visible change** — imports only — and list it under **Decided without review**.
- **A relocated `impl` member comes out `pub(crate)` and stays there.** It is reported on stdout and on
  the journal entry, but not undone — narrowing it back would be `E0624` for a private method with a
  sibling-module caller. Account for it, and fix any doc comment it made false.

- **Not finished until build and tests are back to baseline.** "Type-check passes" is not the bar; a
  restructure that compiles and fails a test has changed behaviour.
- **Report the comparison, not an impression.** State baseline vs after. A test failing both before
  and after is pre-existing — say that explicitly rather than letting it read as your regression.
- **Attribute a failure before claiming it is unrelated.** Run the single file in isolation, re-run
  the full suite, and where it is cheap, swap the original file back and run again. A load-sensitive
  race can pass alone and fail in a 29-file suite; only the comparison tells you which you have.
- **Check the callers were rewritten the way you intended, not merely legally.** The compiler proves
  every importer still resolves; it says nothing about *what* they now import. Diff the importer set
  against the step-4 inventory: a file you did not expect means the seam caught more than you planned,
  and an importer now reaching past a facade into a deep path is a structure regression that compiles
  perfectly.
- **New lint errors are a finding, not noise.** They are usually step 2's blind spot surfacing —
  dead code that became visible. Go back to step 2 rather than silencing the rule.

### 8. Close the changeset, then wrap it

Write the after-numbers into the changeset beside the baseline, **delete the code issues this run
resolved** — `git rm` each `<package-dir>/docs/code-issues/` file the changeset named, with the new
measurement in the commit message — tick the Restructure row's TODOs, and record what
the run actually did — a seam refused, a facade added, a member the vocabulary could not reach, and
**every visibility widening the run reported**, with the doc comments it falsified now corrected. The
applied tree is allowed to differ from the step-4 proposal, so **re-check the Wrap row's TODOs against
what landed, not against what you proposed.**

**Delete the spent plan in the same commit.** `git rm -r <package-dir>/restructure/<changeset-slug>/`
(the plan, and the directory with it), and clear the run state (`rm -rf .restructure/` — gitignored,
but a journal left behind translates the *next* plan's coordinates a second time). Record in the
changeset's `## Plan` section the operation count and the commit that applied it — not the path, which
no longer exists. Confirm nothing is left:

```bash
git ls-files '*/restructure/*/plan.jsonl'    # must print nothing
```

Close the Restructure row ✅ with the comparison and commit it with the apply. The wrap is the
changeset's Wrap row: its `/wrap-context-docs` runs at the moment the PR is set ready for review — not
while it is a draft, not after merge. For a restructure it executes a deliberately small wrap:

- **The changelog entry, always.** A new release-note file in each affected package's
  `docs/architecture.md` — or the package README's history where the package has no `docs/` — naming what
  moved, stating that behaviour is unchanged, and carrying the baseline-vs-after numbers that back the
  claim. This is the audit trail, and for most restructures it is the whole wrap.
- **Dev docs only where the restructure made them false**, per the Wrap row's TODOs, rewritten to State
  B: the new layout stated plainly, with no "moved from" and no "previously".
- **Nothing else.** `/wrap-context-docs` otherwise merges a changeset's State B across the package
  docs; here most of State B *is* State A. Rewriting architecture prose that is still accurate is churn
  a reviewer has to read and cannot verify against anything.
- **No PRD and no feature-doc changelog under `docs/<area>/`.** Those describe behaviour, which did not
  change. The exception is a package whose product *is* its structure — a public API surface, a
  restructuring tool — where the surface moving is itself the user-visible change.


## Rules

- **The changeset comes before the plan.** The layout is the reviewable artefact; the JSONL is its
  mechanical consequence. Proposing a split only in chat leaves nothing for the next session, and
  nothing for `/wrap-context-docs` to act on.
- **No PRD, and no acceptance tests.** A behaviour-preserving change has nothing new to accept — its
  acceptance criterion is the baseline recorded in step 1. A test written to accept a restructure is
  testing code that was already there.
- **Never put code in a plan.** No `text`, `code`, or `content` field; the parser rejects them. If an
  operation seems to need a snippet, the vocabulary is wrong for what you are trying to do — say so
  rather than working around it.
- **Never declare a new file.** There is no `create_file`. Files come into existence because
  `move_symbol` named a target that did not exist, or `extract_module_to_file` ran.
- **Commit each row's work with its row update, and nothing else.** The Plan row commits the
  changeset, its initial-discovery companion and `plan.jsonl` (step 2's dead-code removal in its own
  commit before them); the Restructure row commits the apply, the deleted plan and the resolved
  code-issue records. Relevant paths only, never `--no-verify`, never amend. The executor stages
  moves with `git mv`, so check `git diff --cached --stat` before each commit: if you `git mv` files
  into place before the plan runs, **any later commit silently absorbs those renames** — a commit
  meant for one package can land a second package's tree alongside it with no warning.
- **An unsupported operation is a hard error, by design.** Not every operation exists in every
  language — see the coverage table in `references/plan-schema.md` before planning against Rust.
- **Delete the code-issue records this run resolved** (`git rm`, new measurement in the commit message) — and file
  new ones for what it declined to touch. See the `deferred-work` skill.
- **A plan does not outlive its apply.** It lives at `<package-dir>/restructure/<changeset-slug>/plan.jsonl`
  only until `restructure apply` has run and the baseline is green again; step 8 deletes it. A
  `plan.jsonl` on a branch that is ready for review, or on `master`, is a leftover — `/pr-wrap` and
  `/wrap-context-docs` refuse to ready a PR that still has one.
- **Verify with the compiler and the suite, not by reading the diff.** `tsc --noEmit` / `cargo check`
  proves it still type-checks; only a package build plus a test run at baseline proves behaviour held.

## Python: forms rope can miss, and what to grep for

`check --deep` predicts *refusals*; it says nothing about a move that exits 0 having done half the
job. After every cross-package `move_file`, `restructure` prints `note: unrewritten reference in …`
for files that still mention the moved module — a **warning, not a refusal**. Read those lines; two of
the forms below cannot be rewritten by any engine, so refusing would block moves that are correct as
far as the tool can act.

| Form | rope | Grep starting point |
|---|---|---|
| `from pkg.mod import name` | rewritten everywhere | — |
| `from pkg import mod` at module level | rewritten | — |
| `from pkg import mod` deferred in a function | **skipped** | `from <pkg> import <mod>` inside a `def` |
| `from . import mod` deferred | call site rewritten, import left stale | `from \. import <mod>` inside a `def` |
| `"pkg.mod.attr"` in a string | unreachable | `"<pkg>.<mod>` |
| `Path(__file__).parents[N]` | unreachable | no textual grep — see [python-restructuring-blind-spots](../../../docs/architecture.md) |

Eleven of fourteen hand fixes in one real split were the same shape: *a module reached through its
package rather than by its own dotted path.*

## When this skill is the wrong tool

- The change adds or alters behaviour — restructuring tools preserve it by construction.
- The target language is none of TypeScript, Rust or Python.
- The edit is a one-line rename in a single file, where the plan costs more than the edit.
- **The vocabulary cannot express the split.** No operation moves a class member, and `extract_class`
  refuses statics, `super`, `#private` reads, `this` writes, accessors, and decorated members by name
  — so a file that is one large class of statics is out of reach *by design*. Halt the Plan row ⛔,
  name what the tool can reach instead, and offer the alternatives below, rather than quietly falling
  back to retyping.

Describe the alternative accurately when you offer it. "I would retype it by hand" and "I would
generate it from the AST and diff it against the original" are different risks, and a developer
choosing between them deserves the real one.

## If you restructure by hand anyway

Sometimes the developer weighs the tradeoff and chooses the unreachable target regardless. That is
their call. The engine guarantee is then gone, so replace it with evidence:

- **Derive the moved text mechanically** from the AST — never retype it. A codemod that slices each
  member verbatim and rewrites only the declaration header and `this.` qualifiers keeps every other
  character byte-identical, and stays re-runnable from the pristine original.
- **Analysis is checker-based from line one** — the same rule as step 3, and it matters more here.
  Build a `ts.createProgram` and ask `checker.getSymbolAtLocation`; never match identifiers textually. Textual matching cannot tell a
  top-level import from a local that shadows it (`const SessionRecording = (await import('session fixtures')).default`)
  nor a type-property named `join` from `path.join` — and it gets both wrong silently, so the damage
  shows up much later as unused-import lint errors and missing imports. Retrofitting the checker means
  redoing the analysis and regenerating everything; starting with it costs about twenty lines.
- **Verify the span you actually copied.** A fidelity diff that compares `getStart()`→`getEnd()` is
  blind to leading and trailing trivia — exactly where extraction bugs live. `getEnd()` stops at the
  semicolon, so a trailing `// comment` falls into the *next* declaration's leading trivia and silently
  re-documents the wrong symbol. If the extraction reasons about comments, the diff must too: compare
  leading JSDoc per symbol, and reconcile total comment counts before and after.
- **Diff the result against the original programmatically.** Compare each moved body
  whitespace-insensitively, and compare string and template-literal contents *exactly* — reindentation
  inside a template literal is a real behaviour change that a whitespace-insensitive diff hides.
- **Give the codemod a dry run, and require idempotence.** Snapshot the tree, regenerate from the
  pristine original, and diff: if a second run does not reproduce it byte for byte, something was
  hand-patched and the mechanical guarantee is gone. Make this a standing invariant, not a late check.
- **A fix you re-apply after every run belongs in the generator.** Hand-patching the same defect on
  four consecutive runs is the signal you are compensating for a generator bug instead of fixing it.
- Then run step 7 in full. Hand work raises the bar on verification; it does not lower it.
