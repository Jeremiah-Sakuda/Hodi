"""
tests/offline_env.py — declare the credential-free mode without clobbering it
for everyone else.

WHY THIS EXISTS. Almost every test in this suite needs `HODI_OFFLINE=1`, and
each one used to do:

    os.environ["HODI_OFFLINE"] = "1"
    self.addCleanup(lambda: os.environ.pop("HODI_OFFLINE", None))

`make test` sets `HODI_OFFLINE=1` for the WHOLE run, so that cleanup did not
restore the previous state — it deleted a variable the suite depends on. The
first such test to finish silently un-declared offline mode for every test
that ran after it.

That was invisible while the gateway failed OPEN on a missing Firestore
client: a test that had lost the flag just got the same in-memory path by
accident. The moment storage began failing CLOSED (HOD-716), eight tests
started erroring — not because the fail-closed change was wrong, but because
it removed the fallback that had been hiding the pollution. Save and restore;
never pop what you did not set.
"""

import os

FLAG = "HODI_OFFLINE"


def force_offline(case, value: str = "1") -> None:
    """
    Declare the credential-free mode for the duration of one test, restoring
    whatever the environment held before — including the common case where
    the suite runner had already set it.
    """
    prior = os.environ.get(FLAG)
    os.environ[FLAG] = value
    case.addCleanup(_restorer(prior))


def force_online(case) -> None:
    """
    The inverse, for tests that must exercise the NOT-offline path (the
    fail-closed suite). Same restore discipline.
    """
    prior = os.environ.get(FLAG)
    os.environ.pop(FLAG, None)
    case.addCleanup(_restorer(prior))


def _restorer(prior):
    def restore():
        if prior is None:
            os.environ.pop(FLAG, None)
        else:
            os.environ[FLAG] = prior
    return restore
