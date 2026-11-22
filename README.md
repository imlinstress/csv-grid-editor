# CSV Grid Editor

A GTK3 CSV editor for Debian/Ubuntu with a spreadsheet-style grid, Rainbow CSV-style colors, aligned and resizable columns, frozen editable headers, pinned line numbers, live CSVLint, RBQL-style queries, grouping, and system light/dark theming.

Current version: **1.4.1**.

## About

| Detail | Value |
| --- | --- |
| Repository | `imlinstress/csv-grid-editor` |
| URL | https://github.com/imlinstress/csv-grid-editor |
| Default branch | `main` |
| Package name | `csv-grid-editor` |
| Platform | Debian/Ubuntu with Python 3, GTK 3, and PyGObject |
| UI toolkit | GTK 3 |
| Project type | Desktop application with local Debian packaging |

This repository contains the complete source, packaging metadata, build script, and released `.deb` packages. `build.sh` stages the application into `dist/build-root` and produces the installable package in `dist/`.

## Features

- Rainbow colors per column, with contrast-aware text on light and dark themes.
- Live theme switching that follows GNOME's `color-scheme` setting.
- Frozen, editable header row and a pinned `#` column numbering data rows from 1.
- Automatic column sizing, numeric right-alignment, and per-column alignment overrides.
- Cell tooltips showing column number and header.
- Live CSV issue highlighting: field-count mismatches and strict quote errors.
- RBQL-style queries: `SELECT`, `WHERE`, `ORDER BY`, `LIMIT`, `NR`, `aN`, and `contains()`.
- Group By: reorders rows so matching values are contiguous; numeric-aware, stable, and reversible.
- Copy selection data as TSV or Markdown.
- Delete empty rows.
- Desktop launcher and scalable icon.

## Requirements

- Python 3.9+
- GTK 3 and PyGObject

On Debian/Ubuntu:

```bash
sudo apt install python3 python3-gi gir1.2-gtk-3.0
```

`dpkg-deb` is provided by the base `dpkg` package and is used to build the `.deb`.

## Build

From the repository root:

```bash
./build.sh
```

The script syntax-checks the Python sources, stages the package, runs `dpkg-deb --build`, and writes the result to:

```text
dist/csv-grid-editor_<version>_all.deb
```

When changing the source, update `VERSION` in `build.sh` and the version shown in Help → About before rebuilding.

## Install and run

```bash
sudo dpkg -i dist/csv-grid-editor_1.4.1_all.deb
csv-grid-editor ~/Documents/data.csv
```

The application also appears in the desktop application grid as **CSV Grid Editor**.

## Keyboard shortcuts

| Shortcut | Action |
| --- | --- |
| `Ctrl+N` | New document |
| `Ctrl+O` | Open CSV |
| `Ctrl+S` | Save |
| `Ctrl+Shift+S` | Save As |
| `Ctrl+Q` | Quit |
| `Insert` | Add row |
| `Delete` | Delete row |
| `F2` | Rename column |
| `Ctrl+Shift+Delete` | Delete empty rows |
| `Ctrl+Shift+R` | Restore original row order after grouping |
| `Ctrl+Shift+Q` | Query |
| `Ctrl+Shift+G` | Group By |

## Project layout

```text
build.sh                         Package build script
packaging/control.in             Debian control template
packaging/csv-grid-editor.svg    Application icon
src/csv_grid_editor/             Application source modules
dist/                            Built .deb packages
```

## Modules

- `app.py` — GTK user interface, menus, grid rendering, and dialogs.
- `model.py` — CSV loading, saving, editing, row identities, and reordering.
- `theme.py` — system theme detection and contrast-aware colors.
- `group.py` — stable numeric-aware grouping order.
- `query.py` — RBQL-style query parser and evaluator.
- `lint.py` — CSV issue checks.
- `alignment.py` — numeric detection, alignment, and column sizing.
