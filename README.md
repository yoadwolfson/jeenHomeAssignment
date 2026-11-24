# docindex: document indexing and semantic search

`docindex` indexes PDF and DOCX files and lets you search them in plain
language. It extracts clean text from a file, splits it into chunks with one of
three strategies, embeds each chunk with Gemini (`gemini-embedding-001`, 1536
dimensions) and stores the chunks in PostgreSQL with pgvector. Search returns
the 5 closest chunks.

## 1. Installation

You need Python 3.14 and Docker.

```bash
python -m venv .venv && source .venv/bin/activate   # PowerShell: .venv\Scripts\Activate.ps1
pip install -r requirements.txt                     # requirements-dev.txt adds pytest, mypy, fpdf2, pillow
docker compose up -d                                # pgvector/pgvector:pg17
cp .env.example .env                                # then fill in GEMINI_API_KEY
```

Postgres is published on host port **5433**. A locally installed PostgreSQL
usually owns 5432 and answers `localhost` first, which shows up as a confusing
`password authentication failed`. You don't need to run a migration: the first
run creates the extension, the table and the index.

## 2. Environment variables

| Variable | Value |
|---|---|
| `GEMINI_API_KEY` | a Gemini API key (the free tier is enough) |
| `POSTGRES_URL` | `postgresql://postgres:postgres@localhost:5433/docindex` |

- Both are read from `.env`, which is git-ignored.
- A variable already set in the shell wins over `.env`.
- A missing variable gives exit 2 and the hint to copy `.env.example`.
- Neither value is ever printed.

## 3. Usage

```bash
python index_documents.py --file samples/urban_beekeeping.pdf --strategy paragraph
python search.py --query "how do I stop bees swarming"
```

| `--strategy` | Rule |
|---|---|
| `fixed` | chunks of at most 1,000 characters, cut at whitespace, each with up to 200 characters of overlap with the previous chunk |
| `sentence` | whole sentences (pysbd, English) packed up to 1,000 characters; a chunk may cross a paragraph break |
| `paragraph` | one chunk per paragraph; only a paragraph over 1,000 characters is split, by sentence packing |

- **Re-indexing:** indexing a file again with the same strategy *replaces* its
  chunks. A different strategy *adds* a second set beside the first, so you can
  compare them.
- **Search** covers every file and strategy that has been indexed.
- **Output:** results go to stdout and progress logs to stderr. `--verbose` adds
  DEBUG logs and tracebacks.

## 4. Design

**Layout and seams.** The services (`IndexingService`, `SearchService`) depend
on four protocols: `TextExtractor`, `Chunker`, `Embedder` and `ChunkRepository`.
Only `ServiceFactory` (`docindex/bootstrap.py`) creates the concrete classes, so
the tests can swap in a fake embedder and a fake repository while the real
extraction and chunking code runs. The entry scripts are 3 lines each: they call
the shared `run_cli` in `docindex/cli.py`.

**Clean text.** Each extractor only reads the file. One shared `TextCleaner`
applies the same rules to PDF and DOCX text, and paragraphs come out separated
by exactly `\n\n`. The rules, in order:

1. Apply NFKC.
2. Drop control and zero-width characters.
3. Collapse whitespace.
4. Drop page-number lines.
5. Join wrapped lines.
6. Rejoin words hyphenated at a line end (`pro-`/`ductivity` becomes `productivity`).

pypdf must run in *layout* mode, because plain mode drops the vertical gaps,
which are a PDF's only paragraph signal. A page break always ends a paragraph.

**Chunk sizes are in characters, not tokens.** Gemini has no local tokenizer, and
`count_tokens` costs one API call per chunk. 1,000 characters is about 250
tokens, well under the 2,048-token limit. pysbd runs on one paragraph at a time,
so a heading without a final period never fuses into the next sentence.

**Pipeline order.** The steps run in this order:

- Indexing: extract + chunk → connect + ensure schema → embed everything → replace chunks.
- Search: connect + ensure schema → embed the query → search.

A bad document fails before any network call. The database is checked *before*
Gemini, so a stopped database costs no quota. Everything is embedded before
anything is written, so an embedding failure leaves the stored chunks untouched.
Replacing chunks is one transaction (`DELETE` + `INSERT`), so a failed re-index
keeps the old chunks.

**Error model.** Every failure raises a domain exception, which carries its own
message and chains the library cause (`raise ... from`). `run_cli` prints exactly
one `Error: ...` line and looks up the exit code by exception class:

| Code | Meaning |
|---|---|
| 0 | success, including empty search results |
| 1 | unexpected error (`unexpected failure (run with --verbose for details)`) |
| 2 | bad CLI usage or missing configuration |
| 3 | document: not found, unsupported type, unreadable, or no extractable text |
| 4 | embedding: bad key, quota exhausted after retries, or service/network error |
| 5 | database: cannot connect, or operation failed (rolled back) |
| 130 | Ctrl+C |

Problems found while building it:

- **Unreadable vs no text.** A corrupt or encrypted file and an empty or scanned
  file need different fixes, so they are separate errors. pypdf and python-docx
  leak many exception types (`KeyError`, `zipfile`, `lxml` and more), so the
  catch is broad. It wraps *only* the library read, so a bug in our own code
  still surfaces as exit 1.
- **A bad Gemini key returns 400, not 401.** Checked live: the response is
  `400 INVALID_ARGUMENT` with reason `API_KEY_INVALID`.
- **Gemini responses are validated.** A wrong vector count, a wrong dimension or
  a zero vector used to crash later as exit 1. It is now exit 4, raised before
  any write.
- **Library warnings broke the one-line rule.** pypdf and psycopg log their own
  WARNING lines, so those loggers are set to ERROR unless `--verbose` is on.
- **Docker Desktop on Windows swallows connections** to a stopped container
  instead of refusing them, and libpq waits forever by default. A 3 s connect
  timeout fixes this.
- **Windows piped output is cp1252**, which crashed on the `ﬁ` ligature, so both
  scripts force UTF-8.

**Retries.** The SDK has built-in retries, but they are off by default. We turn
them on with 8 attempts, exponential backoff and a 60 s cap, on 408, 429, 5xx
and network errors. The waits add up to at least 123 s, which outlasts a full
per-minute quota window. There is no hand-written sleep code. Vectors are
L2-normalised by us, because Gemini normalises only its full 3072-dimension
output.

**Secrets.** `Settings` masks the key and the password in its repr. Logs name
only the database host and database name. Error messages are our own text. A
malformed `POSTGRES_URL` is the one cause that is *not* chained, because libpq
echoes the whole URL in its error, password included. A test runs `--verbose`
on every outcome and asserts that no secret appears in the output.

## 5. Sample documents

The files in `samples/` are committed. To regenerate them, run
`python samples/generate_samples.py` (needs `requirements-dev.txt`).

| File | Tests |
|---|---|
| `urban_beekeeping.pdf` | PDF happy path: paragraph gaps, the `pro-`/`ductivity` rejoin, a `- N -` footer, a paragraph cut by the page break |
| `remote_work_policy.docx` | DOCX happy path: a heading, a soft line break, the `ﬁ` ligature, plus a table and a footer that must be excluded |
| `scanned_no_text.pdf` | an image-only page: no extractable text, with the OCR hint |
| `empty.docx` | an empty document: no extractable text |

## 6. Sample runs

These are real runs on a fresh volume (`docker compose down -v && docker
compose up -d`), in order. They were captured on Windows, which is why one path
prints with `\`. In PowerShell, use `$LASTEXITCODE` instead of `$?`.

```text
$ python search.py --query "how do I stop bees swarming"
INFO docindex.storage.postgres: Connected to PostgreSQL (host=localhost, database=docindex) and ensured the schema
No results found for "how do I stop bees swarming". Index a document first with index_documents.py.
$ echo $?
0

$ python index_documents.py --file samples/urban_beekeeping.pdf --strategy fixed
INFO docindex.services.indexing: Extracted 3541 characters from urban_beekeeping.pdf
INFO docindex.services.indexing: Split into 5 chunks with strategy 'fixed'
INFO docindex.storage.postgres: Connected to PostgreSQL (host=localhost, database=docindex) and ensured the schema
INFO docindex.embedding.gemini: Embedding batch 1/1 (5 chunks)
Indexed urban_beekeeping.pdf with strategy 'fixed': 5 chunks stored (replaced previous chunks for this file and strategy, if any).

$ python index_documents.py --file samples/urban_beekeeping.pdf --strategy sentence 2>/dev/null
Indexed urban_beekeeping.pdf with strategy 'sentence': 4 chunks stored (replaced previous chunks for this file and strategy, if any).

$ python index_documents.py --file samples/urban_beekeeping.pdf --strategy paragraph 2>/dev/null
Indexed urban_beekeeping.pdf with strategy 'paragraph': 11 chunks stored (replaced previous chunks for this file and strategy, if any).

$ python index_documents.py --file samples/remote_work_policy.docx --strategy paragraph 2>/dev/null
Indexed remote_work_policy.docx with strategy 'paragraph': 6 chunks stored (replaced previous chunks for this file and strategy, if any).

$ python index_documents.py --file samples/urban_beekeeping.pdf --strategy paragraph 2>/dev/null
Indexed urban_beekeeping.pdf with strategy 'paragraph': 11 chunks stored (replaced previous chunks for this file and strategy, if any).
```

**Searches** (expand each one for the full output):

- **"how do I stop bees swarming"**: the `paragraph` chunk is exactly the
  swarming paragraph and ranks first. Sentence packing split that topic across
  two chunks, so the `sentence` chunks rank lower. This shows paragraph chunks
  following topic boundaries.
- **"what equipment does the company provide"**: all 5 results come from the
  DOCX, and the table text is absent.
- **"quarterly revenue forecast"**: an off-topic query still returns 5 weak
  results, because there is no relevance threshold.

<details><summary><code>search.py --query "how do I stop bees swarming"</code></summary>

```text
$ python search.py --query "how do I stop bees swarming" 2>/dev/null
Results for "how do I stop bees swarming" (top 5):

[1] urban_beekeeping.pdf · paragraph · chunk 4
    Swarming is the natural way a colony reproduces. The old queen leaves with roughly half of the workers and settles on a branch or a lamp post while scouts search for a new home. In a city this frightens people, so urban keepers prevent swarms by giving the colony more space before it feels crowded, or by splitting it into two hives on purpose. A well timed split also replaces an ageing queen and gives the keeper a spare colony to fall back on if the original one fails over the winter.

[2] urban_beekeeping.pdf · sentence · chunk 1
    The old queen leaves with roughly half of the workers and settles on a branch or a lamp post while scouts search for a new home. In a city this frightens people, so urban keepers prevent swarms by giving the colony more space before it feels crowded, or by splitting it into two hives on purpose. A well timed split also replaces an ageing queen and gives the keeper a spare colony to fall back on if the original one fails over the winter. Varroa mites are the greatest threat to honey bee health worldwide. The mites feed on developing bees and spread viruses that deform wings and shorten lives. Most keepers count mites once a month by washing a sample of bees in alcohol or by counting the mites that fall onto a sticky board placed under the hive. When the count rises above a threshold the keeper treats the colony, ideally in late summer after the honey harvest and before the winter bees are raised.

[3] urban_beekeeping.pdf · fixed · chunk 1
    warn that the colony is preparing to swarm, and for signs of disease such as discoloured or sunken brood cappings.
    
    Swarming is the natural way a colony reproduces. The old queen leaves with roughly half of the workers and settles on a branch or a lamp post while scouts search for a new home. In a city this frightens people, so urban keepers prevent swarms by giving the colony more space before it feels crowded, or by splitting it into two hives on purpose. A well timed split also replaces an ageing queen and gives the keeper a spare colony to fall back on if the original one fails over the winter.
    
    Varroa mites are the greatest threat to honey bee health worldwide. The mites feed on developing bees and spread viruses that deform wings and shorten lives. Most keepers count mites once a month by washing a sample of bees in alcohol or by counting the mites that fall onto a sticky board placed under the hive. When the count rises above a threshold the keeper treats the colony, ideally in

[4] urban_beekeeping.pdf · sentence · chunk 0
    Urban Beekeeping: A Short Field Guide Keeping honey bees in a city is easier than most people expect. A single hive needs about one square metre of ground, a water source within a few hundred metres, and a neighbour who does not mind the occasional visitor on a flowering shrub. The most important decision is where the hive entrance faces. An entrance turned towards a wall or a tall hedge forces foragers to climb steeply as they leave, which keeps their flight path above head height and reduces the colony's overall productivity only slightly while avoiding almost every conflict with people walking past. Inspections should happen every seven to ten days during spring and early summer. During each inspection the keeper looks for eggs, which prove the queen is laying, for queen cells, which warn that the colony is preparing to swarm, and for signs of disease such as discoloured or sunken brood cappings. Swarming is the natural way a colony reproduces.

[5] urban_beekeeping.pdf · paragraph · chunk 3
    Inspections should happen every seven to ten days during spring and early summer. During each inspection the keeper looks for eggs, which prove the queen is laying, for queen cells, which warn that the colony is preparing to swarm, and for signs of disease such as discoloured or sunken brood cappings.
```
</details>

<details><summary><code>search.py --query "what equipment does the company provide"</code></summary>

```text
$ python search.py --query "what equipment does the company provide" 2>/dev/null
Results for "what equipment does the company provide" (top 5):

[1] remote_work_policy.docx · paragraph · chunk 3
    The company provides a laptop, a headset and a monthly allowance towards internet costs. Employees are responsible for a safe workspace and for keeping company devices locked when unattended. The finance team reimburses approved purchases within thirty days.

[2] remote_work_policy.docx · paragraph · chunk 1
    This policy explains how employees may work away from the office, what equipment the company provides, and how teams stay in touch across time zones.

[3] remote_work_policy.docx · paragraph · chunk 5
    Questions about this policy go to the people team. Requests for exceptions go to your manager first.

[4] remote_work_policy.docx · paragraph · chunk 0
    Remote Work Policy

[5] remote_work_policy.docx · paragraph · chunk 2
    Eligibility depends on the role rather than the person. Roles that need physical presence, such as laboratory work or reception, are not eligible. Every other role may be performed remotely for up to four days a week with the manager’s agreement.
```
</details>

<details><summary><code>search.py --query "quarterly revenue forecast"</code></summary>

```text
$ python search.py --query "quarterly revenue forecast" 2>/dev/null
Results for "quarterly revenue forecast" (top 5):

[1] remote_work_policy.docx · paragraph · chunk 5
    Questions about this policy go to the people team. Requests for exceptions go to your manager first.

[2] remote_work_policy.docx · paragraph · chunk 3
    The company provides a laptop, a headset and a monthly allowance towards internet costs. Employees are responsible for a safe workspace and for keeping company devices locked when unattended. The finance team reimburses approved purchases within thirty days.

[3] urban_beekeeping.pdf · paragraph · chunk 8
    apiary to the next.

[4] remote_work_policy.docx · paragraph · chunk 4
    Core hours run from ten in the morning until three in the afternoon in the team’s home time zone. Outside core hours people may arrange their day freely, as long as meetings are announced at least one working day in advance.

[5] urban_beekeeping.pdf · sentence · chunk 0
    Urban Beekeeping: A Short Field Guide Keeping honey bees in a city is easier than most people expect. A single hive needs about one square metre of ground, a water source within a few hundred metres, and a neighbour who does not mind the occasional visitor on a flowering shrub. The most important decision is where the hive entrance faces. An entrance turned towards a wall or a tall hedge forces foragers to climb steeply as they leave, which keeps their flight path above head height and reduces the colony's overall productivity only slightly while avoiding almost every conflict with people walking past. Inspections should happen every seven to ten days during spring and early summer. During each inspection the keeper looks for eggs, which prove the queen is laying, for queen cells, which warn that the colony is preparing to swarm, and for signs of disease such as discoloured or sunken brood cappings. Swarming is the natural way a colony reproduces.
```
</details>

**Database rows.** There is one row group per file and split strategy (four in
all). The re-indexed `paragraph` group still has 11 rows from a single indexing
run, so the replace worked. Every vector has 1536 dimensions and unit length. A
double space in `text_start` is a flattened `\n\n` paragraph break.

```text
$ docker compose exec db psql -U postgres -d docindex -c "SELECT filename, split_strategy, count(*) AS chunks, count(DISTINCT created_at) AS runs FROM chunks GROUP BY 1, 2 ORDER BY 1, 2;"
        filename         | split_strategy | chunks | runs 
-------------------------+----------------+--------+------
 remote_work_policy.docx | paragraph      |      6 |    1
 urban_beekeeping.pdf    | fixed          |      5 |    1
 urban_beekeeping.pdf    | paragraph      |     11 |    1
 urban_beekeeping.pdf    | sentence       |      4 |    1
(4 rows)

$ docker compose exec db psql -U postgres -d docindex -c "SELECT id, filename, split_strategy, chunk_index, replace(left(chunk_text, 40), E'\n', ' ') AS text_start, vector_dims(embedding) AS dims, round(vector_norm(embedding)::numeric, 3) AS norm, created_at FROM chunks ORDER BY id LIMIT 5;"
 id |       filename       | split_strategy | chunk_index |                text_start                | dims | norm  |          created_at           
----+----------------------+----------------+-------------+------------------------------------------+------+-------+-------------------------------
  1 | urban_beekeeping.pdf | fixed          |           0 | Urban Beekeeping: A Short Field Guide  K | 1536 | 1.000 | 2026-11-24 16:02:54.418203+00
  2 | urban_beekeeping.pdf | fixed          |           1 | warn that the colony is preparing to swa | 1536 | 1.000 | 2026-11-24 16:02:54.418203+00
  3 | urban_beekeeping.pdf | fixed          |           2 | by washing a sample of bees in alcohol o | 1536 | 1.000 | 2026-11-24 16:02:54.418203+00
  4 | urban_beekeeping.pdf | fixed          |           3 | limit the number of colonies per garden  | 1536 | 1.000 | 2026-11-24 16:02:54.418203+00
  5 | urban_beekeeping.pdf | fixed          |           4 | colony nearby.  Winter is a quiet season | 1536 | 1.000 | 2026-11-24 16:02:54.418203+00
(5 rows)
```

**Error demos.** Each prints a single `Error:` line (the bad-key run also shows
its progress logs, which come before the Gemini call). The key override is inline, so
`.env` is untouched. In PowerShell, use `$env:GEMINI_API_KEY='invalid'; python
...; Remove-Item Env:GEMINI_API_KEY`.

```text
$ python index_documents.py --file samples/nope.pdf --strategy paragraph; echo $?
Error: File not found: samples\nope.pdf
3
$ python index_documents.py --file requirements.txt --strategy paragraph; echo $?
Error: Unsupported file type '.txt': only .pdf and .docx are supported
3
$ python index_documents.py --file samples/scanned_no_text.pdf --strategy paragraph; echo $?
Error: No extractable text in scanned_no_text.pdf (it may be a scanned image; OCR is not supported)
3
$ python index_documents.py --file samples/empty.docx --strategy paragraph; echo $?
Error: No extractable text in empty.docx
3
$ GEMINI_API_KEY=invalid python index_documents.py --file samples/remote_work_policy.docx --strategy paragraph; echo $?
INFO docindex.services.indexing: Extracted 1005 characters from remote_work_policy.docx
INFO docindex.services.indexing: Split into 6 chunks with strategy 'paragraph'
INFO docindex.storage.postgres: Connected to PostgreSQL (host=localhost, database=docindex) and ensured the schema
INFO docindex.embedding.gemini: Embedding batch 1/1 (6 chunks)
Error: Gemini rejected the API key: check GEMINI_API_KEY in .env
4
$ docker compose stop db
$ python search.py --query "how do I stop bees swarming"; echo $?
Error: Cannot connect to PostgreSQL: check POSTGRES_URL in .env and that the database is running
5
$ docker compose start db
```

Not demoed: an unreadable file (`echo garbage > fake.pdf`) and the quota error.
The tests cover both.

## 7. Assumptions & limitations

- **Testing:** the repository SQL and the real Gemini calls are verified
  manually, by the runs above, not by automated tests.
- **PDF paragraphs:**
  - Paragraphs are detected from vertical gaps, so an indent-only paragraph
    merges with the one above.
  - Multi-column pages interleave their columns.
  - The samples are synthetic (fpdf2), and other producers may space paragraphs
    differently.
  - A paragraph that spans a page break becomes two paragraphs (see
    `apiary to the next.` above).
- **Cleaning:**
  - Hyphen rejoining turns `well-`/`known` at a line end into `wellknown`.
  - Only page-number lines are dropped, so running headers are kept. A line that
    is only a number, such as `2024`, is dropped too.
- **Not indexed:**
  - DOCX tables, headers, footers, footnotes and text boxes are skipped.
  - There is no OCR.
  - `.doc` is not supported.
  - The file type comes from the extension only, so a DOCX renamed to `.pdf` is
    reported as *unreadable*.
  - An encrypted PDF gets the same message as a corrupt one.
- **Chunking:**
  - Sizes are approximate token limits, because they count characters (about 4
    per token).
  - Sentence detection is English only. pysbd also breaks at a single `\n`,
    which is safe only because clean text never has one inside a paragraph.
  - Short paragraphs and headings make weak embeddings.
  - A sentence over 1,000 characters is cut mid-sentence.
  - Sentence packing ignores topic boundaries.
  - Fixed-size overlap can make neighbouring results repeat text.
- **Storage:**
  - Files with the same basename in different folders overwrite each other's
    rows.
  - Every re-index embeds again, even an unchanged file.
  - The DB user must be allowed to run `CREATE EXTENSION vector`.
  - Concurrent indexing of the same file and strategy fails on the unique
    constraint.
  - Every connect failure gets one message; `--verbose` shows the cause.
  - A database slower than 3 s to connect counts as down.
- **Search:**
  - Results span every strategy, so the same text can come back once per
    strategy.
  - The score is computed but not shown.
  - There is no relevance threshold, so a search always returns up to 5 results.
  - Empty results exit 0.
- **Embedding (free tier: about 100 requests a minute, 30K tokens a minute, 1K
  requests a day):**
  - Large documents may be slow or hit the daily quota.
  - During 429 backoff the run prints nothing for up to about 2 minutes, because
    the SDK's retry logs stay quiet even under `--verbose`.
  - If a later batch fails, the earlier batches' embeddings are discarded.
- **Configuration:** a variable set to an empty string in the shell still wins
  over `.env`, and is then reported as missing.

## 8. Running tests

```bash
pip install -r requirements-dev.txt
python -m pytest   # 123 tests, no network or database, a few seconds
python -m mypy
```

The tests run against these seams:

- **The CLI:** the real extractors and chunkers on `samples/`, with a fake
  embedder and a fake repository. They check every message and exit code, the
  replace behaviour, that nothing is embedded when the database is down, that
  nothing is written when embedding fails, and that no secret appears under
  `--verbose`.
- **The chunkers:** crafted strings with small sizes.
- **The extractors:** the samples, plus bad files built in a temp directory.
- **The Gemini client boundary:** the SDK's real exception classes.
- **The real `PostgresChunkRepository`:** only `psycopg.connect` is swapped out.
