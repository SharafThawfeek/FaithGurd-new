"""Find, parse, normalise and render the numbers in financial text.

Every value is a Decimal, never a float. Amounts are normalised to base units
(rupees, dollars), percentages to percentage points, and basis points to
percentage points. A mention keeps its printed style, so a corrected value can be
written back the way the original answer wrote it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from decimal import ROUND_HALF_UP, Decimal
from typing import Literal

Kind = Literal["amount", "percent", "ratio", "number", "year"]

SCALE_WORDS: dict[str, int] = {
    "thousand": 3, "thousands": 3, "k": 3, "'000": 3, "’000": 3,
    "million": 6, "millions": 6, "mn": 6, "mln": 6, "m": 6,
    "billion": 9, "billions": 9, "bn": 9, "b": 9,
    "trillion": 12, "trillions": 12, "tn": 12, "trn": 12,
    "lakh": 5, "lakhs": 5, "crore": 7, "crores": 7,
}
SCALE_NAMES = {3: "thousand", 6: "million", 9: "billion", 12: "trillion"}

CURRENCY_CODES = {
    "rs": "LKR", "rs.": "LKR", "lkr": "LKR", "slr": "LKR", "rupees": "LKR",
    "usd": "USD", "us$": "USD", "$": "USD", "dollars": "USD",
    "eur": "EUR", "€": "EUR", "gbp": "GBP", "£": "GBP", "inr": "INR",
}

_PREFIX = r"(?P<cur>Rs\.?|LKR|SLR|USD|US\$|\$|€|EUR|£|GBP|INR)"
_NUMBER = r"(?P<num>\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?|\.\d+)"
_SUFFIX = (
    r"(?P<suffix>"
    r"\s?(?:per\s?cent|percent|pct\b|%)"
    r"|\s?(?:basis\s+points|bps|bp)\b"
    r"|\s?(?:percentage\s+points|ppts?\b|pp\b)"
    r"|\s?(?:x\b|times\b)"
    r"|\s?(?:'000|’000)"
    r"|\s(?:thousand|million|billion|trillion|mn|mln|bn|tn|trn|lakh|crore)s?\b"
    r"|(?:k|m|mn|b|bn|tn)\b"
    r")?"
)
_CUR_AFTER = r"(?P<cur_after>\s(?:rupees|dollars|LKR|USD)\b)?"

NUMBER_RE = re.compile(
    r"(?<![\w.,/'’])"  # never start inside a word, a number, or a range like 2024/25
    r"(?P<sign>[-−])?"
    + _PREFIX + r"?\s?"
    r"(?P<sign2>[-−])?"
    + _NUMBER
    + r"(?![\d])"
    + _SUFFIX
    + _CUR_AFTER,
    re.IGNORECASE,
)

MONTHS = (
    "january|february|march|april|may|june|july|august|september|october|november|december"
    "|jan|feb|mar|apr|jun|jul|aug|sep|sept|oct|nov|dec"
)
_DATE_DAY_BEFORE = re.compile(rf"^\s*(?:st|nd|rd|th)?\s+(?:{MONTHS})\b", re.IGNORECASE)
_DATE_DAY_AFTER = re.compile(rf"\b(?:{MONTHS})\s*$", re.IGNORECASE)


@dataclass(frozen=True)
class NumberStyle:
    """How a number was printed, so a replacement can be printed the same way."""

    kind: Kind = "amount"
    prefix: str = ""  # currency as written, with its trailing space, e.g. "Rs. "
    suffix: str = ""  # scale or unit as written, e.g. " million", "%", " bps"
    scale: int = 0  # power of ten the printed number is in (6 for "million")
    decimals: int = 0
    grouping: bool = True  # thousands separators
    brackets: bool = False  # negative written as (1,234)
    bps: bool = False  # percentage printed in basis points


@dataclass(frozen=True)
class NumberMention:
    start: int
    end: int
    text: str
    raw: Decimal  # the number as printed, with its sign
    kind: Kind
    style: NumberStyle
    currency: str | None = None

    @property
    def decimals(self) -> int:
        return self.style.decimals

    @property
    def scale(self) -> int:
        return self.style.scale

    @property
    def value(self) -> Decimal:
        """Base units for amounts and numbers; percentage points for percentages."""
        if self.kind == "percent" and self.style.bps:
            return self.raw / 100
        if self.kind in ("amount", "number"):
            return self.raw.scaleb(self.style.scale)
        return self.raw

    def half_unit(self) -> Decimal:
        """Half of the last printed digit, in the same units as `value`: the rounding tolerance."""
        unit = Decimal(1).scaleb(-self.style.decimals)
        if self.kind == "percent" and self.style.bps:
            unit = unit / 100
        elif self.kind in ("amount", "number"):
            unit = unit.scaleb(self.style.scale)
        return unit / 2


def _scale_from_suffix(suffix: str) -> int:
    word = suffix.strip().lower()
    return SCALE_WORDS.get(word, SCALE_WORDS.get(word.rstrip("s"), 0))


def _is_date_part(text: str, start: int, end: int) -> bool:
    return bool(_DATE_DAY_BEFORE.match(text[end : end + 14]) or _DATE_DAY_AFTER.search(text[max(0, start - 12) : start]))


def find_numbers(text: str, include_years: bool = False, brackets_negative: bool = False) -> list[NumberMention]:
    """Every number in `text`, in order. Years and day-of-month numbers are skipped unless asked for.

    In prose, "(Rs. 5 million)" is an aside, so brackets are ignored. In table cells,
    pass brackets_negative=True: there "(1,234)" means minus 1,234.
    """
    mentions = []
    for m in NUMBER_RE.finditer(text):
        num = m.group("num")
        suffix = m.group("suffix") or ""
        cur = m.group("cur") or ""
        cur_after = m.group("cur_after") or ""
        start, end = m.start(), m.end()
        before, after = text[:start].rstrip(), text[end:].lstrip()
        brackets = brackets_negative and before.endswith("(") and after.startswith(")")
        if brackets:
            start = len(before) - 1
            end = len(text) - len(after) + 1
        negative = bool(m.group("sign") or m.group("sign2") or brackets)
        raw = Decimal(num.replace(",", ""))
        decimals = len(num.split(".")[1]) if "." in num else 0
        low = suffix.strip().lower()
        if low in ("%", "percent", "per cent", "pct", "percentage points", "pp", "ppt", "ppts") or "cent" in low:
            kind: Kind = "percent"
        elif low in ("bps", "bp", "basis points"):
            kind = "percent"
        elif low in ("x", "times"):
            kind = "ratio"
        elif cur or cur_after or _scale_from_suffix(suffix):
            kind = "amount"
        elif len(num) == 4 and num.isdigit() and 1900 <= int(num) <= 2100:
            kind = "year"
        else:
            kind = "number"
        if kind == "year" and not include_years:
            continue
        if kind == "number" and decimals == 0 and len(num) <= 2 and _is_date_part(text, start, end):
            continue
        style = NumberStyle(
            kind=kind,
            prefix=text[m.start("cur") : m.start("sign2") if m.group("sign2") else m.start("num")] if cur else "",
            suffix=suffix + cur_after,
            scale=_scale_from_suffix(suffix) if kind == "amount" else 0,
            decimals=decimals,
            grouping="," in num or len(num.split(".")[0]) < 4,
            brackets=brackets,
            bps=low in ("bps", "bp", "basis points"),
        )
        currency = CURRENCY_CODES.get((cur or cur_after.strip()).lower())
        mentions.append(
            NumberMention(
                start=start,
                end=end,
                text=text[start:end],
                raw=-raw if negative else raw,
                kind=kind,
                style=style,
                currency=currency,
            )
        )
    return mentions


def parse_number(text: str, brackets_negative: bool = True) -> NumberMention | None:
    """The single number in a short string such as a table cell; None if there is none."""
    found = find_numbers(text.strip(), include_years=True, brackets_negative=brackets_negative)
    return found[0] if len(found) == 1 else None


def parse_cell(text: str) -> NumberMention | None:
    """A table cell's printed number, or None for blanks and dashes. Handles '(1,234)' and '$ 5,829'."""
    t = text.strip().replace("$ ", "$").replace("( ", "(").replace(" )", ")")
    if t.lower() in ("", "-", "—", "–", "n/a", "nil", "none"):
        return None
    return parse_number(t)


def detect_scale(text: str) -> int:
    """The scale stated in a table title or header, e.g. "Rs. '000" -> 3, "(in millions)" -> 6."""
    low = text.lower()
    if re.search(r"['’]000|in thousands|thousands of|(?:rs\.?|lkr|usd|us\$|\$)\s?000\b", low):  # "Rs 000" too
        return 3
    if re.search(r"in millions|millions of|\bmn\b|\(million|\bmillion\)", low):
        return 6
    if re.search(r"in billions|billions of|\bbn\b", low):
        return 9
    return 0


def matches(mention: NumberMention, value: Decimal, slack: Decimal = Decimal("1e-9")) -> bool:
    """True if `value` (same units as mention.value) rounds to the printed number."""
    return abs(mention.value - value) <= mention.half_unit() + slack


def _group(digits: str) -> str:
    whole, _, frac = digits.partition(".")
    whole = f"{int(whole):,}"
    return whole + ("." + frac if frac else "")


def render(value: Decimal, style: NumberStyle, min_significant: int = 3) -> str:
    """Write `value` (base units or percentage points) in the given printed style."""
    if style.kind == "percent" and style.bps:
        x = value * 100
    elif style.kind in ("amount", "number"):
        x = value.scaleb(-style.scale)
    else:
        x = value
    decimals = style.decimals
    if style.kind in ("amount", "number") and x != 0:
        int_digits = len(str(int(abs(x)))) if abs(x) >= 1 else 0
        decimals = max(decimals, min(max(0, min_significant - int_digits), decimals + 2))
    q = abs(x).quantize(Decimal(1).scaleb(-decimals), rounding=ROUND_HALF_UP)
    while q == 0 and x != 0 and decimals < 4:
        decimals += 1
        q = abs(x).quantize(Decimal(1).scaleb(-decimals), rounding=ROUND_HALF_UP)
    digits = f"{q:f}"
    digits = _group(digits) if style.grouping else digits
    body = style.prefix + digits + style.suffix
    if x < 0 and q != 0:
        return f"({body})" if style.brackets else "-" + body
    return body


def restyle(style: NumberStyle, **changes) -> NumberStyle:
    return replace(style, **changes)


def default_style(kind: Kind, scale: int = 0, currency: str | None = None, decimals: int = 0) -> NumberStyle:
    """A plain style for values that have no original mention to copy, e.g. 'Rs. 14,213 million'."""
    prefix = {"LKR": "Rs. ", "USD": "$", "EUR": "€", "GBP": "£"}.get(currency or "", "")
    if kind == "percent":
        return NumberStyle(kind="percent", suffix="%", decimals=decimals or 1)
    suffix = f" {SCALE_NAMES[scale]}" if scale in SCALE_NAMES else ""
    return NumberStyle(kind=kind, prefix=prefix, suffix=suffix, scale=scale, decimals=decimals)
