from dataclasses import dataclass
from typing import List, Set


@dataclass
class LintIssue:
    line: int
    message: str


def check(document) -> List[LintIssue]:
    issues = [LintIssue(line, message) for line, message in document.source_issues]
    expected = len(document.headers)
    for offset, row in enumerate(document.rows, start=1):
        if len(row) != expected:
            issues.append(LintIssue(offset + 1, "expected {} fields, found {}".format(expected, len(row))))
    return sorted(issues, key=lambda issue: issue.line)


def bad_rows(issues: List[LintIssue]) -> Set[int]:
    return {issue.line - 2 for issue in issues if issue.line >= 2}
