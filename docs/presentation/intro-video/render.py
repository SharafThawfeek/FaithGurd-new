"""Render the FaithGuard intro video: narration, animated scenes and captions -> MP4 (1920x1080, 30 fps).

    python render.py script.json AUDIO_DIR OUT.mp4              # the video
    python render.py script.json AUDIO_DIR SHEET.png --sheet    # key frames on one image, to check the layout

AUDIO_DIR holds one MP3 per sentence (tts.py). Needs Pillow, NumPy and ffmpeg on the PATH.
"""

from __future__ import annotations

import math
import json
import subprocess
import sys
import wave
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

W, H, FPS, SR = 1920, 1080, 30, 48000
GAP = 0.35  # silence between sentences in a scene

BG = (232, 225, 212)
NAVY = (30, 42, 58)
INK2 = (92, 99, 112)
CARD = (251, 248, 242)
SOFT = (240, 234, 223)
LINE = (210, 201, 186)
BRONZE = (156, 107, 48)
RED = (178, 58, 48)
RED_BG = (244, 220, 213)
GREEN = (46, 125, 79)
GREEN_BG = (219, 236, 223)
AMBER = (170, 112, 34)
AMBER_BG = (246, 231, 205)
WHITE = (255, 255, 255)

FONTS = {"regular": "segoeui.ttf", "semibold": "seguisb.ttf", "bold": "segoeuib.ttf",
         "light": "segoeuil.ttf", "semilight": "segoeuisl.ttf"}


@lru_cache(maxsize=None)
def font(kind: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(f"C:/Windows/Fonts/{FONTS[kind]}", size)


# ---------------------------------------------------------------- timing helpers

def clamp(x: float, a: float = 0.0, b: float = 1.0) -> float:
    return max(a, min(b, x))


def ease(x: float) -> float:
    x = clamp(x)
    return 1 - (1 - x) ** 3


def ramp(t: float, start: float, dur: float = 0.5) -> float:
    return ease((t - start) / dur)


def window(t: float, start: float, end: float, fade: float = 0.35) -> float:
    """1 between start and end, with smooth edges."""
    return min(ramp(t, start, fade), 1 - ramp(t, end - fade, fade))


# ---------------------------------------------------------------- sprites

class Sp:
    """An RGBA image plus the offset of its content origin (cards carry a shadow margin)."""

    def __init__(self, im: Image.Image, ox: int = 0, oy: int = 0):
        self.im, self.ox, self.oy = im, ox, oy

    @property
    def w(self) -> int:
        return self.im.width - 2 * self.ox

    @property
    def h(self) -> int:
        return self.im.height - 2 * self.oy


def blit(fr: Image.Image, sp: Sp, x: float, y: float, op: float = 1.0, crop_w: float | None = None) -> None:
    if op <= 0.004:
        return
    im = sp.im
    if crop_w is not None:
        if crop_w < 1:
            return
        im = im.crop((0, 0, min(im.width, int(crop_w) + sp.ox), im.height))
    if op < 0.999:
        im = im.copy()
        im.putalpha(im.getchannel("A").point(lambda v: int(v * op)))
    dx, dy = int(round(x - sp.ox)), int(round(y - sp.oy))
    sx, sy = max(0, -dx), max(0, -dy)
    if sx or sy:
        im = im.crop((sx, sy, im.width, im.height))
        dx, dy = dx + sx, dy + sy
    fr.alpha_composite(im, (dx, dy))


def compose(base: Sp, items) -> Sp:
    im = base.im.copy()
    for sp, x, y in items:
        im.alpha_composite(sp.im, (int(base.ox + x - sp.ox), int(base.oy + y - sp.oy)))
    return Sp(im, base.ox, base.oy)


def wrap(text: str, f: ImageFont.FreeTypeFont, max_w: float) -> list[str]:
    out = []
    for para in text.split("\n"):
        cur = ""
        for word in para.split():
            trial = f"{cur} {word}".strip()
            if cur and f.getlength(trial) > max_w:
                out.append(cur)
                cur = word
            else:
                cur = trial
        out.append(cur)
    return out


def text_sprite(text: str, kind: str, size: int, color, max_w: float | None = None, spacing: float = 1.3,
                align: str = "left") -> Sp:
    f = font(kind, size)
    lines = wrap(text, f, max_w) if max_w else text.split("\n")
    asc, desc = f.getmetrics()
    lh = int(round(size * spacing))
    width = int(max(f.getlength(l) for l in lines)) + 6
    height = lh * (len(lines) - 1) + asc + desc + 4
    im = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    for i, line in enumerate(lines):
        lw = f.getlength(line)
        x = (width - lw) / 2 if align == "center" else 0
        d.text((x, i * lh), line, font=f, fill=color)
    return Sp(im)


def label_sprite(text: str, size: int, color, tracking: float = 2.5, kind: str = "semibold") -> Sp:
    """Small upper-case label with letter spacing."""
    f = font(kind, size)
    text = text.upper()
    width = int(sum(f.getlength(c) + tracking for c in text)) + 4
    asc, desc = f.getmetrics()
    im = Image.new("RGBA", (width, asc + desc + 2), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    x = 0.0
    for c in text:
        d.text((x, 0), c, font=f, fill=color)
        x += f.getlength(c) + tracking
    return Sp(im)


def card(w: int, h: int, fill=CARD, radius: int = 26, border=None, bw: int = 2, shadow: float = 0.13) -> Sp:
    pad, s = 44, 2
    big = Image.new("RGBA", ((w + 2 * pad) * s, (h + 2 * pad) * s), (0, 0, 0, 0))
    if shadow:
        sh = Image.new("RGBA", big.size, (0, 0, 0, 0))
        ImageDraw.Draw(sh).rounded_rectangle([pad * s, (pad + 12) * s, (pad + w) * s, (pad + h + 12) * s], radius * s,
                                             fill=(60, 45, 25, int(255 * shadow)))
        big.alpha_composite(sh.filter(ImageFilter.GaussianBlur(16 * s)))
    d = ImageDraw.Draw(big)
    d.rounded_rectangle([pad * s, pad * s, (pad + w) * s, (pad + h) * s], radius * s, fill=fill,
                        outline=border, width=bw * s if border else 0)
    return Sp(big.resize((w + 2 * pad, h + 2 * pad), Image.LANCZOS), pad, pad)


def pill(w: int, h: int, fill, radius: int | None = None) -> Sp:
    s = 3
    im = Image.new("RGBA", (w * s, h * s), (0, 0, 0, 0))
    ImageDraw.Draw(im).rounded_rectangle([0, 0, w * s - 1, h * s - 1], (radius if radius is not None else h // 2) * s, fill=fill)
    return Sp(im.resize((w, h), Image.LANCZOS))


def tag(text: str, fg, bg, size: int = 24) -> Sp:
    t = text_sprite(text, "semibold", size, fg)
    p = pill(t.w + 34, t.h + 6, bg)
    return compose(p, [(t, 17, 1)])


def arrow(length: int, color=INK2, thick: int = 4, head: int = 15) -> Sp:
    s = 4
    im = Image.new("RGBA", ((length + 4) * s, (2 * head + 4) * s), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    cy = (head + 2) * s
    d.line([(2 * s, cy), ((length - head) * s, cy)], fill=color, width=thick * s)
    d.polygon([((length - head - 4) * s, cy - head * 0.62 * s), ((length + 2) * s, cy),
               ((length - head - 4) * s, cy + head * 0.62 * s)], fill=color)
    return Sp(im.resize((length + 4, 2 * head + 4), Image.LANCZOS))


# ---------------------------------------------------------------- icons

def icon(kind: str, size: int, color=NAVY, bg=None, inner: float = 0.56) -> Sp:
    s = 4
    n = size * s
    im = Image.new("RGBA", (n, n), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    if bg is not None:
        d.ellipse([0, 0, n - 1, n - 1], fill=bg)
        k = inner
    else:
        k = 1.0
    o = (1 - k) / 2

    def Q(x, y):
        return (n * (o + k * x), n * (o + k * y))

    L = max(2, int(n * k * 0.085))
    if kind == "shield":
        pts = [(.5, .04), (.68, .1), (.9, .16), (.89, .4), (.84, .58), (.74, .74), (.62, .86), (.5, .95),
               (.38, .86), (.26, .74), (.16, .58), (.11, .4), (.1, .16), (.32, .1)]
        d.polygon([Q(*p) for p in pts], fill=color)
        d.line([Q(.32, .5), Q(.46, .64), Q(.7, .36)], fill=CARD, width=int(L * 1.25), joint="curve")
    elif kind == "warning":
        d.polygon([Q(.5, .1), Q(.95, .88), Q(.05, .88)], outline=color, width=L)
        d.line([Q(.5, .38), Q(.5, .62)], fill=color, width=L)
        cx, cy = Q(.5, .75)
        d.ellipse([cx - L * .7, cy - L * .7, cx + L * .7, cy + L * .7], fill=color)
    elif kind == "search":
        d.ellipse([*Q(.08, .08), *Q(.66, .66)], outline=color, width=L)
        d.line([Q(.6, .6), Q(.9, .9)], fill=color, width=int(L * 1.3))
    elif kind == "doc":
        d.rounded_rectangle([*Q(.18, .06), *Q(.82, .94)], int(n * k * .07), outline=color, width=L)
        for y in (.32, .5, .68):
            d.line([Q(.32, y), Q(.68, y)], fill=color, width=int(L * .75))
    elif kind == "bubble":
        d.rounded_rectangle([*Q(.06, .12), *Q(.94, .7)], int(n * k * .16), outline=color, width=L)
        d.line([Q(.3, .69), Q(.24, .9), Q(.48, .69)], fill=color, width=L, joint="curve")
    elif kind == "table":
        d.rounded_rectangle([*Q(.08, .16), *Q(.92, .84)], int(n * k * .07), outline=color, width=L)
        d.line([Q(.08, .4), Q(.92, .4)], fill=color, width=int(L * .75))
        d.line([Q(.08, .62), Q(.92, .62)], fill=color, width=int(L * .75))
        d.line([Q(.4, .16), Q(.4, .84)], fill=color, width=int(L * .75))
    elif kind == "fork":
        d.line([Q(.06, .5), Q(.4, .5)], fill=color, width=L)
        d.line([Q(.4, .5), Q(.76, .22)], fill=color, width=L)
        d.line([Q(.4, .5), Q(.76, .78)], fill=color, width=L)
        for (x, y, a) in ((.86, .14, -0.66), (.86, .86, 0.66)):
            tip = Q(x, y)
            ang = math.atan2(-1 if a < 0 else 1, 1.28)
            back = 0.17 * n * k
            left = (tip[0] - back * math.cos(ang - 0.5), tip[1] - back * math.sin(ang - 0.5))
            right = (tip[0] - back * math.cos(ang + 0.5), tip[1] - back * math.sin(ang + 0.5))
            d.polygon([tip, left, right], fill=color)
        cx, cy = Q(.4, .5)
        d.ellipse([cx - L, cy - L, cx + L, cy + L], fill=color)
    elif kind == "edit":
        ax, ay, bx, by = .16, .84, .84, .16
        ux, uy = (bx - ax) / math.hypot(bx - ax, by - ay), (by - ay) / math.hypot(bx - ax, by - ay)
        vx, vy = -uy * .12, ux * .12
        px, py = ax + ux * .2, ay + uy * .2
        body = [(px + vx, py + vy), (bx + vx, by + vy), (bx - vx, by - vy), (px - vx, py - vy)]
        d.polygon([Q(*p) for p in body], outline=color, width=L)
        d.line([Q(px + vx, py + vy), Q(ax, ay), Q(px - vx, py - vy)], fill=color, width=L, joint="curve")
        qx, qy = bx - ux * .2, by - uy * .2
        d.line([Q(qx + vx, qy + vy), Q(qx - vx, qy - vy)], fill=color, width=L)
    elif kind == "gauge":
        d.arc([*Q(.06, .2), *Q(.94, 1.08)], start=180, end=360, fill=color, width=L)
        cx, cy = Q(.5, .64)
        a = math.radians(-50)
        ex, ey = cx + .32 * n * k * math.cos(a), cy + .32 * n * k * math.sin(a)
        d.line([(cx, cy), (ex, ey)], fill=color, width=L)
        d.ellipse([cx - L * 1.1, cy - L * 1.1, cx + L * 1.1, cy + L * 1.1], fill=color)
    elif kind == "chip":
        d.rounded_rectangle([*Q(.26, .26), *Q(.74, .74)], int(n * k * .06), outline=color, width=L)
        for i in range(3):
            c = .38 + i * .12
            d.line([Q(c, .08), Q(c, .26)], fill=color, width=int(L * .7))
            d.line([Q(c, .74), Q(c, .92)], fill=color, width=int(L * .7))
            d.line([Q(.08, c), Q(.26, c)], fill=color, width=int(L * .7))
            d.line([Q(.74, c), Q(.92, c)], fill=color, width=int(L * .7))
    elif kind == "globe":
        d.ellipse([*Q(.06, .06), *Q(.94, .94)], outline=color, width=L)
        d.ellipse([*Q(.3, .06), *Q(.7, .94)], outline=color, width=int(L * .8))
        d.line([Q(.06, .5), Q(.94, .5)], fill=color, width=int(L * .8))
    elif kind == "check":
        d.line([Q(.2, .52), Q(.42, .74), Q(.82, .3)], fill=color, width=int(L * 1.25), joint="curve")
    elif kind == "info":
        d.line([Q(.5, .44), Q(.5, .82)], fill=color, width=int(L * 1.2))
        cx, cy = Q(.5, .22)
        d.ellipse([cx - L * .9, cy - L * .9, cx + L * .9, cy + L * .9], fill=color)
    return Sp(im.resize((size, size), Image.LANCZOS))


def badge(n: int, size: int = 54) -> Sp:
    s = 4
    im = Image.new("RGBA", (size * s, size * s), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.ellipse([0, 0, size * s - 1, size * s - 1], fill=BRONZE)
    d.text((size * s / 2, size * s / 2 + s * 1), str(n), font=font("semibold", int(size * .52) * s), fill=WHITE, anchor="mm")
    return Sp(im.resize((size, size), Image.LANCZOS))


# ---------------------------------------------------------------- shared pieces

def background() -> Image.Image:
    y, x = np.mgrid[0:H, 0:W].astype(np.float32)
    g = (x / W * 0.55 + y / H * 0.45)  # light top-left to slightly deeper bottom-right
    r = np.hypot((x - W / 2) / (W / 2), (y - H / 2) / (H / 2))
    shade = 1.0 + 0.022 * (0.5 - g) - 0.035 * np.clip(r - 0.55, 0, None)
    arr = np.clip(np.array(BG, np.float32)[None, None, :] * shade[..., None], 0, 255).astype(np.uint8)
    return Image.fromarray(arr, "RGB").convert("RGBA")


def heading(text: str) -> Sp:
    t = text_sprite(text, "semibold", 56, NAVY)
    bar = pill(70, 6, BRONZE, radius=3)
    return compose(Sp(Image.new("RGBA", (t.w + 10, t.h + 30), (0, 0, 0, 0))), [(t, 0, 0), (bar, 3, t.h + 14)])


def wordmark() -> Sp:
    logo = icon("shield", 38, NAVY)
    name = text_sprite("FaithGuard", "semibold", 30, NAVY)
    im = Image.new("RGBA", (logo.w + 14 + name.w, max(logo.h, name.h)), (0, 0, 0, 0))
    base = Sp(im)
    return compose(base, [(logo, 0, (base.h - logo.h) // 2), (name, logo.w + 14, (base.h - name.h) // 2 - 4)])


def caption(text: str) -> Sp:
    t = text_sprite(text, "regular", 31, NAVY, max_w=1440, align="center", spacing=1.32)
    p = pill(t.w + 70, t.h + 24, (255, 255, 255, 214), radius=26)
    return compose(p, [(t, 35, 9)])


@dataclass
class Scene:
    id: str
    start: float
    end: float
    sent: list  # (start, end, text) in scene time

    @property
    def dur(self) -> float:
        return self.end - self.start

    def at(self, i: int, phrase: str | None = None) -> float:
        """When sentence i (or the phrase inside it) starts, estimated by characters."""
        s, e, text = self.sent[i]
        if phrase is None:
            return s
        k = text.find(phrase)
        return s + (e - s) * max(k, 0) / len(text)


# ---------------------------------------------------------------- scenes

class Title:
    caption = False

    def __init__(self):
        self.logo = icon("shield", 168, NAVY)
        self.name = text_sprite("FaithGuard", "semibold", 136, NAVY)
        self.tag = text_sprite("Checking AI answers about financial reports\nbefore they reach the reader", "light", 46, INK2,
                               align="center", spacing=1.28)
        self.foot = label_sprite("IT4010 Research Project", 22, INK2, tracking=3)

    def draw(self, fr, t, sc):
        a = ramp(t, 0.2, 0.8)
        blit(fr, self.logo, W / 2 - self.logo.w / 2, 196 + 26 * (1 - a), a)
        b = ramp(t, 0.5, 0.8)
        blit(fr, self.name, W / 2 - self.name.w / 2, 388 + 26 * (1 - b), b)
        c = ramp(t, 1.0, 0.7)
        if c > 0:
            ImageDraw.Draw(fr).rounded_rectangle([W / 2 - 120 * c, 600, W / 2 + 120 * c, 605], 3, fill=BRONZE)
        e = ramp(t, sc.at(1) - 0.1, 0.8)
        blit(fr, self.tag, W / 2 - self.tag.w / 2, 640 + 20 * (1 - e), e)
        f = ramp(t, sc.at(1) + 1.6, 0.8)
        blit(fr, self.foot, W / 2 - self.foot.w / 2, 812, f)


class Problem:
    caption = True
    ANSWER = "Group profit after tax rose 7.0%\nto Rs. 12,450 million."

    def __init__(self):
        self.head = heading("The problem")
        self.chat = card(900, 520)
        self.chat_label = label_sprite("AI assistant", 20, INK2)
        q = text_sprite("What was the Group's profit after tax in 2025?", "regular", 30, WHITE, max_w=500)
        self.qb = compose(pill(q.w + 56, q.h + 34, NAVY, radius=26), [(q, 28, 14)])
        self.af = font("semibold", 38)
        self.lines = self.ANSWER.split("\n")
        self.ab = pill(int(max(self.af.getlength(l) for l in self.lines)) + 70, 2 * 52 + 52, SOFT, radius=26)
        self.ai_icon = icon("bubble", 46, BRONZE)
        # the wrong figure, on line 2
        x0 = self.af.getlength("to ")
        x1 = self.af.getlength("to Rs. 12,450 million")
        self.hl = pill(int(x1 - x0) + 20, 50, RED_BG, radius=10)
        self.hl_x = x0 - 10
        note = text_sprite("Looks right, but it is the Bank's profit, not the Group's.", "semibold", 26, RED)
        self.callout = compose(Sp(Image.new("RGBA", (50 + note.w, 52), (0, 0, 0, 0))),
                               [(icon("warning", 34, RED), 0, 8), (note, 50, 5)])
        rows = [("Miscalculated", "A growth rate worked out wrongly"),
                ("Wrong scale", "Thousands read as millions"),
                ("Wrong context", "The Bank's profit given as the Group's")]
        self.rows = []
        for name, desc in rows:
            c = card(700, 150)
            self.rows.append(compose(c, [(tag(name, RED, RED_BG, 24), 36, 26),
                                         (text_sprite(desc, "semibold", 34, NAVY), 36, 76)]))
        # the mix in the benchmark labels (runs/main/labels/report.md, "Labelled spans by slot")
        fact = text_sprite("Our benchmark labels: 216 marked spans.\n130 are a wrong number; 9 are wrong context.",
                           "semibold", 26, NAVY, spacing=1.3)
        self.fact = compose(card(700, 110, fill=SOFT, shadow=0.0),
                            [(icon("info", 44, WHITE, bg=BRONZE, inner=0.6), 32, 33), (fact, 100, 16)])

    def draw(self, fr, t, sc):
        blit(fr, self.head, 120, 92, ramp(t, 0.0, 0.6))
        a = ramp(t, 0.15, 0.6)
        cx, cy = 120, 236
        blit(fr, self.chat, cx, cy + 20 * (1 - a), a)
        blit(fr, self.chat_label, cx + 40, cy + 34, a)
        q = ramp(t, sc.at(0) + 0.5, 0.6)
        blit(fr, self.qb, cx + 900 - 40 - self.qb.w, cy + 92 + 14 * (1 - q), q)
        # the AI answer types itself out
        ai_t = sc.at(0) + 2.0
        b = ramp(t, ai_t, 0.45)
        bx, by = cx + 40, cy + 92 + self.qb.h + 40
        blit(fr, self.ai_icon, bx, by + 6, b)
        blit(fr, self.ab, bx + 64, by, b)
        total = len(self.ANSWER.replace("\n", ""))
        shown = int(total * clamp((t - ai_t - 0.3) / 2.2))
        h = ramp(t, sc.at(1) + 1.6, 0.5)
        if h > 0:
            blit(fr, self.hl, bx + 64 + 35 + self.hl_x, by + 26 + 52 + 2, h)
        if shown > 0:
            d = ImageDraw.Draw(fr)
            left = shown
            for i, line in enumerate(self.lines):
                part = line[:max(0, left)]
                left -= len(line)
                if not part:
                    break
                d.text((bx + 64 + 35, by + 22 + i * 52), part, font=self.af, fill=NAVY)
        c = ramp(t, sc.at(2) + 0.4, 0.6)
        blit(fr, self.callout, bx, by + self.ab.h + 36 + 10 * (1 - c), c)
        for i, (row, phrase) in enumerate(zip(self.rows, ("miscalculated", "wrong scale", "wrong part"))):
            r = ramp(t, sc.at(2, phrase) - 0.15, 0.55)
            blit(fr, row, 1100 + 40 * (1 - r), 236 + i * 168, r)
        f = ramp(t, sc.at(3) - 0.1, 0.55)
        blit(fr, self.fact, 1100, 744 + 16 * (1 - f), f)


class Why:
    caption = True

    def __init__(self):
        self.head = heading("Why it matters")
        items = [("warning", RED, "One wrong figure", "can mislead an investment or an audit decision."),
                 ("search", NAVY, "Hard to catch", "You must find the right line, and often redo the arithmetic."),
                 ("table", BRONZE, "Sri Lanka: none found", "We found no comparable public dataset for Sri Lankan companies.")]
        self.cards = []
        for kind, color, title, body in items:
            c = card(500, 400)
            self.cards.append(compose(c, [(icon(kind, 92, color, bg=SOFT), 44, 44),
                                          (text_sprite(title, "semibold", 42, NAVY), 44, 176),
                                          (text_sprite(body, "regular", 31, INK2, max_w=410), 44, 246)]))

    def draw(self, fr, t, sc):
        blit(fr, self.head, 120, 92, ramp(t, 0.0, 0.6))
        for i, c in enumerate(self.cards):
            a = ramp(t, sc.at(i) - 0.1, 0.6)
            blit(fr, c, 150 + i * 560, 290 + 36 * (1 - a), a)


class Flow:
    caption = True

    def __init__(self):
        self.head = heading("How FaithGuard works")
        inp = card(300, 330)
        rows = [("bubble", "Question"), ("doc", "Annual report"), ("bubble", "AI answer")]
        items = [(label_sprite("Input", 20, INK2), 36, 34)]
        for i, (k, name) in enumerate(rows):
            items += [(icon(k, 40, BRONZE), 36, 96 + i * 70), (text_sprite(name, "semibold", 30, NAVY), 92, 94 + i * 70)]
        self.inp = compose(inp, items)
        steps = [(1, "Detect", "Every number is checked against the report's tables. What does not fit is flagged, with the reason."),
                 (2, "Decide", "Send it as it is, repair it, or hold it back?"),
                 (3, "Repair", "Wrong numbers are replaced with the report's own figures, each traced to its source.")]
        self.steps, self.steps_hl = [], []
        for n, title, body in steps:
            content = [(badge(n), 34, 34), (text_sprite(title, "semibold", 44, NAVY), 104, 30),
                       (text_sprite(body, "regular", 28, INK2, max_w=340), 34, 116)]
            self.steps.append(compose(card(400, 330), content))
            self.steps_hl.append(compose(card(400, 330, border=BRONZE, bw=3, shadow=0.2), content))
        self.ok = compose(card(400, 116, fill=GREEN_BG),
                          [(icon("check", 56, WHITE, bg=GREEN, inner=0.6), 28, 30),
                           (text_sprite("Trusted answer,\nwith its sources", "semibold", 28, GREEN, spacing=1.18), 104, 20)])
        self.hold = compose(card(400, 116, fill=AMBER_BG),
                            [(icon("info", 56, WHITE, bg=AMBER, inner=0.6), 28, 30),
                             (text_sprite("Held back: evidence\nand an honest reason", "semibold", 28, AMBER, spacing=1.18), 104, 20)])
        self.arrow = arrow(58)
        self.down = Sp(arrow(56).im.rotate(-90, expand=True))
        self.x = [96, 506, 966, 1426]

    def draw(self, fr, t, sc):
        blit(fr, self.head, 120, 92, ramp(t, 0.0, 0.6))
        c0 = sc.at(0)
        y = 300
        a = ramp(t, c0 - 0.2, 0.5)
        blit(fr, self.inp, self.x[0], y + 24 * (1 - a), a)
        hl = [window(t, sc.at(1), sc.at(2) - 0.1), window(t, sc.at(2), sc.at(3) - 0.1), window(t, sc.at(3), sc.at(4) - 0.1)]
        for i in range(3):
            st = c0 + 0.45 + i * 0.55
            blit(fr, self.arrow, self.x[i] + (300 if i == 0 else 400) + 12, y + 148, 1.0, crop_w=62 * ramp(t, st, 0.35))
            b = ramp(t, st + 0.25, 0.5)
            lift = -8 * hl[i]
            blit(fr, self.steps[i], self.x[i + 1], y + 24 * (1 - b) + lift, b)
            blit(fr, self.steps_hl[i], self.x[i + 1], y + lift, b * hl[i])
        g = ramp(t, sc.at(3, "so every corrected"), 0.6)
        blit(fr, self.down, self.x[3] + 200 - self.down.w / 2, y + 344, g)
        blit(fr, self.ok, self.x[3], y + 418 + 20 * (1 - g), g)
        k = ramp(t, sc.at(4) + 0.2, 0.6)
        blit(fr, self.down, self.x[2] + 200 - self.down.w / 2, y + 344, k)
        blit(fr, self.hold, self.x[2], y + 418 + 20 * (1 - k), k)


class Example:
    caption = True
    BEFORE = "Group profit after tax rose 7.0% to Rs. 12,450 million."
    AFTER = "Group profit after tax rose 9.3% to Rs. 14,213 million."

    def __init__(self):
        self.head = heading("An example")
        self.q = text_sprite("Question: What was the Group's profit after tax in 2025?", "regular", 30, INK2)
        self.f = font("semibold", 46)
        self.before = compose(card(1680, 176), [(label_sprite("AI answer", 20, INK2), 40, 22)])
        self.after = compose(card(1680, 176), [(label_sprite("FaithGuard", 20, GREEN), 40, 22)])
        self.btext = text_sprite(self.BEFORE, "semibold", 46, NAVY)
        self.atext = text_sprite(self.AFTER, "semibold", 46, NAVY)
        self.marks_b = [self.span(self.BEFORE, "7.0%", RED_BG), self.span(self.BEFORE, "Rs. 12,450 million", RED_BG)]
        self.marks_a = [self.span(self.AFTER, "9.3%", GREEN_BG), self.span(self.AFTER, "Rs. 14,213 million", GREEN_BG)]
        self.notes_b = [text_sprite("7.0% is the Bank's growth", "semibold", 24, RED),
                        text_sprite("Rs. 12,450 million is the Bank's profit", "semibold", 24, RED)]
        self.notes_a = [text_sprite("9.3% is calculated from Group 2025 and 2024", "semibold", 24, GREEN),
                        text_sprite("Rs. 14,213 million is the Group's 2025 figure", "semibold", 24, GREEN)]
        # the report extract: headers in the card, figures drawn above their highlights
        self.cols = ["Profit after tax (Rs. '000)", "Group 2025", "Group 2024", "Bank 2025"]
        self.cw = [400, 240, 240, 240]
        items = [(label_sprite("Annual report extract", 20, INK2), 32, 22)]
        x = 32
        for i, cname in enumerate(self.cols):
            items.append((text_sprite(cname, "semibold" if i else "regular", 27, NAVY if i else INK2), x, 68))
            x += self.cw[i]
        self.table = compose(card(sum(self.cw) + 64, 200), items)
        self.vals = [None] + [text_sprite(v, "regular", 34, NAVY) for v in ("14,212,560", "13,004,180", "12,450,330")]
        self.cell_red = pill(220, 58, RED_BG, radius=10)
        self.cell_green = pill(220, 58, GREEN_BG, radius=10)

    def span(self, text: str, phrase: str, color):
        i = text.find(phrase)
        x0, x1 = self.f.getlength(text[:i]), self.f.getlength(text[:i + len(phrase)])
        return (x0, x1, pill(int(x1 - x0) + 22, 62, color, radius=12))

    def answer(self, fr, t, x, y, op, base, marks, mark_op, text, notes, note_ops):
        blit(fr, base, x, y + 16 * (1 - op), op)
        for x0, x1, sp in marks:
            blit(fr, sp, x + 40 + x0 - 11, y + 52, mark_op * op)
        blit(fr, text, x + 40, y + 50, op)
        nx = x + 40
        for note, v in zip(notes, note_ops):
            blit(fr, note, nx, y + 126 + 8 * (1 - v), v * op)
            nx += note.w + 56

    def draw(self, fr, t, sc):
        blit(fr, self.head, 120, 92, ramp(t, 0.0, 0.6))
        blit(fr, self.q, 120, 206, ramp(t, 0.1, 0.6))
        a = ramp(t, 0.2, 0.6)
        h = ramp(t, sc.at(0, "sees"), 0.5)
        n = ramp(t, sc.at(0, "belongs"), 0.5)
        self.answer(fr, t, 120, 262, a, self.before, self.marks_b, h, self.btext, self.notes_b, (n, n))
        # report extract
        tx, ty = (W - self.table.w) / 2, 482
        ta = ramp(t, 0.6, 0.6)
        tyy = ty + 16 * (1 - ta)
        blit(fr, self.table, tx, tyy, ta)
        cx = [tx + 32 + sum(self.cw[:i]) for i in range(4)]
        r = ramp(t, sc.at(0, "belongs"), 0.5)
        g = ramp(t, sc.at(1) + 0.2, 0.5)
        blit(fr, self.cell_red, cx[3] - 14, tyy + 118, r * ta)
        blit(fr, self.cell_green, cx[1] - 14, tyy + 118, g * ta)
        blit(fr, self.cell_green, cx[2] - 14, tyy + 118, g * ta)
        for i in (1, 2, 3):
            blit(fr, self.vals[i], cx[i], tyy + 122, ta)
        # FaithGuard's answer
        u = ramp(t, sc.at(1) + 0.6, 0.6)
        notes = [ramp(t, sc.at(1, "recalculates"), 0.5), ramp(t, sc.at(1, "shows exactly"), 0.5)]
        self.answer(fr, t, 120, 722, u, self.after, self.marks_a, 1.0, self.atext, self.notes_a, notes)


class Different:
    caption = True

    def __init__(self):
        self.head = heading("What makes it different")
        rows = [("search", "Learns context mistakes from real company filings"),
                ("edit", "Fixes numbers precisely, instead of rewriting answers"),
                ("gauge", "Tests a limit on wrong answers, and says when it is not met"),
                ("chip", "Runs on small, open models and free hardware"),
                ("globe", "A new benchmark of Sri Lankan and US annual reports")]
        self.rows = []
        for kind, text in rows:
            ic = icon(kind, 84, BRONZE, bg=CARD, inner=0.5)
            tx = text_sprite(text, "semibold", 42, NAVY)
            base = Sp(Image.new("RGBA", (84 + 40 + tx.w, 90), (0, 0, 0, 0)))
            self.rows.append(compose(base, [(ic, 0, 3), (tx, 124, 14)]))
        self.x = (W - max(r.w for r in self.rows)) / 2

    def draw(self, fr, t, sc):
        blit(fr, self.head, 120, 92, ramp(t, 0.0, 0.6))
        for i, row in enumerate(self.rows):
            a = ramp(t, sc.at(i + 1) - 0.15, 0.55)
            blit(fr, row, self.x + 36 * (1 - a), 262 + i * 122, a)


class Close:
    caption = False

    def __init__(self):
        self.head = text_sprite("Three parts, one goal", "semibold", 56, NAVY)
        parts = [("search", "Detection", "M.L Ahamed"), ("fork", "Decision policy", "Sharaf"), ("edit", "Repair", "M.S.A Ahamed")]
        self.cards = []
        for kind, title, name in parts:
            c = card(440, 300)
            tt = text_sprite(title, "semibold", 42, NAVY)
            nn = text_sprite(name, "regular", 32, INK2)
            ic = icon(kind, 104, BRONZE, bg=SOFT, inner=0.5)
            self.cards.append(compose(c, [(ic, 220 - 52, 40), (tt, 220 - tt.w // 2, 166), (nn, 220 - nn.w // 2, 226)]))
        self.arrow = arrow(70)
        self.logo = icon("shield", 150, NAVY)
        self.name = text_sprite("FaithGuard", "semibold", 120, NAVY)
        self.tag = text_sprite("The right number, in the right context.", "light", 48, INK2)

    def draw(self, fr, t, sc):
        out = 1 - ramp(t, sc.at(1) - 0.1, 0.5)
        a = ramp(t, 0.0, 0.6)
        blit(fr, self.head, W / 2 - self.head.w / 2, 270, a * out)
        for i, c in enumerate(self.cards):
            b = ramp(t, 0.25 + i * 0.35, 0.55)
            blit(fr, c, 180 + i * 560, 440 + 30 * (1 - b), b * out)
            if i < 2:
                blit(fr, self.arrow, 180 + i * 560 + 450 + 25, 574, out, crop_w=74 * ramp(t, 0.6 + i * 0.35, 0.35))
        f = ramp(t, sc.at(1) + 0.15, 0.8)
        blit(fr, self.logo, W / 2 - self.logo.w / 2, 238 + 20 * (1 - f), f)
        g = ramp(t, sc.at(1) + 0.4, 0.8)
        blit(fr, self.name, W / 2 - self.name.w / 2, 410 + 20 * (1 - g), g)
        k = ramp(t, sc.at(1) + 0.9, 0.8)
        if k > 0:
            ImageDraw.Draw(fr).rounded_rectangle([W / 2 - 110 * k, 600, W / 2 + 110 * k, 605], 3, fill=BRONZE)
        blit(fr, self.tag, W / 2 - self.tag.w / 2, 636 + 16 * (1 - k), k)


SCENES = {"title": Title, "problem": Problem, "why": Why, "flow": Flow, "example": Example, "different": Different, "close": Close}


# ---------------------------------------------------------------- audio and timeline

def decode(path: Path) -> np.ndarray:
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-f", "f32le", "-ac", "1", "-ar", str(SR), "-"],
                         check=True, capture_output=True).stdout
    return np.frombuffer(raw, np.float32)


def timeline(script: dict, audio_dir: Path):
    scenes, clips, t = [], [], 0.0
    for si, sc in enumerate(script["scenes"]):
        start = t
        t += sc["lead"]
        sent = []
        for k, text in enumerate(sc["sentences"]):
            pcm = decode(audio_dir / f"{si:02d}-{k:02d}.mp3")
            d = len(pcm) / SR
            sent.append((t - start, t - start + d, text))
            clips.append((t, pcm))
            t += d + (GAP if k < len(sc["sentences"]) - 1 else 0)
        t += sc["tail"]
        scenes.append(Scene(sc["id"], start, t, sent))
    return scenes, clips, t


def write_audio(clips, total: float, path: Path) -> None:
    out = np.zeros(int(total * SR) + SR, np.float32)
    for t, pcm in clips:
        i = int(t * SR)
        out[i:i + len(pcm)] += pcm
    peak = float(np.abs(out).max()) or 1.0
    out = out * (0.89 / peak)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes((out * 32767).astype(np.int16).tobytes())


# ---------------------------------------------------------------- frames

class Renderer:
    def __init__(self, scenes):
        self.scenes = scenes
        self.objs = {s.id: SCENES[s.id]() for s in scenes}
        self.bg = background()
        self.mark = wordmark()
        self.caps = {(s.id, i): caption(text) for s in scenes for i, (_, _, text) in enumerate(s.sent)}

    def frame(self, t: float) -> Image.Image:
        sc = next((s for s in self.scenes if s.start <= t < s.end), self.scenes[-1])
        lt = t - sc.start
        obj = self.objs[sc.id]
        fr = self.bg.copy()
        obj.draw(fr, lt, sc)
        fade_out = 0.6 if sc.id == "close" else 0.4
        op = min(ramp(lt, 0.0, 0.35), 1 - ramp(lt, sc.dur - fade_out, fade_out))
        if op < 0.999:
            fr = Image.blend(self.bg, fr, op)
        if obj.caption:
            blit(fr, self.mark, W - 80 - self.mark.w, 52, op)
            for i, (s, e, _) in enumerate(sc.sent):
                c = window(lt, s - 0.05, e + 0.25, 0.15)
                if c > 0:
                    cap = self.caps[(sc.id, i)]
                    blit(fr, cap, W / 2 - cap.w / 2, H - 56 - cap.h, c)
        return fr


def main() -> None:
    script_path, audio_dir, out = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
    script = json.loads(script_path.read_text(encoding="utf-8"))
    scenes, clips, total = timeline(script, audio_dir)
    print(f"{total:.1f} s, {len(scenes)} scenes: " + ", ".join(f"{s.id} {s.dur:.1f}" for s in scenes), flush=True)
    r = Renderer(scenes)
    if "--sheet" in sys.argv:
        picks = []
        for s in scenes:
            picks += [s.start + s.dur * 0.55, s.end - 0.5]
        thumbs = [r.frame(t).convert("RGB").resize((640, 360), Image.LANCZOS) for t in picks]
        cols = 3
        sheet = Image.new("RGB", (cols * 640 + (cols + 1) * 8, ((len(thumbs) + cols - 1) // cols) * 368 + 8), (90, 90, 90))
        for i, im in enumerate(thumbs):
            sheet.paste(im, (8 + (i % cols) * 648, 8 + (i // cols) * 368))
        sheet.save(out)
        print("sheet ->", out)
        return
    if "--frames" in sys.argv:  # full-size frames at given times: --frames 12.5,40
        for t in map(float, sys.argv[sys.argv.index("--frames") + 1].split(",")):
            r.frame(t).convert("RGB").save(out.with_name(f"{out.stem}-{t:.1f}.png"))
        return
    wav = out.with_suffix(".wav")
    write_audio(clips, total, wav)
    n = int(math.ceil(total * FPS))
    cmd = ["ffmpeg", "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
           "-i", str(wav), "-map", "0:v", "-map", "1:a", "-c:v", "libx264", "-preset", "medium", "-crf", "18",
           "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", "-shortest", str(out)]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    for i in range(n):
        proc.stdin.write(r.frame(i / FPS).convert("RGB").tobytes())
        if i % 300 == 0:
            print(f"frame {i} of {n}", flush=True)
    proc.stdin.close()
    proc.wait()
    wav.unlink(missing_ok=True)
    print(f"{n} frames -> {out}", flush=True)


if __name__ == "__main__":
    main()
