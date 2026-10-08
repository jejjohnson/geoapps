"""Detection status and analyst verdicts (workstream E, sub-decision E4).

A detection is born ``predicted``. Only a person's verdict moves it, and only
``validated`` rows may flow to attribution, watch rules, persistence and exports.
"""

from enum import StrEnum


class Status(StrEnum):
    PREDICTED = "predicted"
    VALIDATED = "validated"
    REJECTED = "rejected"


class Verdict(StrEnum):
    CONFIRM = "confirm"
    REDRAW = "redraw"
    REJECT = "reject"


def status_after(verdict: Verdict) -> Status:
    """Confirm and redraw validate a detection; reject marks it a false positive."""
    if verdict in (Verdict.CONFIRM, Verdict.REDRAW):
        return Status.VALIDATED
    return Status.REJECTED
