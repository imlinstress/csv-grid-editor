from typing import List, Sequence


def group_indices(document, indices: Sequence[int]) -> List[int]:
    if not indices:
        raise ValueError("At least one column must be selected")
    for index in indices:
        if not 0 <= index < len(document.headers):
            raise ValueError("Column index out of range: {}".format(index))

    def sort_key(row_index):
        parts = []
        for column in indices:
            value = document.rows[row_index][column]
            try:
                parts.append((0, float(str(value).replace(",", ""))))
            except (TypeError, ValueError):
                parts.append((1, str(value).lower()))
        return tuple(parts)

    return sorted(range(len(document.rows)), key=sort_key)
