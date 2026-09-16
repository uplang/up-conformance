[![actions](https://github.com/uplang/up-conformance/actions/workflows/actions.yml/badge.svg)](https://github.com/uplang/up-conformance/actions/workflows/actions.yml) [![docs](https://github.com/uplang/up-conformance/actions/workflows/docs.yml/badge.svg)](https://github.com/uplang/up-conformance/actions/workflows/docs.yml) [![validate](https://github.com/uplang/up-conformance/actions/workflows/validate.yml/badge.svg)](https://github.com/uplang/up-conformance/actions/workflows/validate.yml)

# UP conformance — the language-neutral conformance corpus

This repository is the **single, language-neutral conformance corpus** for the [UP language](https://uplang.org). Every UP implementation — the reference parsers ([`up.go`](https://github.com/uplang/up.go), [`up.py`](https://github.com/uplang/up.py), [`up.js`](https://github.com/uplang/up.js), [`up.rust`](https://github.com/uplang/up.rust), [`up.c`](https://github.com/uplang/up.c), [`up.java`](https://github.com/uplang/up.java)) and any third-party one — proves conformance by running this corpus and matching every expected outcome. The corpus is part of the **specification**, not of any single implementation, and it MUST stay aligned with [the spec at uplang.org](https://uplang.org/specification/).

## Layout

Every case is a directory holding an input and its expected outcome. Cases are partitioned by the **rung** that defines their behavior:

```text
rungs/
  0/cases/<name>/
    input.up          # the UP source to parse
    expect.json       # the expected outcome (see schema/expect.schema.json)
  1/cases/<name>/...
  2/cases/<name>/...
  ...
```

A [rung](https://uplang.org/rungs/) is a self-contained layer of the language. **Rung 0** is the minimal core; each higher rung adds one capability (Rung 1 escapes + inline forms, Rung 2 annotation syntax, Rung 3 multiline strings, Rung 4 tables, Rung 5 documents + pragmas, Rung 6 error recovery, Rung 7 templating, Rung 8 schema validation). Partitioning by rung is what lets an implementation **know which tests it is expected to pass**: a parser that implements through Rung N runs `rungs/0` … `rungs/N` and ignores higher rungs until it implements them.

## The expectation format

Each [`expect.json`](schema/expect.schema.json) records one of two outcomes (full schema: [`schema/expect.schema.json`](schema/expect.schema.json)):

```json
{ "expect": "parse", "model": { "name": "Ada" } }
{ "expect": "parse", "model": { "name": "“value”" }, "lint": ["W_SMART_QUOTES"] }
{ "expect": "error", "code": "E_MISSING_VALUE" }
```

- **`expect`** — `"parse"` (a conforming parser MUST accept the input) or `"error"` (it MUST reject it).
- **`model`** (parse) — the data model the parse MUST yield, as an **order-significant** JSON projection: a string value is a JSON string, a block is a JSON object, a list is a JSON array. **Object key order is significant** — blocks are insertion-ordered. **Every scalar value is a string** ([spec §4](https://uplang.org/specification/#4-data-model)); there is no type inference or coercion. A **multiline string** (Rung 3) carrying an info string projects as `{"$info": "<text>", "$value": "<string>"}` (absent info ⇒ the bare string). An **annotated member** (Rung 2) projects as a **tagged value object** `{"$annotation": {"name": …, "args": …?}, "$value": …}` — `$annotation.name` is the captured identifier, `$annotation.args` (present only when the use site wrote `(…)`) is the raw argument text, and `$value` is the member's ordinary value projection. A member with no annotation is its bare value projection, unwrapped; **list items are never annotated**. Annotations are captured **opaquely** — recognized and round-tripped, never interpreted (`port!int 8080` yields the string `"8080"`, not the number `8080`).
- **`lint`** (parse) — lint warning codes (`W_*`) a linter SHOULD emit. Absent means none.
- **`code`** (error) — the stable error code (`E_*`) the parser MUST report. **Match by code, never by message text.**

Two flags qualify an expectation:

- **`rung_exact: true`** — the expectation holds **only** for a parser implementing exactly that rung, not cumulatively. It marks "feature not yet supported" rejections — e.g. `E_INLINE_UNSUPPORTED` at Rung 0, whose input _becomes valid_ at Rung 1. A runner for rung N MUST **skip** a `rung_exact` case that belongs to a lower rung.
- **`provisional: true`** — the expectation is **not yet spec-final**: it reflects the draft suite for a rung whose specification (notably the data model and error codes) is still being written, so it uses `error_contains` (a message substring) instead of a stable `code`. Provisional cases are **excluded from the conformance verdict**; they record intent and light up once their rung is specified.

## Writing a runner (any language)

A conformance runner for an implementation claiming **Rung N** does, for each case under `rungs/0` … `rungs/N`:

1. Skip the case if `provisional` is true, or if `rung_exact` is true and the case's rung is below N.
2. Read `input.up` and parse it with the implementation.
3. If `expect` is `"error"`: assert the parse failed with `code` (compare the implementation's error code, not its message).
4. If `expect` is `"parse"`: assert the parse succeeded, then assert its data model equals `model` under the order-significant projection above, and that its emitted lint codes equal `lint` (as a set).

That contract is all an implementation needs; nothing here is Go- or Python-specific. The reference Go runner is [`up.go`](https://github.com/uplang/up.go)'s permanent `conformance_test.go`: it runs this corpus from a sibling checkout (`../up-conformance`, the standard org-tree layout) and skips loudly when the corpus is absent. It also asserts the corpus exercises **every** spec `E_*` and `W_*` code, so the corpus and the spec cannot drift apart silently.

## The typing corpus

Beside the rung (syntax) corpus, [`typing/cases/`](typing/cases/) holds the conformance suite for the **typing layer** ([spec §9](https://uplang.org/specification/#9-the-typing-layer-up-typing)) — the opt-in `typed(document, registry, mode)` processor that resolves each member's opaque annotation to a type semantic and validates its exact lexical form. Each case is the same `input.up` + `expect.json` shape (full schema: [`schema/typing.expect.schema.json`](schema/typing.expect.schema.json)), with its own contract:

- **`expect`** — `"typed"` (typing MUST succeed) or `"error"` (it MUST fail).
- **`model`** (typed) — the typed data model as an order-significant JSON projection over the parse projection: an untyped member keeps its parse projection; a member whose annotation resolved to a type projects as `{"$type": "<name>", "$value": "<canonical form>"}` — `$type` is the resolved type name (a bare `!int` resolves in the sealed core namespace, `int` ≡ `up.type.int`) and `$value` is the value's canonical form as a string. Typing never mutates the parse model; scalars stay strings.
- **`mode`** — `"open"` runs the case in open mode, where unresolved _extension_ names pass through untyped (core-namespace failures still error). Absent means the default strict mode.
- **`code`** (error) — the stable `T_*` typing error code (`T_UNRESOLVED`, `T_MISMATCH`, `T_KIND`, `T_BAD_ARGS`, `T_SCALE`) — a code space disjoint from the parse `E_*`/`W_*` spaces. Match by code, never by message text.
- **`line`** (error) — the 1-based input line the error MUST be reported at; under distribution over a list, a failing element reports its own line.

A typing runner does, for each case under `typing/cases/`: parse `input.up`, run the typing processor in the case's mode with the ten standard core types registered, then assert the typed projection equals `model` (or the failure carries `code` and, when present, `line`). The reference runners are each binding's permanent typing conformance suite (e.g. [`up.go`](https://github.com/uplang/up.go)'s `typing_conformance_test.go`), run from the same sibling checkout.

## Spec alignment & status

- **Rungs 0–3** are **spec-aligned today** — the string data model matches [spec §4](https://uplang.org/specification/#4-data-model) and the error codes match [§6](https://uplang.org/specification/#6-errors). Rung 2 adds the [annotation **syntax** foundation](https://uplang.org/rungs/2-annotations/) (`key!name`, `key!name(args)`): annotations are captured **opaquely** (the tagged-value projection above), with the single new error code `E_BAD_ANNOTATION`. The annotation _system_ — types, validation, definitions, composition — is a later rung and stays out of the corpus until specified.
- **Rungs 4+** are **provisional**: the spec for tables, documents, and templating is still being written. Their `model` projections are **not settled** and will be reconciled when each rung is specified. Do not treat a provisional expectation as authoritative.

See [`manifest.json`](manifest.json) for the generated index of every case and its status.
