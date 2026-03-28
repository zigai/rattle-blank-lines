from __future__ import annotations

from collections.abc import Sequence

import libcst as cst

BRANCH_SMALL_STATEMENTS = (cst.Break, cst.Continue, cst.Raise, cst.Return)
HEADER_BLOCK_STATEMENTS = (cst.For, cst.If, cst.Match, cst.While, cst.With)
CONTROL_BLOCK_STATEMENTS = (cst.For, cst.If, cst.Match, cst.Try, cst.While, cst.With)
EXCEPTION_CLEANUP_PARENTS = (cst.ExceptHandler, cst.Finally)
DOCSTRING_VALUE_NODES = (cst.ConcatenatedString, cst.SimpleString)


class NameCollector(cst.CSTVisitor):
    """Collect all ``Name`` values below a node."""

    def __init__(self) -> None:
        self.names: set[str] = set()

    def visit_ClassDef(self, _node: cst.ClassDef) -> bool:  # noqa: N802
        return False

    def visit_FunctionDef(self, _node: cst.FunctionDef) -> bool:  # noqa: N802
        return False

    def visit_Name(self, node: cst.Name) -> None:  # noqa: N802
        self.names.add(node.value)


def collect_names(node: cst.CSTNode) -> set[str]:
    collector = NameCollector()
    node.visit(collector)

    return collector.names


def is_blank_line(line: cst.EmptyLine) -> bool:
    return line.comment is None


def has_separator(statement: cst.BaseStatement) -> bool:
    return len(statement.leading_lines) > 0


def prepend_blank_line(statement: cst.BaseStatement) -> cst.BaseStatement:
    return statement.with_changes(
        leading_lines=(cst.EmptyLine(indent=False), *statement.leading_lines)
    )


def is_branch_statement(statement: cst.BaseStatement) -> bool:
    if not isinstance(statement, cst.SimpleStatementLine):
        return False

    if len(statement.body) != 1:
        return False

    return isinstance(statement.body[0], BRANCH_SMALL_STATEMENTS)


def is_docstring_statement(statement: cst.BaseStatement) -> bool:
    if not isinstance(statement, cst.SimpleStatementLine):
        return False

    if len(statement.body) != 1:
        return False

    expression = statement.body[0]
    if not isinstance(expression, cst.Expr):
        return False

    return isinstance(expression.value, DOCSTRING_VALUE_NODES)


def assignment_small_statement(statement: cst.BaseStatement) -> cst.BaseSmallStatement | None:
    if not isinstance(statement, cst.SimpleStatementLine):
        return None

    if len(statement.body) != 1:
        return None

    small_statement = statement.body[0]
    if isinstance(small_statement, (cst.AnnAssign, cst.Assign, cst.AugAssign)):
        return small_statement

    return None


def extract_target_names(target: cst.BaseExpression) -> list[str]:
    if isinstance(target, cst.Name):
        return [target.value]

    if isinstance(target, (cst.List, cst.Tuple)):
        names: list[str] = []
        for element in target.elements:
            names.extend(extract_target_names(element.value))

        return names

    if isinstance(target, cst.StarredElement):
        return extract_target_names(target.value)

    return []


def target_reference_names(target: cst.BaseAssignTargetExpression) -> set[str]:
    if isinstance(target, cst.Name):
        return set()

    if isinstance(target, (cst.List, cst.Tuple)):
        names: set[str] = set()
        for element in target.elements:
            names.update(target_reference_names(element.value))

        return names

    if isinstance(target, cst.StarredElement):
        return target_reference_names(target.value)

    return collect_names(target)


def assigned_names(statement: cst.BaseStatement) -> set[str]:
    assignment = assignment_small_statement(statement)
    if assignment is None:
        return set()

    names: list[str] = []
    if isinstance(assignment, cst.Assign):
        for assign_target in assignment.targets:
            names.extend(extract_target_names(assign_target.target))
    elif isinstance(assignment, (cst.AnnAssign, cst.AugAssign)):
        names.extend(extract_target_names(assignment.target))

    return set(names)


def ordered_assigned_names(statement: cst.BaseStatement) -> list[str]:
    assignment = assignment_small_statement(statement)
    if assignment is None:
        return []

    names: list[str] = []
    if isinstance(assignment, cst.Assign):
        for assign_target in assignment.targets:
            names.extend(extract_target_names(assign_target.target))
    elif isinstance(assignment, (cst.AnnAssign, cst.AugAssign)):
        names.extend(extract_target_names(assignment.target))

    return names


def last_assigned_name(statement: cst.BaseStatement) -> str | None:
    names = ordered_assigned_names(statement)
    if not names:
        return None

    return names[-1]


def assignment_reference_names(statement: cst.BaseStatement) -> set[str]:
    assignment = assignment_small_statement(statement)
    if assignment is None:
        return set()

    names: set[str] = set()
    if isinstance(assignment, cst.Assign):
        names.update(collect_names(assignment.value))

        for assign_target in assignment.targets:
            names.update(target_reference_names(assign_target.target))
    elif isinstance(assignment, cst.AnnAssign):
        if assignment.value is not None:
            names.update(collect_names(assignment.value))

        names.update(target_reference_names(assignment.target))
    elif isinstance(assignment, cst.AugAssign):
        names.update(collect_names(assignment.target))
        names.update(collect_names(assignment.value))

    return names


def header_expression_nodes(statement: cst.BaseStatement) -> list[cst.CSTNode]:
    if isinstance(statement, cst.If):
        return [statement.test]

    if isinstance(statement, cst.While):
        return [statement.test]

    if isinstance(statement, cst.For):
        return [statement.iter]

    if isinstance(statement, cst.With):
        return [item.item for item in statement.items]

    if isinstance(statement, cst.Match):
        return [statement.subject]

    return []


def first_statement_in_suite(suite: cst.BaseSuite) -> cst.CSTNode | None:
    if isinstance(suite, cst.IndentedBlock):
        if not suite.body:
            return None

        return suite.body[0]

    if isinstance(suite, cst.SimpleStatementSuite):
        if not suite.body:
            return None

        return suite.body[0]

    return None


def first_statement_in_block(statement: cst.BaseStatement) -> cst.CSTNode | None:
    if isinstance(statement, (cst.For, cst.If, cst.Try, cst.While, cst.With)):
        return first_statement_in_suite(statement.body)

    if isinstance(statement, cst.Match):
        if not statement.cases:
            return None

        return first_statement_in_suite(statement.cases[0].body)

    return None


def is_header_block_statement(statement: cst.BaseStatement) -> bool:
    return isinstance(statement, HEADER_BLOCK_STATEMENTS)


def is_control_block_statement(statement: cst.BaseStatement) -> bool:
    return isinstance(statement, CONTROL_BLOCK_STATEMENTS)


def is_exception_cleanup_suite_parent(node: cst.CSTNode) -> bool:
    return isinstance(node, EXCEPTION_CLEANUP_PARENTS)


def is_terminal_exception_cleanup_run(
    body: list[cst.BaseStatement] | tuple[cst.BaseStatement, ...],
    start_index: int,
    suite_parent: cst.CSTNode | None,
) -> bool:
    if suite_parent is None or not is_exception_cleanup_suite_parent(suite_parent):
        return False

    if start_index < 0 or start_index >= len(body):
        return False

    if not is_branch_statement(body[-1]):
        return False

    return all(isinstance(statement, cst.SimpleStatementLine) for statement in body[start_index:])


def is_single_line_control_block(statement: cst.BaseStatement) -> bool:
    if isinstance(statement, cst.Match):
        return False

    if isinstance(statement, (cst.For, cst.If, cst.Try, cst.While, cst.With)):
        return isinstance(statement.body, cst.SimpleStatementSuite)

    return False


def _simple_if_test_subject(statement: cst.BaseStatement) -> cst.BaseExpression | None:
    if (
        not isinstance(statement, cst.If)
        or statement.orelse is not None
        or not isinstance(statement.body, cst.IndentedBlock)
        or len(statement.body.body) != 1
        or not isinstance(statement.test, cst.Comparison)
        or len(statement.test.comparisons) != 1
    ):
        return None

    return statement.test.left


def is_same_subject_simple_if_chain(
    current_statement: cst.BaseStatement,
    next_statement: cst.BaseStatement,
) -> bool:
    current_subject = _simple_if_test_subject(current_statement)
    if current_subject is None:
        return False

    next_subject = _simple_if_test_subject(next_statement)
    if next_subject is None:
        return False

    return current_subject.deep_equals(next_subject)


def _assert_reference_names(statement: cst.Assert) -> set[str]:
    names = collect_names(statement.test)
    if statement.msg is not None:
        names.update(collect_names(statement.msg))

    return names


def _branch_reference_names(statement: cst.Raise | cst.Return) -> set[str]:
    expression = statement.exc if isinstance(statement, cst.Raise) else statement.value
    if expression is None:
        return set()

    return collect_names(expression)


def small_statement_reference_names(statement: cst.BaseSmallStatement) -> set[str]:
    if isinstance(statement, cst.Assert):
        return _assert_reference_names(statement)

    if isinstance(statement, (cst.Assign, cst.AnnAssign, cst.AugAssign)):
        return assignment_reference_names(cst.SimpleStatementLine(body=[statement]))

    if isinstance(statement, cst.Expr):
        return collect_names(statement.value)

    if isinstance(statement, (cst.Raise, cst.Return)):
        return _branch_reference_names(statement)

    return set()


def statement_reference_names(statement: cst.BaseStatement) -> set[str]:
    if isinstance(statement, cst.SimpleStatementLine):
        names: set[str] = set()
        for small_statement in statement.body:
            names.update(small_statement_reference_names(small_statement))

        return names

    if is_control_block_statement(statement):
        names: set[str] = set()
        for expression in header_expression_nodes(statement):
            names.update(collect_names(expression))

        return names

    return set()


def has_nontrivial_related_use(
    body: Sequence[cst.BaseStatement],
    assignment_index: int,
    *,
    lookahead: int,
) -> bool:
    if lookahead <= 0 or assignment_index < 0 or assignment_index >= len(body):
        return False

    names = assigned_names(body[assignment_index])
    if not names:
        return False

    for next_index in range(assignment_index + 1, min(len(body), assignment_index + 1 + lookahead)):
        statement = body[next_index]
        if not statement_reference_names(statement).intersection(names):
            continue

        if (
            is_branch_statement(statement)
            and isinstance(statement, cst.SimpleStatementLine)
            and len(statement.body) == 1
        ):
            branch = statement.body[0]
            if (
                isinstance(branch, cst.Return)
                and isinstance(branch.value, cst.Name)
                and branch.value.value in names
            ):
                continue

            if (
                isinstance(branch, cst.Raise)
                and isinstance(branch.exc, cst.Name)
                and branch.exc.value in names
            ):
                continue

        return True

    return False


def suite_statements(suite: cst.BaseSuite) -> list[cst.BaseStatement]:
    if isinstance(suite, cst.IndentedBlock):
        return list(suite.body)

    return []


def leading_block_body_statements(
    statement: cst.BaseStatement,
    *,
    limit: int,
) -> list[cst.BaseStatement]:
    if limit <= 0:
        return []

    if isinstance(statement, (cst.For, cst.If, cst.While, cst.With)):
        return suite_statements(statement.body)[:limit]

    if isinstance(statement, cst.Match) and statement.cases:
        return suite_statements(statement.cases[0].body)[:limit]

    return []


def control_block_ends_with_loop_exit(statement: cst.BaseStatement) -> bool:
    if not isinstance(statement, (cst.If, cst.Match, cst.Try)):
        return False

    if isinstance(statement, cst.Try):
        body = suite_statements(statement.body)
    elif isinstance(statement, cst.Match):
        if not statement.cases:
            return False

        body = suite_statements(statement.cases[0].body)
    else:
        body = suite_statements(statement.body)

    if not body or not is_branch_statement(body[-1]):
        return False

    branch = body[-1]
    if not isinstance(branch, cst.SimpleStatementLine) or len(branch.body) != 1:
        return False

    return isinstance(branch.body[0], (cst.Break, cst.Continue))


def _suite_is_single_pass(suite: cst.BaseSuite) -> bool:
    if isinstance(suite, cst.IndentedBlock):
        statements = suite.body
        if len(statements) != 1:
            return False
        statement = statements[0]

        return (
            isinstance(statement, cst.SimpleStatementLine)
            and len(statement.body) == 1
            and isinstance(statement.body[0], cst.Pass)
        )

    if isinstance(suite, cst.SimpleStatementSuite):
        return len(suite.body) == 1 and isinstance(suite.body[0], cst.Pass)

    return False


def is_pass_only_try(statement: cst.BaseStatement) -> bool:
    return (
        isinstance(statement, cst.Try)
        and bool(statement.handlers)
        and statement.orelse is None
        and statement.finalbody is None
        and all(_suite_is_single_pass(handler.body) for handler in statement.handlers)
    )


def count_non_empty_lines(source_lines: list[str], start_line: int, end_line: int) -> int:
    if not source_lines:
        return 0

    safe_start = max(start_line, 1)
    safe_end = min(end_line, len(source_lines))

    if safe_end < safe_start:
        return 0

    count = 0
    for line_number in range(safe_start, safe_end + 1):
        if source_lines[line_number - 1].strip():
            count += 1

    return count


__all__ = [
    "BRANCH_SMALL_STATEMENTS",
    "CONTROL_BLOCK_STATEMENTS",
    "HEADER_BLOCK_STATEMENTS",
    "NameCollector",
    "assigned_names",
    "assignment_reference_names",
    "assignment_small_statement",
    "collect_names",
    "control_block_ends_with_loop_exit",
    "count_non_empty_lines",
    "extract_target_names",
    "first_statement_in_block",
    "first_statement_in_suite",
    "has_nontrivial_related_use",
    "has_separator",
    "header_expression_nodes",
    "is_blank_line",
    "is_branch_statement",
    "is_control_block_statement",
    "is_docstring_statement",
    "is_header_block_statement",
    "is_pass_only_try",
    "is_same_subject_simple_if_chain",
    "is_single_line_control_block",
    "last_assigned_name",
    "leading_block_body_statements",
    "ordered_assigned_names",
    "prepend_blank_line",
    "statement_reference_names",
    "suite_statements",
    "target_reference_names",
]
