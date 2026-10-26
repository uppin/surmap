# Plan schema (v2)

A plan is JSONL. Line 1 is the snapshot header; every later line is one operation, applied in order.

```jsonl
{"v":2,"snapshot":{"<path>":"sha256:<digest>", …}}
{"op":"<name>","anchor":{…}, …}
```

Schema **v1** and **`symbol` anchors are refused**. Regenerate plans with `restructure anchors` or the
harness helpers `positionAt` / `rangeOf` / `fileAnchor`.

The plan is a **command log** and is never rewritten. Execution appends to `.restructure/journal.jsonl`
(the event log) and checkpoints the coordinate ledger to `.restructure/ledger.json`.

## Anchors (LSP coordinates)

All anchors use **0-based** `line` and **0-based** `character` counted in **UTF-16 code units** — the
same units as LSP and editor selections. Ranges are **end-exclusive**.

```jsonc
{"kind":"position","file":"src/a.ts","position":{"line":11,"character":9}}
{"kind":"range","file":"src/a.ts","range":{"start":{"line":20,"character":0},"end":{"line":31,"character":0}}}
{"kind":"file","file":"src/a.ts"}   // whole-file ops (imports, moves)
```

Coordinates are expressed in the **snapshot** tree, before any operation runs; the ledger translates
them as earlier operations land.

Malformed coordinates (line past EOF, character past EOL, inside a surrogate pair) are refused with
`file:line:character`. `restructure check` lists every malformed coordinate in one run.

## Operations

| `op` | Anchor | Fields | TypeScript | Rust | Python |
|---|---|---|---|---|---|
| `extract_method` | range | `name`, `variant` = `inner` \| `module` | ✅ | ✅ | ✅ |
| `extract_variable` | range | `name` | ✅ | ✅ | ✅ |
| `extract_type` | range | `name`, `variant` = `alias` \| `interface` | ✅ | — | — |
| `extract_class` | range over whole members | `name`, `to` | ⚠️ | — | — |
| `move_symbol` | position | `to`, `with_private_deps` | ✅ | — | ✅ |
| `move_file` | file | `to` | ✅ | — | ✅ |
| `rename_symbol` | position or range | `name` | ✅ | ✅ | ✅ |
| `extract_module` | range over a selection of items | `name`, `reexport` = `glob` \| `named` \| `none`, `to_file` | — | ✅ | — |
| `extract_module_to_file` | position at the `mod` keyword | — | — | ✅ | — |
| `extract_trait` | range at the `impl` keyword | `name` | — | ✅ | — |
| `inline_method` | position | — | — | ✅ | ✅ |
| `organize_imports` | file | — | ✅ | — | ✅ |
| `add_missing_imports` | file | — | ✅ | — | ✅ |

The engines are TypeScript's own language service, rust-analyzer, and — for Python — `rope` through
**pylsp** with the **pylsp-rope** plugin (extract, rename, inline) plus the rope **sidecar** (moves
and imports).

Every operation but one is backed by a real assist in the engine that claims it. Where a cell is
empty the engine has no equivalent, and the executor refuses the operation rather than approximating
it. The ⚠️ marks the exception — see **`extract_class` is hand-written** below.

`variant` selects between actions the engine offers for the same operation. Omitting it keeps the
behaviour an operation had before the field existed (`inner`, `alias`), and a name the operation does
not define is refused rather than ignored.

### Notes that matter when planning

- **What `move_symbol` does with a private-only dependency is the engine's decision, and the two
  engines differ.** TypeScript always carries it along with the symbol, and refuses
  `with_private_deps: false` rather than silently ignoring it. **rope does neither**: it leaves the
  helper where it is and authors an import back to it, so a moved `scale_box` that called a private
  `_clamp` arrives as `from shapes import _clamp` plus the function. Neither is a fallback for the
  other, and the field cannot make one behave like the other — what it can do is tell you which you
  are getting.
- **Rust has no whole-symbol move.** To split a Rust file, group the items with `extract_module` and
  then run `extract_module_to_file`, whose anchor is a caret on the `mod` keyword.
- **`to_file: true` does both steps in one operation, and is the way to do this.** `extract_module`
  groups the items and gives the module its file without ever naming the intermediate `mod` keyword, so
  the constraint below does not arise. The parent's edit is measured against what was on disk, so one
  journal entry describes the whole operation and the ledger still sees a single edit. A plan written
  before the field existed produces a byte-identical tree, and an operation that cannot honour it is
  refused rather than having it ignored. The four-plan recipe becomes two plans, and two rounds of
  re-indexing instead of four.
- **Without `to_file`, those two steps need two plans, not two lines of one plan** — but *only* those
  two. The `mod` keyword the second step aims at is text no original coordinate maps to, so the ledger
  correctly reports the anchor as inside removed text. Apply the first plan, then start the second as a
  restructure of its own: clear `.restructure/`, re-hash the file, and write the anchors against the
  tree the first plan left. Run state describes one plan's edits, and a journal left in place would
  translate the new plan's coordinates a second time.

  Other Rust operations **do** compose in one plan. They once did not, for a reason that was nothing
  to do with anchors: the backend reported each operation as a single edit spanning from its first
  changed line to its last, so an extraction that rewrote two distant places swallowed every
  untouched line between them. It now reports one hunk per changed region, so the lines between stay
  addressable and a plan can carry as many seams as you can order correctly.
- **`extract_module` restores the imports its own assist loses, and refuses when it cannot.** The
  items move out of the scope of the file's `use` declarations, so the backend asks rust-analyzer for
  an import at each name left unresolved. Where the server offers several paths for one name, the
  file's existing imports decide; where they do not settle it, the operation refuses and names the
  candidates rather than guessing.
- **`extract_module` refuses when another file references what would move — unless you ask for a
  facade.** The module is reached by a different path than the items are now and rust-analyzer
  rewrites no reference it did not move, so a caller elsewhere would only surface at compile time.
  The refusal names each item and the files referencing it.

  `reexport` is the cheap way past it, and it touches no caller: `"glob"` leaves one
  `pub use <name>::*;` in the parent, so `crate::core::context_manager::create_shading_pdf` goes on
  resolving through the re-export. `"named"` leaves one grouped `use` per visibility tier, covering
  only the items something outside the new module reaches. Absent, or `"none"`, is the refusal above.
  A parent `foo.rs` may own a `foo/` directory in Rust 2018, so the facade survives a later
  `extract_module_to_file` with no rename to `mod.rs`.

  **A `named` facade that names nothing is reported, not refused.** A seam whose items are all reached
  only from inside it legitimately needs no facade, so the operation succeeds and says so on stdout as
  a `note:` line — a facade asked for and absent is otherwise visible only in the diff.

  **A `named` facade refuses an item whose own module it would not carry.** A nested item is reached
  *through* the module holding it, so re-exporting that module keeps `parent::nested::buried`
  resolving and naming the item as well would publish `parent::buried`, a path no caller used. Where
  something outside reaches the nested item but nothing reaches its module, no line would keep the old
  path resolving and the operation refuses — `reexport: glob` covers that case, because a glob
  re-exports the module too.

  The refusal only ever concerned items reached by a **module path** — free functions, structs, enums,
  statics, consts, type aliases. An inherent associated function or method is reached through its
  *type*, so the `impl` carrying it can move to any module in the crate with no caller anywhere
  changing. **Moving a whole `impl` is free of caller churn**, and is the cheapest restructuring move
  Rust has.

  **Free of callers is not free of seams, and the difference decides whether a plan runs.** Three
  geometries look alike and only one blocks — measured, not assumed:

  | Geometry | Outcome |
  |---|---|
  | A whole `impl` moves; the parent calls its methods | **Succeeds.** A method is reached through its type, so there is nothing to rewrite |
  | A path-reached item moves; the parent still names it | **Succeeds.** The assist rewrites the reference and the import pass restores the binding — which is why an in-file reference "costs nothing" |
  | **One member is lifted out of an `impl` while a sibling in that same `impl` calls it** | **Refused.** The new module is written *outside* the impl, so the rewritten path never resolved from in there, and rust-analyzer does not rename what does not resolve |

  Only the third is a blocker, and no ordering fixes it: an `impl` body cannot hold a `mod`, so the
  sibling can be moved neither out of the way first nor after. Grow the seam to carry the whole `impl`,
  or cut it where nothing crosses. The refusal fires before the assist runs and names the member and
  the lines its siblings reach it from.

- **`extract_module` reports every visibility it had to widen, and preserves the rest — except inside
  an `impl`, where it reports but does not restore.** The assist rewrites what it relocates to
  `pub(crate)`. For a **path-reached** item, what nothing outside the new module reaches is put back as
  it was written, so a seam that carries a private helper along with its only caller keeps the helper
  private. Prefer such seams: cutting between a helper and its only caller is what forces a widening.

  A relocated **`impl` member** is different, and deliberately so. It is reached through its type, so
  no module path names it and the survey that decides restoration rightly does not descend into an
  `impl` — which means the member stays `pub(crate)`. That widening is now *named* on stdout and
  recorded on the journal entry, but it is not undone: narrowing it back would be `E0624` for a private
  method with a sibling-module caller, which is safe today precisely because the item stays widened.
  So **expect a private method to come out `pub(crate)` and stay there**, and account for it as a real
  consequence of the seam rather than looking for a way to prevent it.
- **`extract_module` refuses a module name the parent has already taken.** The name is the one piece
  of text an extraction invents, and the only name a facade can collide on — every other name in the
  module was already unique, and an extraction only moves names *out*. A `mod report {` written beside
  an existing `pub mod report;` is `E0428` and the assist writes it without complaint, so the run would
  report success against a crate that no longer compiles. The check is lexical: it reads `mod`
  declarations and `use` bindings outside the seam, and a declaration *inside* the seam does not count
  because it moves into the new module and vacates the name. A module already extracted to its own file
  is out of reach of a lexical read; only same-file bindings are seen.
- **An extraction refuses a seam that would separate an attribute's string path from the item it
  names.** `#[serde(default = "default_extend")]` reaches an item the way a call does, but
  `textDocument/references` on the helper does not report that site — serde builds the call from the
  string's *contents*, so the identifier it generates has no span in the source. The stranded check is
  therefore blind to it, the visibility pass narrows the helper back to private, and the failure lands
  inside generated code. Only an unqualified name is weighed: a qualified one resolves the same from
  either side of the seam. `doc` attributes are excluded — their strings are prose.
- **`extract_module_to_file` names the new file itself**, after the module. There is no `to` field.
- **`extract_module`'s selection must cover whole items including their doc comments.** A doc
  comment belongs to the item below it, so a selection starting at `pub fn` leaves that item out.
- **`inline_method` rewrites callers in every file, and removes the definition only once it has
  rewritten them all.** A call sitting inside a macro invocation — `format!("{}", scaled(x))` — is
  one rust-analyzer will not rewrite, and the inline then leaves both that caller and the definition
  in place.
- **`extract_method` with `variant: "module"` is refused on a range that reads `this`.** TypeScript
  omits the module scope for such a range rather than reporting it inapplicable, so the operation
  refuses instead of quietly extracting a method. In Python the same variant is rope's `global_`, and
  a variant the operation does not define is refused rather than treated as one that it does.
- **Python's `move_file` either renames a module or moves it to another package, and not both at
  once.** rope has one assist for each — a module rename, and a move into a destination folder — so a
  `to` that changes the folder *and* the basename is two intents and is refused as such. Either
  single-axis move rewrites every importer.
- **A Python `move_symbol` may name a destination that does not exist**, and the file comes into
  being as a consequence of the move, exactly as it does in TypeScript. rope itself refuses an absent
  destination, so the backend materialises an empty one for the length of the operation and removes
  it again; the `create` it reports is what `apply` acts on. Nothing is left behind if the operation
  refuses.
- **A Python `move_file` may name a destination package that does not exist**, symmetrically.
  `_MaterialisedDestinationFolder` creates the folder and an `__init__.py` for the length of the
  operation, reports the `create` entries, and removes them again before returning — the same
  materialise-then-report pattern as `move_symbol`'s `_MaterialisedDestination`.
- **After a cross-package `move_file`, unrewritten references are reported as notes, not refusals.**
  The sidecar scans for the import forms in the table below and prints any file the edit did not
  rewrite. `check --deep` cannot substitute for this — it predicts refusals, not under-rewriting.

  | Form | rope |
  |---|---|
  | `from pkg.mod import name` | rewritten everywhere |
  | `from pkg import mod` at module level | rewritten |
  | `from pkg import mod` deferred in a function | **skipped** |
  | `from . import mod` deferred | call site rewritten, import left stale |
  | `"pkg.mod.attr"` in a string | unreachable by any engine |
  | `Path(__file__).parents[N]` | unreachable by any engine |
- **A Python `add_missing_imports` refuses a name it cannot settle.** Where several modules in the
  project provide the name, the file's own imports decide — a `Tag` in a file that already reaches
  into `alpha` means that one. Where they do not settle it, the operation names every candidate
  rather than choosing, because choosing here runs and means something else. rope composes and places
  the import itself, merging it into a declaration the file already had where one fits.
- **Extraction placeholders are renamed by the engine**, not by string replacement — and the rename
  is *verified* rather than assumed. It has a blind spot: rust-analyzer rewrites references to the
  items it moved as `modname::Item`, and a reference already sitting inside another extracted module
  cannot be renamed, because from that scope `modname::Item` never resolved and rust-analyzer does not
  rename an unresolved path. That once produced nine such sites and fifteen compile errors from an
  operation that reported success. The operation now refuses when the placeholder occurs more often
  than it did before the assist ran, naming the lines.

  The refusal names **which of two causes** it hit, because they want opposite advice. A leftover
  inside an already-extracted *module* is an ordering mistake, and the rule that avoids it entirely is:
  **extract a definition before anything that references it.** Line order and dependency order are
  different axes and dependency order wins — build a small DAG of which seams define symbols other
  seams use, topologically sort it definitions-first, and use line order only to break ties.

  A leftover inside an **`impl`** is not an ordering mistake and reordering cannot fix it. One real
  split was reordered in full and produced byte-identical refusals at identical offsets, because the
  reference was merely *in the file* rather than inside an already-extracted module. Grow the seam
  instead. The check that predicts this before any index is paid is `restructure check`.

### `extract_class` is hand-written

Neither engine has an extract-class or a move-member refactor, so this one operation is performed by
the sidecar itself. The plan still carries only intent and the parser still rejects code-bearing
fields; what is relaxed is that the result is authored by this package rather than by TypeScript.

- The anchor must cover **whole class members**. A partially covered member is refused.
- The state the moved members read is bound through a constructor parameter, and the original class
  is left holding an instance and delegating to it.
- Members whose meaning would change on the way out are **refused by name**: a `super` call, a
  `#private` read, a write through `this`, a call to a member staying behind, an accessor, a static,
  a decorated member, an overload, a destructured parameter.
- Prefer the engine-backed route where it applies: for `this`-free members, `extract_method` with
  `variant: "module"` followed by `move_symbol` yields a module of free functions instead of a class
  of statics, and every character of it comes from TypeScript.
- Indentation of relocated bodies lands wrong; `uv run ruff check src tests` corrects it. There is no Rust
  equivalent of that step — a crate without a `rustfmt.toml` is usually not rustfmt-formatted, and
  running rustfmt would restyle code beyond the move and destroy the diff's reviewability. Rust
  extractions have not been observed to need it.

## What a plan may not contain

`create_file`, `insert_text`, `delete_range`, or any `text` / `code` / `content` field. The parser
rejects all of them, `extract_class` included. This is the guarantee that no hand-written code
enters a restructure *through a plan* — distinct from, and stronger than, the claim that every
character of a result comes from an engine, which `extract_class` alone does not meet.
