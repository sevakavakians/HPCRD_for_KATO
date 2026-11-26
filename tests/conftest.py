"""Tests run in-process on KATO's own classes. KATO_REPO must name a checkout of KATO.

With KATO_API set (and a KATO_API_TAG the service has not seen), every node lives in a running KATO
service instead, and only the tests marked `through_api` are run: the ones that say the same of both.

    KATO_API=http://127.0.0.1:8000 KATO_API_TAG=check1 .venv/bin/python -m pytest -q
"""
import os

import pytest

os.environ.setdefault('LOG_LEVEL', 'ERROR')


def pytest_configure(config):
    config.addinivalue_line('markers', "through_api: says the same of the in-process node and of a running KATO service")
    if not os.environ.get('KATO_REPO'):
        raise pytest.UsageError("Set KATO_REPO to a checkout of https://github.com/sevakavakians/kato")
    if os.environ.get('KATO_API') and not os.environ.get('KATO_API_TAG'):
        raise pytest.UsageError("Set KATO_API_TAG to a tag this service has not seen: the node ids are made from it")


def pytest_collection_modifyitems(config, items):
    if not os.environ.get('KATO_API'):
        return
    kept = [item for item in items if item.get_closest_marker('through_api')]
    config.hook.pytest_deselected(items=[item for item in items if item not in kept])
    items[:] = kept
