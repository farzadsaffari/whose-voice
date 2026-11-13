"""What the agent may do, given the voice check.

The voice is one key, never the only key to money: a recording or a clone of the
owner's voice can pass any voice threshold."""

PUBLIC, LOW, PRIVATE, MONEY = 0, 1, 2, 3
RISK = {"time": PUBLIC, "weather": PUBLIC, "calendar": LOW, "who_messaged": LOW,
        "read_messages": PRIVATE, "send_email": PRIVATE, "book_meeting": PRIVATE, "pay": MONEY}
MAX_FAILURES = 3


def next_step(action, voice, failures=0, phrase_asked=False):
    """voice = the strictest limit the score passed: 'private', 'low-risk', 'unsure' or 'reject'."""
    risk = RISK[action]
    if risk == PUBLIC:
        return "do it"
    if risk == MONEY or failures >= MAX_FAILURES:
        return "confirm on phone"               # always for money; after 3 failures the owner is also notified
    if voice == "private" or (voice == "low-risk" and risk == LOW):
        return "do it"
    if voice == "reject":
        return "ask to say it again"            # never say why: that would coach an attacker
    if not phrase_asked:
        return "ask to repeat a random phrase"  # said in the ear, so a prepared recording can't contain it
    return "confirm on phone"
