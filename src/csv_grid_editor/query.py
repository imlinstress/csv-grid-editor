import ast
import re
from typing import List, Optional, Tuple

SELECT = re.compile(r"^\s*select\s+", re.IGNORECASE)
KEYWORDS = re.compile(r"\b(where|order\s+by|limit)\b", re.IGNORECASE)
ORDER = re.compile(r"^(a\d+|nr)(?:\s+(asc|desc))?$", re.IGNORECASE)
REFERENCE = re.compile(r"^a(\d+)$", re.IGNORECASE)


class QueryError(Exception):
    pass


def _mask_strings(text):
    characters = list(text)
    quote = None
    for index, character in enumerate(characters):
        if quote:
            if character == quote:
                quote = None
            characters[index] = " "
        elif character in "'\"":
            quote = character
            characters[index] = " "
    return "".join(characters)


def _strip_select(text):
    match = SELECT.match(text)
    if not match:
        raise QueryError("Query must start with SELECT")
    return text[match.end():].strip()


def _split_clauses(query):
    masked = _mask_strings(query)
    matches = list(KEYWORDS.finditer(masked))
    if not matches:
        return _strip_select(query.strip()), None, None, None
    select = _strip_select(query[:matches[0].start()].strip())
    clauses = {}
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(query)
        word = match.group(1).lower()
        key = "order" if word.startswith("order") else word
        clauses[key] = query[match.end():end].strip()
    if not select:
        raise QueryError("SELECT clause is empty")
    return select, clauses.get("where"), clauses.get("order"), clauses.get("limit")


def _column_index(reference, count):
    reference = reference.strip()
    if reference.upper() == "NR":
        return -1
    match = REFERENCE.match(reference)
    if not match:
        raise QueryError("Invalid column reference: {}".format(reference))
    index = int(match.group(1)) - 1
    if not 0 <= index < count:
        raise QueryError("Column {} is out of range (1-{})".format(index + 1, count))
    return index


def _parse_select(select, count):
    if select.strip() == "*":
        return list(range(count))
    return [_column_index(part, count) for part in select.split(",")]


def _validate(node):
    if isinstance(node, ast.Expression):
        _validate(node.body)
        return
    if isinstance(node, ast.Constant):
        if isinstance(node.value, (str, int, float, bool, type(None))):
            return
        raise QueryError("Unsupported literal")
    if isinstance(node, ast.Name):
        if node.id.upper() == "NR" or REFERENCE.match(node.id):
            return
        raise QueryError("Unknown name: {}".format(node.id))
    if isinstance(node, ast.BoolOp) and isinstance(node.op, (ast.And, ast.Or)):
        for value in node.values:
            _validate(value)
        return
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.Not, ast.USub, ast.UAdd)):
        _validate(node.operand)
        return
    if isinstance(node, ast.Compare) and all(
        isinstance(op, (ast.Eq, ast.NotEq, ast.Lt, ast.LtE, ast.Gt, ast.GtE)) for op in node.ops
    ):
        _validate(node.left)
        for comparator in node.comparators:
            _validate(comparator)
        return
    if isinstance(node, ast.Call):
        if not isinstance(node.func, ast.Name) or node.func.id.lower() != "contains" or len(node.args) != 2:
            raise QueryError("Only contains(value, substring) is supported")
        for argument in node.args:
            _validate(argument)
        return
    if isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Add, ast.Sub, ast.Mult, ast.Div)):
        _validate(node.left)
        _validate(node.right)
        return
    raise QueryError("Unsupported expression")


def _parse_where(where):
    try:
        tree = ast.parse(where, mode="eval")
    except SyntaxError as error:
        raise QueryError("Invalid WHERE expression: {}".format(error.msg))
    _validate(tree)
    return tree


def _parse_order(order, count):
    match = ORDER.match(order.strip()) if order else None
    if not match:
        raise QueryError("ORDER BY expects a column such as a1 [ASC|DESC]")
    return _column_index(match.group(1), count), (match.group(2) or "").lower() == "desc"


def _parse_limit(limit):
    try:
        value = int(limit)
    except (TypeError, ValueError):
        raise QueryError("LIMIT expects a non-negative integer")
    if value < 0:
        raise QueryError("LIMIT expects a non-negative integer")
    return value


def _number(value):
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    try:
        return float(str(value).replace(",", ""))
    except (TypeError, ValueError):
        return None


def _compare(operator, left, right):
    left_number, right_number = _number(left), _number(right)
    if left_number is not None and right_number is not None:
        left, right = left_number, right_number
    else:
        left, right = str(left), str(right)
    if isinstance(operator, ast.Eq):
        return left == right
    if isinstance(operator, ast.NotEq):
        return left != right
    if isinstance(operator, ast.Lt):
        return left < right
    if isinstance(operator, ast.LtE):
        return left <= right
    if isinstance(operator, ast.Gt):
        return left > right
    return left >= right


def _evaluate(node, values):
    if isinstance(node, ast.Expression):
        return _evaluate(node.body, values)
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.Name):
        return values[node.id.upper()]
    if isinstance(node, ast.BoolOp):
        if isinstance(node.op, ast.And):
            return all(_evaluate(value, values) for value in node.values)
        return any(_evaluate(value, values) for value in node.values)
    if isinstance(node, ast.UnaryOp):
        operand = _evaluate(node.operand, values)
        if isinstance(node.op, ast.Not):
            return not operand
        return -operand if isinstance(node.op, ast.USub) else +operand
    if isinstance(node, ast.Compare):
        left = _evaluate(node.left, values)
        for operator, comparator in zip(node.ops, node.comparators):
            right = _evaluate(comparator, values)
            if not _compare(operator, left, right):
                return False
            left = right
        return True
    if isinstance(node, ast.Call):
        arguments = [_evaluate(argument, values) for argument in node.args]
        return str(arguments[1]) in str(arguments[0])
    left = _evaluate(node.left, values)
    right = _evaluate(node.right, values)
    if isinstance(node.op, ast.Add):
        return left + right
    if isinstance(node.op, ast.Sub):
        return left - right
    if isinstance(node.op, ast.Mult):
        return left * right
    return left / right


def _sort_key(value):
    number = _number(value)
    return (0, number) if number is not None else (1, str(value).lower())


def run(document, query: str) -> Tuple[List[str], List[List[str]]]:
    select, where, order, limit = _split_clauses(query)
    count = len(document.headers)
    indices = _parse_select(select, count)
    where_node = _parse_where(where) if where else None
    order_index, descending = _parse_order(order, count) if order else (None, False)
    limit_value = _parse_limit(limit) if limit else None

    headers = ["NR" if index == -1 else document.headers[index] for index in indices]
    records = []
    for line, row in enumerate(document.rows, start=2):
        values = {"NR": str(line)}
        for index in range(count):
            values["A{}".format(index + 1)] = row[index]
        if where_node is not None and not _evaluate(where_node, values):
            continue
        result = [str(line) if index == -1 else row[index] for index in indices]
        key = str(line) if order_index is None or order_index == -1 else row[order_index]
        records.append((key, result))

    if order_index is not None:
        records.sort(key=lambda item: _sort_key(item[0]), reverse=descending)
    if limit_value is not None:
        records = records[:limit_value]
    return headers, [record for _, record in records]
