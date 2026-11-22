import csv
import io
import os
from dataclasses import dataclass, field
from typing import Iterable, List, Optional, Sequence, Tuple


@dataclass
class CsvDocument:
    path: Optional[str] = None
    headers: List[str] = field(default_factory=list)
    rows: List[List[str]] = field(default_factory=list)
    delimiter: str = ","
    quotechar: str = '"'
    dirty: bool = False
    source_field_counts: List[int] = field(default_factory=list)
    source_issues: List[Tuple[int, str]] = field(default_factory=list)
    row_ids: List[int] = field(default_factory=list)
    grouped: bool = False
    group_columns: List[str] = field(default_factory=list)

    @classmethod
    def load(cls, path: str) -> "CsvDocument":
        with open(path, "r", encoding="utf-8-sig", newline="") as handle:
            text = handle.read()
        delimiter, quotechar = ",", '"'
        try:
            dialect = csv.Sniffer().sniff(text[:8192], delimiters=",;\t|")
            delimiter, quotechar = dialect.delimiter, dialect.quotechar
        except csv.Error:
            pass
        records = [list(record) for record in csv.reader(io.StringIO(text), delimiter=delimiter, quotechar=quotechar)]
        field_counts = [len(record) for record in records]
        issues = []
        expected = field_counts[0] if field_counts else 0
        for line, count in enumerate(field_counts, start=1):
            if count != expected:
                issues.append((line, "expected {} fields, found {}".format(expected, count)))
        strict_reader = csv.reader(io.StringIO(text), delimiter=delimiter, quotechar=quotechar, strict=True)
        try:
            for _ in strict_reader:
                pass
        except csv.Error as error:
            issues.append((strict_reader.line_num, "quote error: {}".format(error)))
        if not records:
            records = [[]]
        width = max(len(record) for record in records)
        records = [record + [""] * (width - len(record)) for record in records]
        document = cls(
            path=path,
            headers=records[0],
            rows=records[1:],
            delimiter=delimiter,
            quotechar=quotechar,
            source_field_counts=field_counts,
            source_issues=sorted(set(issues)),
        )
        document.row_ids = list(range(len(document.rows)))
        return document

    @classmethod
    def new(cls) -> "CsvDocument":
        document = cls(
            headers=["Column 1", "Column 2", "Column 3"],
            rows=[["", "", ""]],
            source_field_counts=[3, 3],
        )
        document.row_ids = [0]
        return document

    def _ensure_row_ids(self) -> None:
        if len(self.row_ids) != len(self.rows):
            self.row_ids = list(range(len(self.rows)))

    def column_values(self, column: int) -> Iterable[str]:
        return (row[column] for row in self.rows)

    def set_cell(self, row: int, column: int, value: str) -> None:
        if 0 <= row < len(self.rows) and 0 <= column < len(self.headers):
            if self.rows[row][column] != value:
                self.rows[row][column] = value
                self.dirty = True

    def set_header(self, column: int, value: str) -> None:
        if 0 <= column < len(self.headers) and self.headers[column] != value:
            self.headers[column] = value
            self.dirty = True

    def insert_row(self, index: int) -> None:
        self._ensure_row_ids()
        index = max(0, min(index, len(self.rows)))
        next_id = max(self.row_ids, default=-1) + 1
        self.rows.insert(index, [""] * len(self.headers))
        self.row_ids.insert(index, next_id)
        self.dirty = True

    def delete_row(self, index: int) -> None:
        self._ensure_row_ids()
        if 0 <= index < len(self.rows):
            del self.rows[index]
            del self.row_ids[index]
            self.dirty = True

    def delete_empty_rows(self) -> int:
        self._ensure_row_ids()
        kept = [
            (row, row_id)
            for row, row_id in zip(self.rows, self.row_ids)
            if any(value.strip() for value in row)
        ]
        removed = len(self.rows) - len(kept)
        if removed:
            self.rows = [row for row, _ in kept]
            self.row_ids = [row_id for _, row_id in kept]
            self.dirty = True
        return removed

    def reorder_rows(self, order: Sequence[int]) -> bool:
        self._ensure_row_ids()
        if len(order) != len(self.rows) or sorted(order) != list(range(len(self.rows))):
            raise ValueError("Invalid row order")
        if list(order) == list(range(len(self.rows))):
            return False
        self.rows = [self.rows[index] for index in order]
        self.row_ids = [self.row_ids[index] for index in order]
        self.source_field_counts = []
        self.source_issues = []
        self.dirty = True
        return True

    def restore_original_order(self) -> bool:
        self._ensure_row_ids()
        order = sorted(range(len(self.rows)), key=lambda index: self.row_ids[index])
        changed = self.reorder_rows(order)
        self.grouped = False
        self.group_columns = []
        return changed

    def insert_column(self, index: int, title: Optional[str] = None) -> None:
        index = max(0, min(index, len(self.headers)))
        self.headers.insert(index, title or "Column {}".format(len(self.headers) + 1))
        for row in self.rows:
            row.insert(index, "")
        self.dirty = True

    def delete_column(self, index: int) -> None:
        if 0 <= index < len(self.headers) and len(self.headers) > 1:
            del self.headers[index]
            for row in self.rows:
                del row[index]
            self.dirty = True

    def save(self, path: Optional[str] = None) -> str:
        target = path or self.path
        if not target:
            raise ValueError("No file path specified")
        width = len(self.headers)
        with open(target, "w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(
                handle,
                delimiter=self.delimiter,
                quotechar=self.quotechar,
                quoting=csv.QUOTE_MINIMAL,
                lineterminator="\n",
            )
            writer.writerow(self.headers)
            for row in self.rows:
                writer.writerow(row + [""] * (width - len(row)))
        self.path = target
        self.dirty = False
        return target

    @property
    def name(self) -> str:
        return os.path.basename(self.path) if self.path else "Untitled.csv"
