"""The worked examples print exactly examples/report.txt.

The same report was printed with every node in a running KATO service (main at f32bac0)
on 24 Nov 2026, so this pins the in-process nodes to what KATO returned then.
"""
import hashlib
import io
import pathlib
from contextlib import redirect_stdout

from examples import worked_examples

REPORT = pathlib.Path(__file__).resolve().parent.parent / 'examples' / 'report.txt'


def printed():
    buffer = io.StringIO()
    with redirect_stdout(buffer):
        for run in worked_examples.EXAMPLES.values():
            run()
    return buffer.getvalue()


def test_report_is_reproduced():
    assert printed() == REPORT.read_text()


def test_report_digest_is_recorded_in_the_readme():
    digest = hashlib.sha1(REPORT.read_bytes()).hexdigest()
    readme = (REPORT.parent.parent / 'README.md').read_text()
    assert digest in readme
