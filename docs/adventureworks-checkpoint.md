# AdventureWorks checkpoint

## Implemented

- Microsoft fictional HR data converted to 290 employees and 16 departments.
- Deterministic conversion, pinned source URLs/hashes, output hash and MIT notice.
- Departments become teams. Source BusinessEntityID becomes `aw-emp-N`.
- Current assignment means exactly one department-history row with empty EndDate.
  This is the source export's snapshot, not staffing on today's date.
- Encoded hierarchyid is not decoded: manager IDs remain null. Skills remain empty
  and explicitly unknown. Sensitive-shaped fields, even fictional ones, are omitted.
- `quality-hold.json`: original synthetic incident, nine source documents, two
  stages, sourced batch/assembly/order links and ten acceptance cases.
- `search_sources`: parameterized, bounded FalkorDB search available to both engine
  agents. Context comes from the engine, never the model. No HTTP/auth changes.

## Data provenance and reproduction

Microsoft source: https://github.com/microsoft/sql-server-samples/tree/e5d7bb90ca0b695ac14f61458047bfb5a498459e/samples/databases/adventure-works/oltp-install-script

`fixtures/adventureworks/provenance.json` records checksums, revision, rules and
omissions. `MICROSOFT-LICENSE.txt` retains the upstream notice. Original raw bulk
exports remain outside the repo. Only the allowlisted derived directory is committed.
Employee.csv is tab-delimited with 16 fields; Person.csv uses `+|` and `&|` record
terminators. Parsing ordinary comma-separated CSV would silently misread this data.

```sh
.venv/bin/python scripts/fetch_adventureworks.py --output /tmp/relaymind-aw-source
.venv/bin/python scripts/convert_adventureworks.py --source /tmp/relaymind-aw-source --manifest /tmp/relaymind-aw-source/manifest.json --output /tmp/relaymind-aw-converted
```

These commands do not write to FalkorDB. Compare generated directory/provenance
against the committed files. `employees.xlsx` is a plain-text seven-column import
workbook derived from directory.json; use CompanyDirectory metadata from that JSON
when calling `read_employee_xlsx`. Blank managers/skills do not assert none exist.

## Incident and acceptance

This incident is authored for RelayMind; none of its notices, orders or holds are
historical Microsoft records. Before change: held B101 reaches O101 and shipped
O102 through assemblies. After change: B102 additionally reaches O103. O104 has a
different traced batch. O105 has no trace and must be marked unknown, never safe.
There are only 10 unreserved replacement units against O101's requirement of 12.
Engineering approval is model-specific; v1 checklist and rejected alternatives
remain history. Named incident owners are unapproved; teams alone are assigned.

The acceptance file is an offline oracle. It is not loaded into the model's context
as an answer. Production batch/order graph contracts and staged seeding belong to
Claude; this fixture's graph vocabulary is a proposed integration contract.
Before-change seeding must exclude `aw-src-hold-v2`, including from source search.
After-change seeding must add approved supersession, not merely insert source text.

## Search behavior and limitations

The query matches all whitespace-separated lowercase terms in source ID/title/text,
orders deterministically by ID and fetches limit+1 (maximum 11) to report truncation.
It is substring search, not BM25, embeddings, semantic classification or a relevance
ranking. A two-second database query timeout bounds work. Use a few distinctive
terms and fetch the full source before citing it. This scan suits demo-sized graphs;
indexed retrieval and a relevance benchmark are later work.

`not_found` means this successful query returned no matching authorized Source
records. It does not mean all company knowledge was searched. Missing directory,
unknown permissions, DB failure and missing project authorization are not empty
search results. No lookup in another company is performed to confirm absence.
The UI may use a consistent sentence template; the status must come from query rows.

Sources are not approved truth. Current decisions and deterministic reviewer gates
remain authoritative. New handoffs snapshot cited evidence-view hashes and source
IDs; review rejects changed views before model acceptance. The hash describes the
authorized text shown to the agent, not a complete typed business-record version.
Older handoffs have no manifest. A search-hit hash does not grant an approval or
prove a historical decision is current.

## Isolated retrieval evaluation (17 October)

`backend/tests/test_retrieval_evaluation.py` runs the actual `search_sources`
function against isolated, stage-specific synthetic Source rows. It uses the
fixture's acceptance oracle only in test assertions; those answers are never sent
to an agent. Authored query sequences recovered every expected supporting source
for AW-01 through AW-09 (9/9), while AW-10 returned a genuine empty scoped result.
The 23 checks also cover exact and mixed-case IDs, multiple hits and truncation,
database error, denied identity, historical/current notice visibility, and an
instruction embedded in source text. The instruction test verifies that tools
return it as data; it does not prove a live model will ignore it.

Before-change storage excludes `aw-src-hold-v2`; after-change storage includes it.
The opt-in real FalkorDB test now seeds those stages separately and checks approved
decision supersession, but it was not run on this checkout because Docker Desktop's
engine was unavailable. The isolated evaluation measures source recall for these
authored queries, not answer accuracy, relevance ranking or typed manufacturing
retrieval.

## Remaining path to the end-to-end checkpoint

1. Claude reviews identity/company and batch/order/ticket contracts. Add AdventureWorks
   explicitly through server membership; do not rename Cedar's graph or demo identity.
2. Claude implements staged manufacturing storage/queries, approved holds and procedure.
   Source IDs should retain this fixture's provenance; revise fixtures and contracts together.
3. Codex extends discovery to typed entities and directory snapshots after those
   contracts land, then adds their authoritative versions/current-state to the
   evidence manifest on review/resume.
4. Claude wires profile login, imports, tickets and human approvals. Codex verifies
   cross-profile isolation and search/no-result/error behavior through those interfaces.
5. Run a fresh-session real-model manufacturing flow, change the hold mid-run, reject
   the stale plan, regenerate affected orders, review and approve a permitted task action.

No claim of completed AdventureWorks login, live incident ingestion or model run is
made by this checkpoint. Existing fixed demo access policy is still in place.
