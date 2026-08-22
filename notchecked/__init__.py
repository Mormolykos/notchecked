"""notchecked - coverage accounting for validators that refuse to lie.

Three states, not two: what was checked, what could not be checked, and what was
never in scope. Six terminal states once you account for who owns the gap and
whether it can ever move.

    from notchecked import Coverage, Record, Report, Reason, Vocabulary

    vocab = Vocabulary([
        Reason("no_scale", Coverage.NOT_CHECKED_DATA_DEGENERATE,
               "median gradient norm is zero - nothing to measure a spike against"),
        Reason("not_requested", Coverage.OUT_OF_SCOPE_CALLER,
               "no --module given"),
    ])

    report = Report(tool="trainproof", vocabulary=vocab)
    report.add(Record("loss-shape", Coverage.CHECKED, verdict="PASS"))
    report.add(Record("grad-spike", Coverage.NOT_CHECKED_DATA_DEGENERATE,
                      reason="no_scale"))
    report.add(Record("import", Coverage.OUT_OF_SCOPE_CALLER,
                      reason="not_requested"))

    print(report.render())
    raise SystemExit(report.exit_code)   # 2 - checked, but not completely

MIT. The four-state split and the caller-versus-data ownership axis are
Panagiotis Gkilis's; the fixed reason vocabulary, counts derived from rows, and
the permanence split on OUT_OF_SCOPE / DATA are Boris Teplitsky's.
"""

from .record import Reason, Record, Vocabulary, VocabularyError
from .report import (
    EXIT_COVERAGE_INCOMPLETE,
    EXIT_OK,
    EXIT_VERDICT_FAILED,
    SCHEMA,
    Report,
)
from .states import Coverage, Owner, Permanence, StateMeta

__version__ = "0.1.0"

__all__ = [
    "Coverage",
    "Owner",
    "Permanence",
    "StateMeta",
    "Reason",
    "Record",
    "Vocabulary",
    "VocabularyError",
    "Report",
    "SCHEMA",
    "EXIT_OK",
    "EXIT_VERDICT_FAILED",
    "EXIT_COVERAGE_INCOMPLETE",
    "__version__",
]
