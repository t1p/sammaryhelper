"""Tests for mcp_archive_server/db.py"""

import pytest

from mcp_archive_server.db import ArchiveConfig, parse_lazgram_cache_enabled


def test_parse_lazgram_cache_enabled_true_variants():
    assert parse_lazgram_cache_enabled("true") is True
    assert parse_lazgram_cache_enabled("True") is True
    assert parse_lazgram_cache_enabled("1") is True
    assert parse_lazgram_cache_enabled("yes") is True


def test_parse_lazgram_cache_enabled_false_variants():
    assert parse_lazgram_cache_enabled("false") is False
    assert parse_lazgram_cache_enabled("False") is False
    assert parse_lazgram_cache_enabled("0") is False
    assert parse_lazgram_cache_enabled("no") is False


def test_parse_lazgram_cache_enabled_default():
    assert parse_lazgram_cache_enabled(None) is True
    assert parse_lazgram_cache_enabled("") is True


def test_parse_lazgram_cache_enabled_unknown_defaults_to_false():
    assert parse_lazgram_cache_enabled("maybe") is False
    assert parse_lazgram_cache_enabled("invalid") is False


def test_archive_config_default_cache_enabled():
    config = ArchiveConfig()
    assert config.lazgram_cache_enabled is True


def test_archive_config_from_bool():
    config = ArchiveConfig(lazgram_cache_enabled=False)
    assert config.lazgram_cache_enabled is False

    config = ArchiveConfig(lazgram_cache_enabled=True)
    assert config.lazgram_cache_enabled is True
