"""Tests run in-process on KATO's own classes. KATO_REPO must name a checkout of KATO."""
import os

import pytest

os.environ.setdefault('LOG_LEVEL', 'ERROR')


def pytest_configure(config):
    if not os.environ.get('KATO_REPO'):
        raise pytest.UsageError("Set KATO_REPO to a checkout of https://github.com/sevakavakians/kato")
    if os.environ.get('KATO_API'):
        raise pytest.UsageError("Unset KATO_API: the tests check the in-process nodes")
