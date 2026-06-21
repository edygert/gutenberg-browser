# Gutenberg Browser

A terminal UI for browsing and searching Project Gutenberg metadata. Built with
[Textual](https://textual.textualize.io/) and a local SQLite full-text (FTS5) index.

## Requirements

- Python 3.10+
- [uv](https://docs.astral.sh/uv/)
- `rdf-files.tar.zip` — the Project Gutenberg RDF/XML metadata catalog, placed in the
  project root. The app can fetch this for you (see [Updating the index](#updating-the-index)),
  or you can [download it manually](https://www.gutenberg.org/cache/epub/feeds/rdf-files.tar.zip).

## Running the app

From the project root (the directory containing `rdf-files.tar.zip`):

```bash
uv run gutenberg-browser
```

`uv` creates the virtual environment and installs dependencies automatically on
first run.

On first launch the app builds `gutenberg.db` from `rdf-files.tar.zip` (a one-time
indexing pass over ~78k records — this takes a while). Subsequent launches open
instantly against the existing database.

### Updating the index

Fetch the latest catalog from gutenberg.org and update the index in one step:

```bash
uv run gutenberg-browser --download
```

`--download` works even when no `rdf-files.tar.zip` is present yet, so it doubles as the
easiest way to get started.

If you've already obtained a newer `rdf-files.tar.zip` yourself:

```bash
uv run gutenberg-browser --update    # incrementally index changed/new records
uv run gutenberg-browser --reindex   # drop and rebuild the index from scratch
```

You can also refresh the catalog from inside the running app — press `d` (see key
bindings below). The app reindexes automatically if the FTS schema in `gutenberg.db` is
out of date.

## Using the app

- Type to search across titles, authors, subjects, bookshelves, and summaries.
- Filter results by language and sort by **Alpha**, **Downloads**, or **Relevance**
  (relevance requires an active search query).

### Key bindings

| Key      | Action            |
| -------- | ----------------- |
| `/`      | Focus search      |
| `o`      | Open book in browser |
| `d`      | Refresh catalog (download latest + reindex) |
| `Escape` | Clear search      |
| `q`      | Quit              |

## Development

```bash
uv sync                        # install dependencies (incl. dev tools)
uv run textual run --dev src/gutenberg_browser/app.py   # run with the Textual devtools
```

## Project layout

```
src/gutenberg_browser/
  __main__.py        # CLI entry point (argument parsing, launch)
  app.py             # Textual App, screens, key bindings
  db.py              # SQLite schema, search queries, FTS
  indexer.py         # RDF parsing and (incremental) indexing
  models.py          # data models
  widgets/           # search panel, detail panel, progress screen
```
