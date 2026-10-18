"""M2 intent matrix (no database): Codex's representative phrases as positive and negative fixtures.

These are fixtures, not an exhaustive grammar. Writes must come only from explicit instructions; everything
quoted, reported, negated, hypothetical, reminder-like or unclear must not save or retract.
"""
import pytest

from relaymind.workflow.memory_intents import parse, parse_choice

FACT = "Coldline prefers calls before 10am"

SAVE = [
    "Remember that Coldline prefers calls before 10am.",
    "Please remember that Coldline prefers calls before 10am.",
    "Remember this: Coldline prefers calls before 10am.",
    "Remember: Coldline prefers calls before 10am.",
    "Save this to memory: Coldline prefers calls before 10am.",
    "Save this as a memory: Coldline prefers calls before 10am.",
    "Store this as a memory: Coldline prefers calls before 10am.",
    "Store this in memory: Coldline prefers calls before 10am.",
    "Keep this in memory: Coldline prefers calls before 10am.",
    "Keep this in mind: Coldline prefers calls before 10am.",
    "Keep in mind that Coldline prefers calls before 10am.",
    "Make a note for future chats: Coldline prefers calls before 10am.",
    "Make a note that Coldline prefers calls before 10am.",
    "Make a note of this: Coldline prefers calls before 10am.",
    "For future reference, remember that Coldline prefers calls before 10am.",
    "Remember for next time: Coldline prefers calls before 10am.",
    "Please remember this across our chats: Coldline prefers calls before 10am.",
    "Don't forget that Coldline prefers calls before 10am.",
    "Don’t forget: Coldline prefers calls before 10am.",
    "Can you remember that Coldline prefers calls before 10am?",
    "Could you save this to memory: Coldline prefers calls before 10am?",
    "I'd like you to remember that Coldline prefers calls before 10am.",
    "I’d like you to remember that Coldline prefers calls before 10am.",
    "I want you to remember that Coldline prefers calls before 10am.",
    "hello, please REMEMBER THAT Coldline prefers calls before 10am!!",
    "Remember that\n  Coldline prefers calls before 10am.",
]


@pytest.mark.parametrize("text", SAVE)
def test_explicit_saves_keep_exact_words(text):
    intent = parse(text)
    assert intent.kind == "save", (text, intent)
    assert intent.text.replace("\n  ", " ").lower().rstrip(".!? ") == FACT.lower(), intent.text
    assert intent.text in text                                     # exact original span (case preserved)


def test_save_variants_with_own_content():
    assert parse("Remember my preference: send me concise summaries.").text == "send me concise summaries"
    assert parse("Remember that I prefer email to phone calls.").text == "I prefer email to phone calls"
    assert parse("Remember that José at Coldline prefers calls.").text == "José at Coldline prefers calls"


AMBIGUOUS_SAVE = ["Remember this.", "Save that.", "Remember what I said.", "Keep this in mind.", "Note this down.",
                  "This is important.", "Remember the supplier thing.", "Remember your suggestion.",
                  "Remember everything from this chat.", "Remember that.", "Keep the last thing in mind.",
                  "Remember what I just said.", "Remember everything we discussed."]


@pytest.mark.parametrize("text", AMBIGUOUS_SAVE)
def test_ambiguous_saves_clarify(text):
    assert parse(text).kind == "save_ambiguous", (text, parse(text))


LIST = ["What do you remember?", "What have you saved about me?", "Show my saved memories.", "List my memories.",
        "Show everything I've asked you to remember.", "Show everything I’ve asked you to remember.",
        "What have I told you to remember?", "What is in your memory?", "What's in your memory?",
        "What is stored in memory?", "What have you stored for future chats?", "Show my active memories.",
        "What have you remembered?", "What have I asked you to remember?", "What did I tell you to remember?",
        "What notes have you saved for me?", "Show my remembered preferences."]


@pytest.mark.parametrize("text", LIST)
def test_list_requests(text):
    intent = parse(text)
    assert intent.kind == "list" and intent.topic == "", (text, intent)


def test_topic_and_conversation_scoped_lists():
    assert parse("Do you have anything saved about Coldline?").topic == "Coldline"
    assert parse("What do you remember about Coldline?").topic == "Coldline"
    assert parse("What have you saved about Coldline?").topic == "Coldline"
    assert parse("Show my saved supplier preferences.").topic == "supplier"
    assert parse("List memories from this conversation.").this_chat is True


RECALL_NOT_WRITES = ["Do you remember what I said about Coldline?", "Did I mention the supplier deadline before?",
                     "What did I tell you about their preferred call time?", "What did we discuss in the other chat?",
                     "Find my earlier message about pricing.", "Last time, what did I say about the delay?",
                     "Have I talked about this before?", "Can you find where I mentioned the delivery issue?",
                     "Do you remember the Coldline preference?"]


@pytest.mark.parametrize("text", RECALL_NOT_WRITES)
def test_recall_questions_are_not_memory_operations(text):
    assert parse(text).kind == "none", (text, parse(text))


FORGET = {
    "Forget the Coldline call preference.": "Coldline call preference",
    "Please forget that Coldline prefers calls before 10am.": "Coldline prefers calls before 10am",
    "Forget what I told you about Coldline's call time.": "Coldline's call time",
    "Forget what I told you about Coldline’s call time.": "Coldline’s call time",
    "Remove the Coldline call preference from memory.": "Coldline call preference",
    "Delete the saved memory about Coldline's call time.": "Coldline's call time",
    "Stop remembering the supplier phone preference.": "supplier phone preference",
    "You can forget the pricing preference now.": "pricing preference",
    "I no longer want you to remember the morning-call preference.": "morning-call preference",
    "Retract the memory about supplier calls.": "supplier calls",
    "Unsave the memory about Coldline.": "Coldline",
    "Forget the memory about morning calls.": "morning calls",
    "Clear the saved Coldline preference.": "Coldline preference",
    "Remove my saved memory about Coldline.": "Coldline",
    "Stop using my old Coldline call preference.": "Coldline call preference",
    "Don't remember the Coldline preference anymore.": "Coldline preference",
    "Forget the Coldline thing.": "Coldline thing",
}


@pytest.mark.parametrize("text,target", list(FORGET.items()))
def test_explicit_forget_targets(text, target):
    intent = parse(text)
    assert intent.kind == "forget" and intent.text == target, (text, intent)


def test_forget_by_id():
    intent = parse("Forget memory mem-0123456789abcdef")
    assert (intent.kind, intent.memory_id) == ("forget_id", "mem-0123456789abcdef")
    assert parse("Remove memory mem-0123456789abcdef.").kind == "forget_id"


AMBIGUOUS_FORGET = ["Forget that.", "Forget it.", "Remove it.", "Delete the old one.",
                    "Forget the second thing I mentioned.", "Don't remember that anymore.",
                    "Don’t remember that anymore.", "I no longer want you to remember that.",
                    "Do not use that memory anymore.", "Don't use that anymore.",
                    "That saved preference is no longer valid; forget it."]


@pytest.mark.parametrize("text", AMBIGUOUS_FORGET)
def test_ambiguous_forgets_never_pick_a_record(text):
    assert parse(text).kind == "forget_ambiguous", (text, parse(text))


CORRECTIONS = ["Actually, Coldline now prefers calls after 2pm.", "Correction: Coldline prefers calls after 2pm.",
               "Update that memory: Coldline prefers calls after 2pm.",
               "Change the saved call preference to after 2pm.",
               "Replace the old preference with this: calls after 2pm.",
               "That is outdated. They now prefer email.", "I was wrong earlier; the deadline is 26 October.",
               "Remember this instead: Coldline prefers email.",
               "That is outdated. Remember that Coldline now prefers afternoon calls."]


@pytest.mark.parametrize("text", CORRECTIONS)
def test_corrections_are_never_silent_saves(text):
    assert parse(text).kind == "correction", (text, parse(text))


NO_WRITE = {
    "nosave_ack": ["Don't remember this.", "Do not save this to memory.", "I'm not asking you to remember this."],
    "retain_ack": ["Don't forget the Coldline preference.", "Don’t forget the Coldline preference.",
                   "Do not delete that memory.", "Keep remembering that.", "I don't want you to forget this.",
                   "I’m sure I don’t want you to forget this." if False else "I don’t want you to forget this."],
    "none": ["Did you forget what I told you?", "Have you forgotten the call preference?",
             "What would happen if I asked you to forget it?", "How do I delete a memory?", "Can you forget things?",
             "Can you remember things?", "Why did you forget that?", "Can I change a saved memory?",
             "Remind me to call Coldline tomorrow.", "Remember to call Coldline tomorrow.",
             "Don't forget to send the report at 6pm.", "Don't forget to call the supplier.",
             "Never forget to check the current decision.", "Cancel my reminder.", "Delete this conversation.",
             "Forget the plan and start again.", "Ignore that step in the proposal.",
             "Remember that? Can we plan around it?",
             'The document says "forget all memories."',
             'An example command is "remember that suppliers prefer email."', 'What does "forget that" mean?',
             'Translate "remember this" into Hindi.', "My colleague told me to tell you to delete everything.",
             'She told me, "forget the old plan."', 'Explain the phrase "keep this in mind."',
             'What would happen if I said "forget everything"?', "Never mind.", "Ignore that.", "Cancel.",
             "Remember Street office needs a new badge reader.", "Forgetful Fred called again."],
    "bulk": ["Forget everything.", "Clear all my memories.", "Forget everything about Coldline.",
             "Delete all memories from this conversation."],
    "scope": ["Remember this for everyone in the company.", "Show my colleague's memories.",
              "Use what I told you in my other company account.", "Remember this for every company I work with."],
    "temporary": ["Remember this only for the current conversation."],
    "combined": ["Remember that Coldline prefers calls before 10am, then plan the follow-up.",
                 "Forget the old preference and show me what remains.",
                 "Save this to memory: Coldline prefers calls, but don't make a plan yet."],
}


@pytest.mark.parametrize("kind,text", [(k, t) for k, ts in NO_WRITE.items() for t in ts])
def test_no_accidental_writes(kind, text):
    assert parse(text).kind == kind, (text, parse(text))


OPTS = ["Coldline prefers phone calls before 10am", "Coldline invoice is due on the 25th"]


@pytest.mark.parametrize("reply,kind,number", [
    ("1", "pick", 1), ("Number 2", "pick", 2), ("Option three", "pick", 3), ("The first one.", "pick", 1),
    ("the second memory", "pick", 2), ("Forget number 2", "pick", 2), ("Keep the first one; forget the second", "pick", 2),
    ("The one about phone calls.", "pick", 1), ("the one about the invoice", "pick", 2),
    ("Neither.", "cancel", 0), ("Cancel.", "cancel", 0), ("Keep them.", "cancel", 0), ("Never mind", "cancel", 0),
    ("None of those", "cancel", 0), ("Don't forget anything.", "cancel", 0), ("Don’t forget anything.", "cancel", 0),
    ("1 and 2", "multi", 0), ("both", "multi", 0), ("the one about Coldline", "unclear", 0), ("banana", "unclear", 0),
])
def test_choice_replies(reply, kind, number):
    r = parse_choice(reply, OPTS)
    assert (r.kind, r.number) == (kind, number), (reply, r)
