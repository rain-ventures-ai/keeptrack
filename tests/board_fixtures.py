"""Helpers for loading frozen boards from tests/fixtures/."""
import os
import shutil

HERE = os.path.dirname(os.path.abspath(__file__))
FIXTURES = os.path.join(HERE, "fixtures")
_IGNORE_META = shutil.ignore_patterns("fixture.json")


def copy_board_fixture(name, dest):
    shutil.copytree(os.path.join(FIXTURES, name), dest, ignore=_IGNORE_META)
