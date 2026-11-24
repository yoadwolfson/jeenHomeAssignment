# Glossary

**Clean text**: the normalised text of a whole document, made of paragraphs separated by a single blank line. It is what every chunking strategy splits.

**Paragraph**: one unit of clean text between blank lines. In a PDF a page break always ends a paragraph; in a DOCX each non-empty body paragraph is one paragraph.

**No extractable text**: a readable document whose clean text contains no letters or digits (e.g. a scanned PDF or an empty DOCX).

**Unreadable document**: a file with a supported extension that cannot be opened or parsed (corrupt, password-protected, or not really that file type). Distinct from *no extractable text*.

**Chunk**: one piece of a document's clean text that is embedded and stored as a single searchable row.
_Avoid_: segment, passage, split

**Split strategy**: the rule used to cut clean text into chunks: `fixed`, `sentence` or `paragraph`.
_Avoid_: chunking method, splitter mode

**Fixed-size strategy** (`fixed`): chunks of a set character length, cut at whitespace, each overlapping the previous one.

**Sentence strategy** (`sentence`): chunks made of whole sentences packed up to the maximum chunk size; may span paragraphs.

**Paragraph strategy** (`paragraph`): one chunk per paragraph; only a paragraph longer than the maximum chunk size is divided.

**Overlap**: the text a fixed-size chunk repeats from the end of the chunk before it, so content near a cut appears whole in at least one chunk. Only the fixed-size strategy has overlap.

**Unsupported file type**: a file whose extension is neither `.pdf` nor `.docx`.

**Indexing run**: one execution that extracts, chunks and embeds one document with one split strategy, replacing any chunks previously stored for that document and strategy.

**Search result**: one stored chunk returned for a query, ranked by similarity to it.
_Avoid_: hit, match
