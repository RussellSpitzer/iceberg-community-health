# SPDX-License-Identifier: Apache-2.0

"""Rough lexicon tone label for public dev-list text.

The word lists describe tone, not technical content, so a plain bug report
with a stack trace is neutral. This is not a validated sentiment model.
"""

from __future__ import annotations

import re

BODY_CHARS = 2000
NEGATION_REACH = 3

_POSITIVE = {
    "thanks": 1,
    "thank": 1,
    "thankful": 1,
    "appreciate": 1,
    "appreciated": 1,
    "great": 1,
    "good": 1,
    "nice": 1,
    "awesome": 2,
    "excellent": 2,
    "fantastic": 2,
    "wonderful": 2,
    "amazing": 2,
    "brilliant": 2,
    "impressive": 1,
    "love": 1,
    "glad": 1,
    "happy": 1,
    "pleased": 1,
    "excited": 1,
    "exciting": 1,
    "welcome": 1,
    "congrats": 2,
    "congratulations": 2,
    "kudos": 2,
    "helpful": 1,
    "agree": 1,
    "support": 1,
    "supportive": 1,
    "perfect": 1,
    "cool": 1,
    "+1": 1,
}

_NEGATIVE = {
    "terrible": 2,
    "awful": 2,
    "horrible": 2,
    "ridiculous": 2,
    "unacceptable": 2,
    "useless": 2,
    "garbage": 2,
    "stupid": 2,
    "nonsense": 2,
    "pathetic": 2,
    "absurd": 2,
    "insulting": 2,
    "disrespectful": 2,
    "rude": 2,
    "hate": 2,
    "worst": 2,
    "angry": 2,
    "frustrating": 1,
    "frustrated": 1,
    "annoying": 1,
    "annoyed": 1,
    "disappointed": 1,
    "disappointing": 1,
    "sloppy": 1,
    "careless": 1,
    "waste": 1,
    "ignored": 1,
    "embarrassing": 1,
    "unfortunately": 1,
    "confusing": 1,
    "disagree": 1,
    "concerned": 1,
    "worried": 1,
    "bad": 1,
    "-1": 1,
}

_NEGATIONS = {
    "not",
    "no",
    "never",
    "nor",
    "without",
    "hardly",
    "cannot",
    "don't",
    "doesn't",
    "didn't",
    "isn't",
    "wasn't",
    "aren't",
    "can't",
    "won't",
    "wouldn't",
    "shouldn't",
}

_TOKEN = re.compile(r"(?<![\w+-])[+-]1(?!\d)|[a-z]+(?:'[a-z]+)?|[.!?;:]")
_BOUNDARY = set(".!?;:")
_SUBJECT_TAG = re.compile(r"^\s*(?:(?:re|fwd?)\s*:\s*|\[[^\]]*\]\s*)+", re.IGNORECASE)
_ATTRIBUTION = re.compile(r"(?m)^[ \t]*On [^\n]*(?:\n[^\n]*){0,2}?wrote:[ \t]*$")
_SIGN_OFF = re.compile(
    r"^\s*(?:many\s+)?(?:thanks|thank you|thx|regards|best regards|kind regards|best|cheers)"
    r"(?:\s+(?:again|all|everyone))?\s*[,.!]?\s*$",
    re.IGNORECASE,
)


def clean_subject(subject: str | None) -> str:
    return _SUBJECT_TAG.sub("", subject or "").strip()


def clean_body(body: str | None, limit: int = BODY_CHARS) -> str:
    """The message's own words: quoted replies, attributions, sign-offs, and the signature are dropped."""
    kept = []
    for line in _ATTRIBUTION.sub("", body or "").splitlines():
        if line.rstrip() in {"--", "-- "}:
            break
        stripped = line.strip()
        if stripped.startswith(">") or _SIGN_OFF.match(stripped):
            continue
        kept.append(stripped)
    return " ".join(part for part in kept if part)[:limit]


def score(text: str) -> tuple[int, int]:
    """Return the signed lexicon score and the number of word tokens.

    A negation flips the next few words only within the same sentence.
    """
    tokens = _TOKEN.findall(text.lower().replace("\u2019", "'"))
    total = 0
    words = 0
    since_negation = None
    for token in tokens:
        if token in _BOUNDARY:
            since_negation = None
            continue
        words += 1
        if token in _NEGATIONS:
            since_negation = 0
            continue
        if since_negation is not None:
            since_negation += 1
            if since_negation > NEGATION_REACH:
                since_negation = None
        weight = _POSITIVE.get(token, 0) - _NEGATIVE.get(token, 0)
        if weight and since_negation is not None:
            weight = -weight
        total += weight
    return total, words


def label(subject: str | None, body: str | None) -> str | None:
    """`positive`, `neutral`, or `negative`, or None when there is no text to classify."""
    total, words = score(f"{clean_subject(subject)} {clean_body(body)}")
    if words == 0:
        return None
    if total > 0:
        return "positive"
    if total < 0:
        return "negative"
    return "neutral"
