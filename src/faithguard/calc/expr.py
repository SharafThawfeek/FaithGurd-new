"""A tiny arithmetic language over table cells, for CALCULATE edits and gold programs.

    growth(c12, c13)            percentage change
    (t1r3c2 - t1r3c3) / t1r3c3  plain arithmetic
    share(c4, sum(c4, c5, c6))  nested calls

Allowed: cell references, decimal literals, + - * /, unary minus, brackets, and the
functions in ops.FUNCTIONS. Expressions are parsed into a tree and evaluated with
Decimal; nothing is ever passed to eval, so arbitrary code cannot be expressed.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal
from typing import Callable, Union

from faithguard.calc.ops import CONTEXT, FUNCTIONS, CalcError, _div

MAX_LENGTH = 500
MAX_DEPTH = 20

_TOKEN = re.compile(r"\s*(?:(?P<num>\d+(?:\.\d+)?)|(?P<name>[A-Za-z_][A-Za-z0-9_]*)|(?P<op>[-+*/(),]))")


class ExprError(ValueError):
    pass


@dataclass(frozen=True)
class Num:
    value: Decimal


@dataclass(frozen=True)
class Ref:
    cell: str


@dataclass(frozen=True)
class Neg:
    arg: "Node"


@dataclass(frozen=True)
class BinOp:
    op: str
    left: "Node"
    right: "Node"


@dataclass(frozen=True)
class Call:
    fn: str
    args: tuple["Node", ...]


Node = Union[Num, Ref, Neg, BinOp, Call]


def _tokens(text: str) -> list[tuple[str, str]]:
    if len(text) > MAX_LENGTH:
        raise ExprError(f"expression longer than {MAX_LENGTH} characters")
    pos, out = 0, []
    text = text.rstrip()
    while pos < len(text):
        m = _TOKEN.match(text, pos)
        if not m:
            raise ExprError(f"unexpected character {text[pos]!r} at {pos}")
        kind = m.lastgroup
        out.append((kind, m.group(kind)))
        pos = m.end()
    return out


class _Parser:
    def __init__(self, tokens: list[tuple[str, str]]):
        self.tokens, self.i, self.depth = tokens, 0, 0

    def peek(self) -> tuple[str, str] | None:
        return self.tokens[self.i] if self.i < len(self.tokens) else None

    def take(self, value: str | None = None) -> tuple[str, str]:
        tok = self.peek()
        if tok is None or (value is not None and tok[1] != value):
            raise ExprError(f"expected {value or 'more input'}, got {tok[1] if tok else 'end'}")
        self.i += 1
        return tok

    def expr(self) -> Node:
        self.depth += 1
        if self.depth > MAX_DEPTH:
            raise ExprError("expression nested too deeply")
        node = self.term()
        while (tok := self.peek()) and tok[1] in "+-":
            self.take()
            node = BinOp(tok[1], node, self.term())
        self.depth -= 1
        return node

    def term(self) -> Node:
        node = self.factor()
        while (tok := self.peek()) and tok[1] in "*/":
            self.take()
            node = BinOp(tok[1], node, self.factor())
        return node

    def factor(self) -> Node:
        tok = self.take()
        kind, value = tok
        if value == "-":
            return Neg(self.factor())
        if kind == "num":
            return Num(Decimal(value))
        if value == "(":
            node = self.expr()
            self.take(")")
            return node
        if kind == "name":
            nxt = self.peek()
            if nxt and nxt[1] == "(":
                if value not in FUNCTIONS:
                    raise ExprError(f"unknown function {value!r}")
                self.take("(")
                args = [self.expr()]
                while self.peek() and self.peek()[1] == ",":
                    self.take(",")
                    args.append(self.expr())
                self.take(")")
                arity = FUNCTIONS[value][1]
                if arity != -1 and len(args) != arity:
                    raise ExprError(f"{value} takes {arity} arguments, got {len(args)}")
                return Call(value, tuple(args))
            return Ref(value)
        raise ExprError(f"unexpected {value!r}")


def parse(text: str) -> Node:
    parser = _Parser(_tokens(text))
    node = parser.expr()
    if parser.peek() is not None:
        raise ExprError(f"unexpected {parser.peek()[1]!r} after the expression")
    return node


def refs(node: Node) -> list[str]:
    """Cell references in order of first appearance."""
    out: list[str] = []

    def walk(n: Node) -> None:
        if isinstance(n, Ref):
            if n.cell not in out:
                out.append(n.cell)
        elif isinstance(n, Neg):
            walk(n.arg)
        elif isinstance(n, BinOp):
            walk(n.left)
            walk(n.right)
        elif isinstance(n, Call):
            for a in n.args:
                walk(a)

    walk(node)
    return out


def evaluate(node: Node, resolve: Callable[[str], Decimal]) -> Decimal:
    """Evaluate with Decimal; `resolve` maps a cell id to its value (and raises KeyError if unknown)."""
    if isinstance(node, Num):
        return node.value
    if isinstance(node, Ref):
        try:
            return resolve(node.cell)
        except KeyError as err:
            raise CalcError(f"unknown cell {node.cell!r}") from err
    if isinstance(node, Neg):
        return -evaluate(node.arg, resolve)
    if isinstance(node, BinOp):
        a, b = evaluate(node.left, resolve), evaluate(node.right, resolve)
        if node.op == "+":
            return CONTEXT.add(a, b)
        if node.op == "-":
            return CONTEXT.subtract(a, b)
        if node.op == "*":
            return CONTEXT.multiply(a, b)
        return _div(a, b)
    fn = FUNCTIONS[node.fn][0]
    return fn(*(evaluate(a, resolve) for a in node.args))


def calculate(text: str, values: dict[str, Decimal]) -> Decimal:
    """Parse and evaluate in one step."""
    return evaluate(parse(text), lambda cell: values[cell])


def to_text(node: Node) -> str:
    """Write a tree back as an expression string."""
    if isinstance(node, Num):
        return f"{node.value:f}"
    if isinstance(node, Ref):
        return node.cell
    if isinstance(node, Neg):
        return f"-{to_text(node.arg)}"
    if isinstance(node, BinOp):
        return f"({to_text(node.left)} {node.op} {to_text(node.right)})"
    return f"{node.fn}({', '.join(to_text(a) for a in node.args)})"
