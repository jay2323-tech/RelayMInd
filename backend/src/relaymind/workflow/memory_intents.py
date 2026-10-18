"""Multi-chat memory M2: intent parsing for save / list / forget / choices / corrections.

Pure functions (no database). Conservative by design: a WRITE is only recognised for an explicit
instruction; questions, quotations, reported speech, negations, hypotheticals, reminders and plan edits are
never memory writes. Unrecognised memory-ish wording becomes a clarifying question, not a guess.

Matching runs on a same-length normalised copy (lowercase, curly quotes/apostrophes -> straight), so spans
map 1:1 back to the ORIGINAL text: saved memories keep the user's exact words.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass
class MemoryIntent:
    kind: str                       # see KINDS
    text: str = ""                  # exact original span (save content / forget target / correction text)
    topic: str = ""                 # list filter
    memory_id: str = ""             # explicit "forget memory mem-..."
    this_chat: bool = False         # "list memories from this conversation"
    note: str = ""


KINDS = {"save", "save_ambiguous", "list", "forget", "forget_ambiguous", "forget_id", "correction", "bulk",
         "scope", "temporary", "retain_ack", "nosave_ack", "combined", "none"}

_MAP = str.maketrans({"’": "'", "‘": "'", "“": '"', "”": '"', "′": "'"})


def normalise(text: str) -> str:
    """Same length as the input (1:1 index mapping)."""
    return text.translate(_MAP).lower()


_LEAD = r"^\s*(?:(?:hi|hello|hey)[,!.]?\s+)?(?:please\s+)?(?:for\s+future\s+reference[,:]?\s+)?(?:please\s+)?"
_END = r"[\s.!]*$"

# ------------------------------------------------------------------ guards (never memory writes)
_QUOTED_TRIGGER = re.compile(r'"[^"]*\b(remember|forget|save|delete|memor\w*|keep\s+this\s+in\s+mind)\b[^"]*"')
_REPORTED = re.compile(r"\b(the\s+document\s+says|an\s+example\s+command|example\s+command|told\s+me\s+to\s+tell\s+you|"
                       r"(she|he|they|my\s+colleague|someone)\s+(told|said|says)|what\s+does\s+.+\s+mean|translate\b|"
                       r"explain\s+the\s+phrase)\b")
_REMINDER = re.compile(r"\bremind\s+me\b|" + _LEAD + r"(remember|don't\s+forget|do\s+not\s+forget|never\s+forget)\s+to\s+\w")
_QUESTION_ABOUT_MEMORY = re.compile(
    r"^\s*(did\s+you\s+forget|have\s+you\s+forgotten|why\s+did\s+you\s+forget|how\s+(do|can)\s+i\s+(delete|remove|"
    r"change|edit|forget)|can\s+i\s+(change|delete|edit)|can\s+you\s+(forget|remember)\s+things|"
    r"what\s+would\s+happen|what\s+happens\s+if)\b")
_OTHER_WORKFLOW = re.compile(r"\b(forget|scrap)\s+the\s+plan\b|\bignore\s+that\s+step\b|\bdelete\s+(this|the)\s+"
                             r"(conversation|chat)\b|\bcancel\s+(my\s+)?reminder\b|\bstart\s+again\b")
_NOSAVE = re.compile(_LEAD + r"(?:(?:don't|do\s+not)\s+(?:remember|save|store)\s+(?:this|that|it)(?!\s+any\s*more)"
                     r"(?:\s+to\s+memory)?|i'm\s+not\s+asking\s+you\s+to\s+remember)\b")
_RETAIN = re.compile(_LEAD + r"(?:(?:don't|do\s+not)\s+forget\s+(?:the|my)\s+\w|(?:don't|do\s+not)\s+delete\s+"
                     r"(?:that|this|the)\s+memory|keep\s+remembering\s+(?:that|this|it)|i\s+(?:don't|do\s+not)\s+"
                     r"want\s+you\s+to\s+forget)")
_BULK = re.compile(_LEAD + r"(?:forget\s+everything|clear\s+all\s+(?:my\s+)?memor|delete\s+all\s+(?:my\s+)?memor|"
                   r"remove\s+all\s+(?:my\s+)?memor|wipe\s+(?:my\s+)?memor)")
_SCOPE = re.compile(r"\b(for\s+everyone|for\s+the\s+(whole\s+)?(company|team)|for\s+every\s+company|"
                    r"colleague'?s\s+memor\w*|other\s+company(\s+account)?|all\s+(my\s+)?companies|other\s+users?)\b")
_TEMPORARY = re.compile(r"\bonly\s+for\s+(the|this)\s+(current\s+)?(conversation|chat)\b|\bjust\s+for\s+this\s+chat\b")

# ------------------------------------------------------------------ save
_SAVE_PATTERNS = [
    _LEAD + r"(?:can|could|would|will)\s+you\s+(?:please\s+)?(?:remember|save|store|note)\s+"
            r"(?:that\s+|this\s+(?:to|in|as)\s+(?:a\s+)?memory\s*[:,-]?\s*)(?P<c>.+?)[\s?.!]*$",
    _LEAD + r"(?:i'd\s+like|i\s+would\s+like|i\s+want|i'd\s+want)\s+you\s+to\s+remember\s+(?:that\s+)?(?P<c>.+?)" + _END,
    _LEAD + r"remember\s+(?:this\s+)?(?:for\s+next\s+time|across\s+(?:our|all\s+our|my)\s+chats|for\s+future\s+chats)"
            r"\s*[:,-]?\s*(?:that\s+)?(?P<c>.+?)" + _END,
    _LEAD + r"remember\s+my\s+preference\s*[:,-]\s*(?P<c>.+?)" + _END,
    _LEAD + r"remember\s*(?:this\s*[:,-]\s*|that\s+|:\s*)(?P<c>.+?)" + _END,
    _LEAD + r"(?:save|store|keep)\s+this\s+(?:to|in|as|into)\s+(?:a\s+)?memory\s*[:,-]?\s*(?P<c>.+?)" + _END,
    _LEAD + r"keep\s+(?:this\s+)?in\s+mind\s*(?:[:,-]\s*|that\s+)(?P<c>.+?)" + _END,
    _LEAD + r"make\s+a\s+note\s+(?:that\s+|of\s+this\s*[:,-]\s*|for\s+future\s+chats\s*[:,-]\s*)(?P<c>.+?)" + _END,
    _LEAD + r"note\s*(?:that\s+|:\s*)(?P<c>.+?)" + _END,
    _LEAD + r"(?:don't|do\s+not)\s+forget\s*(?:that\s+|:\s*)(?P<c>.+?)" + _END,
]
_SAVE_RE = [re.compile(p, re.S) for p in _SAVE_PATTERNS]
_DEMONSTRATIVE = re.compile(r"^(?:this|that|it|this\s+down|that\s+down|what\s+i\s+(?:just\s+)?said|what\s+i\s+told\s+you|"
                            r"everything.*|the\s+last\s+thing|your\s+suggestion|the\s+.*\bthing|all\s+of\s+(?:this|it))"
                            r"[\s.!?]*$")
_SAVE_AMBIGUOUS = re.compile(
    _LEAD + r"(?:remember|save|note|keep)\s+(?:this|that|it|what\s+i\s+(?:just\s+)?said|the\s+last\s+thing\s+in\s+mind|"
    r"this\s+in\s+mind|that\s+in\s+mind|this\s+down|that\s+down|everything(?:\s+\w+)*|the\s+.+?\s+thing|your\s+suggestion)"
    r"(?:\s+in\s+mind)?" + _END + r"|^\s*this\s+is\s+important" + _END + r"|" + _LEAD + r"note\s+this\s+down" + _END)
_PLAN_TAIL = re.compile(r"(?:,\s*|\s+)(?:and\s+)?then\s+(?:plan|build|make|prepare)\b|\band\s+(?:plan|build\s+a\s+plan)\b|"
                        r"\b(?:make|build|prepare)\s+a\s+plan\b|,\s*but\s+don't\s+make\s+a\s+plan")

# ------------------------------------------------------------------ list
_LIST_PATTERNS = [
    r"^\s*what\s+do\s+you\s+remember(?:\s+about\s+(?P<topic>.+?))?[\s?.!]*$",
    r"^\s*what\s+have\s+you\s+(?:remembered|saved|stored)(?:\s+(?:about|on|for)\s+(?P<topic>.+?))?[\s?.!]*$",
    r"^\s*what\s+(?:have|did)\s+i\s+(?:asked|ask|told|tell)\s+you\s+to\s+remember[\s?.!]*$",
    r"^\s*(?:please\s+)?(?:show|list)\s+(?:me\s+)?everything\s+i'?ve\s+asked\s+you\s+to\s+remember[\s?.!]*$",
    r"^\s*(?:please\s+)?(?:show|list)\s+(?:me\s+)?(?:my\s+)?(?:active\s+|saved\s+|remembered\s+)*"
    r"(?:memories|memory|notes|preferences)(?P<chat>\s+from\s+this\s+(?:conversation|chat))?[\s?.!]*$",
    r"^\s*(?:please\s+)?(?:show|list)\s+(?:me\s+)?my\s+saved\s+(?P<topic>.+?)\s+(?:preferences|memories|notes)[\s?.!]*$",
    r"^\s*what(?:'s|\s+is)\s+(?:in\s+your\s+memory|stored\s+in\s+memory)[\s?.!]*$",
    r"^\s*what\s+have\s+you\s+stored\s+for\s+future\s+chats[\s?.!]*$",
    r"^\s*what\s+notes\s+have\s+you\s+saved(?:\s+for\s+me)?[\s?.!]*$",
    r"^\s*do\s+you\s+have\s+anything\s+saved(?:\s+about\s+(?P<topic>.+?))?[\s?.!]*$",
]
_LIST_RE = [re.compile(p) for p in _LIST_PATTERNS]

# ------------------------------------------------------------------ forget
_FORGET_ID = re.compile(r"\b(?:forget|retract|unsave|remove|delete)\s+(?:the\s+)?memory\s+(?P<id>mem-[0-9a-f]{16})\b")
_FORGET_PATTERNS = [
    _LEAD + r"(?:you\s+can\s+)?forget\s+(?:that\s+|about\s+|the\s+memory\s+(?:about|of)\s+|what\s+i\s+told\s+you\s+about\s+)?"
            r"(?P<t>.+?)(?:\s+now)?" + _END,
    _LEAD + r"stop\s+(?:remembering|using\s+(?:my\s+)?(?:old\s+)?)\s*(?P<t>.+?)" + _END,
    _LEAD + r"(?:remove|delete|clear|retract|unsave)\s+(?:the\s+|my\s+)?(?:saved\s+)?(?:memory\s+(?:about|of)\s+)?"
            r"(?P<t>.+?)\s+from\s+(?:my\s+)?memory" + _END,
    _LEAD + r"(?:remove|delete|clear|retract|unsave)\s+(?:the\s+|my\s+)?(?:saved\s+memory|memory)\s+(?:about|of)\s+"
            r"(?P<t>.+?)" + _END,
    _LEAD + r"(?:remove|delete|clear|retract|unsave)\s+(?:the\s+|my\s+)?saved\s+(?P<t>.+?)" + _END,
    _LEAD + r"i\s+no\s+longer\s+want\s+you\s+to\s+remember\s+(?P<t>.+?)" + _END,
    _LEAD + r"(?:don't|do\s+not)\s+(?:remember|use)\s+(?P<t>.+?)\s+any\s*more" + _END,
    r"^\s*(?:that|this)\s+saved\s+(?P<t>\w+)\s+is\s+no\s+longer\s+valid.*$",
]
_FORGET_RE = [re.compile(p, re.S) for p in _FORGET_PATTERNS]
_FORGET_DEMONSTRATIVE = re.compile(r"^(?:that|it|this|that\s+one|this\s+one|them|the\s+old\s+one|the\s+last\s+one|"
                                   r"that\s+memory|this\s+memory|that\s+preference|(?:the\s+)?(?:first|second|third|last)\s+"
                                   r"thing.*)[\s.!]*$")
_FORGET_AMBIGUOUS = re.compile(_LEAD + r"(?:forget|remove|delete)\s+(?:it|that|this|that\s+one|the\s+old\s+one)" + _END)

# ------------------------------------------------------------------ correction
_CORRECTION = re.compile(
    _LEAD + r"(?:actually[,:]?\s+|correction\s*[:,-]\s*|update\s+that\s+memory\s*[:,-]\s*|remember\s+this\s+instead\s*"
    r"[:,-]\s*|replace\s+the\s+old\s+.+?\s+with\s+this\s*[:,-]\s*|change\s+the\s+saved\s+.+?\s+to\s+|"
    r"i\s+was\s+wrong\s+earlier[;,:]\s*|that\s+is\s+outdated[.,;:]\s*(?:remember\s+that\s+)?)(?P<c>.+?)" + _END, re.S)
_COMBINED_FORGET = re.compile(r"\bforget\s+.+?\s+and\s+(?:remember|show|list|save)\b")


def _span(original: str, m: re.Match, group: str) -> str:
    start, end = m.span(group)
    return original[start:end].strip()


def parse(original: str) -> MemoryIntent:
    if not original or not original.strip():
        return MemoryIntent("none")
    t = normalise(original)

    # guards: never writes
    if _QUOTED_TRIGGER.search(t) or _REPORTED.search(t):
        return MemoryIntent("none", note="quoted or reported text is data, not an instruction")
    if _REMINDER.search(t):
        return MemoryIntent("none", note="reminder request, handled by work setup")
    if _QUESTION_ABOUT_MEMORY.search(t) or _OTHER_WORKFLOW.search(t):
        return MemoryIntent("none")
    if _SCOPE.search(t) and re.search(r"\b(remember|memor\w*|forget|save|told\s+you)", t):
        return MemoryIntent("scope")
    if _TEMPORARY.search(t) and re.search(r"\b(remember|memor\w*|save)", t):
        return MemoryIntent("temporary")
    if _BULK.search(t):
        return MemoryIntent("bulk")
    if _NOSAVE.search(t):
        return MemoryIntent("nosave_ack")
    if _RETAIN.search(t):
        return MemoryIntent("retain_ack")
    if m := _FORGET_ID.search(t):
        return MemoryIntent("forget_id", memory_id=m.group("id"))
    if _COMBINED_FORGET.search(t):
        return MemoryIntent("combined", note="forget plus another memory operation")

    for pattern in _LIST_RE:
        if m := pattern.match(t):
            gd = m.groupdict()
            topic = _span(original, m, "topic") if gd.get("topic") else ""
            if topic.lower() in ("me", "myself", "you", "future chats", "future reference", "later"):
                topic = ""
            return MemoryIntent("list", topic=topic, this_chat=bool(gd.get("chat")))

    if m := _CORRECTION.match(t):
        return MemoryIntent("correction", text=_span(original, m, "c"))

    if _FORGET_AMBIGUOUS.match(t):
        return MemoryIntent("forget_ambiguous")
    for index, pattern in enumerate(_FORGET_RE):
        if m := pattern.match(t):
            target = re.sub(r"^(?:the|my|our)\s+", "", _span(original, m, "t"), flags=re.I)
            if index == len(_FORGET_RE) - 1 or _FORGET_DEMONSTRATIVE.match(normalise(target)) or len(target) < 2:
                return MemoryIntent("forget_ambiguous", text=target)   # "that saved X is no longer valid"
            return MemoryIntent("forget", text=target)

    if _SAVE_AMBIGUOUS.match(t):
        return MemoryIntent("save_ambiguous")
    for pattern in _SAVE_RE:
        if m := pattern.match(t):
            content = _span(original, m, "c")
            low = normalise(content)
            if not re.search(r"[a-z]", low) or low.startswith("?") or len(content) < 3:
                return MemoryIntent("none")
            if _DEMONSTRATIVE.match(low):
                return MemoryIntent("save_ambiguous")
            if _PLAN_TAIL.search(low):
                return MemoryIntent("combined", text=content, note="save plus a plan request")
            if "?" in content and not re.match(_LEAD + r"(?:can|could|would|will)\s+you", t):
                return MemoryIntent("none")
            return MemoryIntent("save", text=content.rstrip(" ?"))
    return MemoryIntent("none")


# ------------------------------------------------------------------ replies to a pending choice / confirmation

_ORD = {"first": 1, "one": 1, "second": 2, "two": 2, "third": 3, "three": 3, "fourth": 4, "four": 4,
        "fifth": 5, "five": 5}
_CANCEL = re.compile(r"^\s*(?:neither|none(?:\s+of\s+(?:those|them))?|cancel|never\s*mind|keep\s+(?:them|both|all)|"
                     r"(?:don't|do\s+not)\s+forget\s+anything|no(?:\s+thanks)?|nope|not\s+now|stop)[\s.!]*$")
_YES = re.compile(r"^\s*(?:yes|yeah|yep|yup|sure|ok|okay|please\s+do|go\s+ahead|do\s+it|y|yes\s+please|replace\s+it)[\s.!]*$")
_MULTI = re.compile(r"\b(\d+|first|second|third)\s*(?:,|and|&)\s*(\d+|first|second|third|the\s+\w+)\b|\b(both|all\s+of\s+them)\b")


@dataclass
class ChoiceReply:
    kind: str                     # pick | cancel | multi | yes | unclear
    number: int = 0
    text: str = ""
    extra: dict = field(default_factory=dict)


def parse_choice(original: str, options: list[str]) -> ChoiceReply:
    """Interpret a reply to numbered choices. `options` are the shown excerpts (for 'the one about X')."""
    t = normalise(original).strip()
    if _CANCEL.match(t):
        return ChoiceReply("cancel")
    if _YES.match(t):
        return ChoiceReply("yes")
    if _MULTI.search(t) and not re.search(r"\bkeep\b", t):
        return ChoiceReply("multi")
    m = re.search(r"\bforget\s+(?:the\s+)?(?:number\s+|option\s+|#)?(\d+|first|second|third|fourth|fifth)\b", t)
    if m:                                     # "keep the first one; forget the second"
        v = m.group(1)
        return ChoiceReply("pick", number=int(v) if v.isdigit() else _ORD[v])
    m = re.match(r"^\s*(?:#|number\s+|option\s+|no\.\s*)?(\d{1,2})[\s.!]*$", t)
    if m:
        return ChoiceReply("pick", number=int(m.group(1)))
    m = re.match(r"^\s*(?:the\s+)?(?:number\s+|option\s+)?(first|second|third|fourth|fifth|one|two|three|four|five)"
                 r"(?:\s+(?:one|memory|option|choice))?[\s.!]*$", t)
    if m:
        return ChoiceReply("pick", number=_ORD[m.group(1)])
    m = re.match(r"^\s*(?:the\s+one\s+(?:about|with|on)\s+)(?P<x>.+?)[\s.!]*$", t)
    if m:
        words = [w for w in re.findall(r"[a-z0-9']{3,}", m.group("x"))]
        hits = [i for i, opt in enumerate(options, 1) if words and all(w in normalise(opt) for w in words)]
        if len(hits) == 1:
            return ChoiceReply("pick", number=hits[0])
        return ChoiceReply("unclear")
    return ChoiceReply("unclear")
