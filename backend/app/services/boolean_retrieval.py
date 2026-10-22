"""Boolean retrieval: query tokenizer, recursive-descent parser, postings-merge evaluator.

Grammar (precedence NOT > AND > OR, evaluated without ``eval``)::

    query   := or_expr
    or_expr := and_expr ( OR and_expr )*
    and_expr:= not_expr ( AND not_expr )*
    not_expr:= NOT not_expr | primary
    primary := TERM | '(' or_expr ')'

Operators are case-insensitive. Operands go through the same preprocessing as
documents (so ``Learning`` matches the index term ``learn``). NOT is the complement
relative to the searchable corpus (all indexed documents).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Callable, Union

from app.services.inverted_index import InvertedIndex

MAX_NESTING_DEPTH = 50


class BooleanQueryError(ValueError):
    def __init__(self, message: str, position: int | None = None):
        super().__init__(message)
        self.message = message
        self.position = position


# --------------------------------------------------------------------------- tokens
@dataclass(frozen=True)
class QueryToken:
    kind: str  # TERM, AND, OR, NOT, LPAREN, RPAREN
    text: str
    pos: int


_TOKEN_RE = re.compile(r"\(|\)|[^\s()]+")
_OPERATORS = {"AND", "OR", "NOT"}


def tokenize_query(query: str) -> list[QueryToken]:
    tokens = []
    for m in _TOKEN_RE.finditer(query):
        text = m.group()
        if text == "(":
            kind = "LPAREN"
        elif text == ")":
            kind = "RPAREN"
        elif text.upper() in _OPERATORS:
            kind = text.upper()
        else:
            kind = "TERM"
        tokens.append(QueryToken(kind, text, m.start()))
    return tokens


# --------------------------------------------------------------------------- AST
@dataclass(frozen=True)
class TermNode:
    raw: str
    terms: tuple[str, ...]  # index terms (more than one if the operand splits, e.g. "node.js")


@dataclass(frozen=True)
class NotNode:
    child: "Node"


@dataclass(frozen=True)
class AndNode:
    left: "Node"
    right: "Node"


@dataclass(frozen=True)
class OrNode:
    left: "Node"
    right: "Node"


Node = Union[TermNode, NotNode, AndNode, OrNode]


def node_to_string(node: Node) -> str:
    """Fully parenthesised rendering that makes the parsed precedence visible."""
    if isinstance(node, TermNode):
        return node.raw
    if isinstance(node, NotNode):
        return f"(NOT {node_to_string(node.child)})"
    op = "AND" if isinstance(node, AndNode) else "OR"
    return f"({node_to_string(node.left)} {op} {node_to_string(node.right)})"


def node_to_dict(node: Node) -> dict:
    if isinstance(node, TermNode):
        return {"type": "TERM", "value": node.raw, "index_terms": list(node.terms)}
    if isinstance(node, NotNode):
        return {"type": "NOT", "child": node_to_dict(node.child)}
    kind = "AND" if isinstance(node, AndNode) else "OR"
    return {"type": kind, "left": node_to_dict(node.left), "right": node_to_dict(node.right)}


# --------------------------------------------------------------------------- parser
class Parser:
    def __init__(self, tokens: list[QueryToken], resolve_term: Callable[[str], list[str]]):
        self.tokens = tokens
        self.resolve_term = resolve_term
        self.i = 0

    def _peek(self) -> QueryToken | None:
        return self.tokens[self.i] if self.i < len(self.tokens) else None

    def _next(self) -> QueryToken:
        tok = self.tokens[self.i]
        self.i += 1
        return tok

    def parse(self) -> Node:
        if not self.tokens:
            raise BooleanQueryError("Query is empty.")
        node = self._or(0)
        tok = self._peek()
        if tok is not None:
            if tok.kind == "RPAREN":
                raise BooleanQueryError(f"Unmatched ')' at position {tok.pos}.", tok.pos)
            raise BooleanQueryError(
                f"Missing operator before '{tok.text}' at position {tok.pos}; use AND, OR or NOT.", tok.pos
            )
        return node

    def _or(self, depth: int) -> Node:
        node = self._and(depth)
        while (tok := self._peek()) is not None and tok.kind == "OR":
            self._next()
            node = OrNode(node, self._and(depth))
        return node

    def _and(self, depth: int) -> Node:
        node = self._not(depth)
        while (tok := self._peek()) is not None and tok.kind == "AND":
            self._next()
            node = AndNode(node, self._not(depth))
        return node

    def _not(self, depth: int) -> Node:
        tok = self._peek()
        if tok is not None and tok.kind == "NOT":
            self._next()
            if depth >= MAX_NESTING_DEPTH:
                raise BooleanQueryError("Query is nested too deeply.", tok.pos)
            return NotNode(self._not(depth + 1))
        return self._primary(depth)

    def _primary(self, depth: int) -> Node:
        tok = self._peek()
        prev = self.tokens[self.i - 1] if self.i > 0 else None
        if tok is None:
            after = f" after '{prev.text}'" if prev else ""
            raise BooleanQueryError(f"Unexpected end of query: expected a term, NOT or '('{after}.")
        if tok.kind == "LPAREN":
            self._next()
            if depth >= MAX_NESTING_DEPTH:
                raise BooleanQueryError("Query is nested too deeply.", tok.pos)
            node = self._or(depth + 1)
            closing = self._peek()
            if closing is None or closing.kind != "RPAREN":
                raise BooleanQueryError(f"Missing closing ')' for '(' at position {tok.pos}.", tok.pos)
            self._next()
            return node
        if tok.kind == "TERM":
            self._next()
            return self._term(tok)
        what = {"RPAREN": "')'", "AND": "AND", "OR": "OR"}.get(tok.kind, tok.text)
        raise BooleanQueryError(
            f"Unexpected {what} at position {tok.pos}: expected a term, NOT or '('.", tok.pos
        )

    def _term(self, tok: QueryToken) -> TermNode:
        if "*" in tok.text:
            raise BooleanQueryError(
                f"Wildcard '*' in '{tok.text}' is not supported in Boolean queries; use tolerant search.", tok.pos
            )
        terms = self.resolve_term(tok.text)
        if not terms:
            raise BooleanQueryError(
                f"'{tok.text}' contains no indexable term (stop word or punctuation only).", tok.pos
            )
        return TermNode(tok.text, tuple(terms))


def parse_boolean_query(query: str, resolve_term: Callable[[str], list[str]]) -> Node:
    return Parser(tokenize_query(query or ""), resolve_term).parse()


# --------------------------------------------------------------------------- postings merges
def intersect(a: list[int], b: list[int]) -> list[int]:
    """Classic two-pointer merge of sorted postings: O(|a| + |b|)."""
    i = j = 0
    out = []
    while i < len(a) and j < len(b):
        if a[i] == b[j]:
            out.append(a[i]); i += 1; j += 1
        elif a[i] < b[j]:
            i += 1
        else:
            j += 1
    return out


def union(a: list[int], b: list[int]) -> list[int]:
    i = j = 0
    out = []
    while i < len(a) and j < len(b):
        if a[i] == b[j]:
            out.append(a[i]); i += 1; j += 1
        elif a[i] < b[j]:
            out.append(a[i]); i += 1
        else:
            out.append(b[j]); j += 1
    out.extend(a[i:])
    out.extend(b[j:])
    return out


def difference(a: list[int], b: list[int]) -> list[int]:
    """Elements of ``a`` not in ``b`` (NOT x == universe - x)."""
    i = j = 0
    out = []
    while i < len(a):
        if j >= len(b) or a[i] < b[j]:
            out.append(a[i]); i += 1
        elif a[i] == b[j]:
            i += 1; j += 1
        else:
            j += 1
    return out


# --------------------------------------------------------------------------- evaluation
@dataclass
class EvaluationStep:
    step: int
    operation: str  # LOOKUP, AND, OR, NOT
    description: str
    result_size: int


@dataclass
class BooleanResult:
    query: str
    parsed_expression: str
    ast: dict
    doc_ids: list[int]
    steps: list[EvaluationStep] = field(default_factory=list)
    unknown_terms: list[str] = field(default_factory=list)
    index_terms: dict[str, list[str]] = field(default_factory=dict)


def _preview(ids: list[int], limit: int = 8) -> str:
    shown = ", ".join(map(str, ids[:limit]))
    return f"[{shown}{', ...' if len(ids) > limit else ''}]"


class BooleanRetriever:
    def __init__(self, index: InvertedIndex, resolve_term: Callable[[str], list[str]]):
        self.index = index
        self.resolve_term = resolve_term

    def search(self, query: str) -> BooleanResult:
        node = parse_boolean_query(query, self.resolve_term)
        steps: list[EvaluationStep] = []
        unknown: list[str] = []
        mapping: dict[str, list[str]] = {}
        universe = self.index.all_doc_ids()

        def record(op: str, desc: str, result: list[int]) -> list[int]:
            steps.append(EvaluationStep(len(steps) + 1, op, desc, len(result)))
            return result

        def ev(n: Node) -> list[int]:
            if isinstance(n, TermNode):
                mapping[n.raw] = list(n.terms)
                result: list[int] | None = None
                for t in n.terms:
                    ids = self.index.doc_ids(t)
                    if not ids and t not in unknown:
                        unknown.append(t)
                    record("LOOKUP", f"postings('{t}') = {_preview(ids)} (df={len(ids)})", ids)
                    result = ids if result is None else record(
                        "AND", f"intersect postings of operand '{n.raw}'", intersect(result, ids)
                    )
                return result or []
            if isinstance(n, NotNode):
                child = ev(n.child)
                return record(
                    "NOT",
                    f"complement of {len(child)} docs within {len(universe)} searchable docs",
                    difference(universe, child),
                )
            left, right = ev(n.left), ev(n.right)
            if isinstance(n, AndNode):
                res = intersect(left, right)
                return record("AND", f"intersect {len(left)} docs with {len(right)} docs -> {_preview(res)}", res)
            res = union(left, right)
            return record("OR", f"union {len(left)} docs with {len(right)} docs -> {_preview(res)}", res)

        doc_ids = ev(node)
        return BooleanResult(
            query=query,
            parsed_expression=node_to_string(node),
            ast=node_to_dict(node),
            doc_ids=doc_ids,
            steps=steps,
            unknown_terms=unknown,
            index_terms=mapping,
        )


# --------------------------------------------------------------------------- incidence matrix
def incidence_matrix(index: InvertedIndex, terms: list[str], doc_ids: list[int]) -> list[list[int]]:
    """Binary term-document incidence matrix: rows = ``terms``, columns = ``doc_ids``."""
    return [[1 if index.tf(t, d) > 0 else 0 for d in doc_ids] for t in terms]
