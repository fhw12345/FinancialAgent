"""Negative XML fixtures and cache compatibility for PH-004 security gates."""

from unittest.mock import patch

import pytest

from src.agent.tools.sec_edgar.form4 import (
    parse_atom_filing_index_urls,
    parse_form4_detail,
)
from src.services import translation_service


@pytest.mark.parametrize(
    "declaration",
    [
        '<!DOCTYPE feed [<!ENTITY company "unsafe">]>',
        '<!DOCTYPE feed SYSTEM "https://attacker.invalid/schema.dtd">',
    ],
)
def test_atom_rejects_all_dtds(declaration):
    body = (
        declaration
        + '<feed><entry><link href="https://www.sec.gov/test"/></entry></feed>'
    )
    assert parse_atom_filing_index_urls(body) == []


def test_detail_rejects_entity_expansion():
    body = """<!DOCTYPE ownershipDocument [<!ENTITY company "unsafe">]>
    <ownershipDocument><issuerTradingSymbol>&company;</issuerTradingSymbol>
    <nonDerivativeTransaction/></ownershipDocument>"""
    assert parse_form4_detail(body) == []


def test_external_entity_rejected_without_file_or_network_read():
    body = """<!DOCTYPE ownershipDocument [<!ENTITY ext SYSTEM "file:///etc/passwd">]>
    <ownershipDocument><issuerTradingSymbol>&ext;</issuerTradingSymbol>
    <nonDerivativeTransaction/></ownershipDocument>"""
    assert parse_form4_detail(body) == []


def test_cache_sha1_is_non_security_and_keeps_existing_keys():
    with patch.object(
        translation_service.hashlib, "sha1", wraps=translation_service.hashlib.sha1
    ) as sha1:
        key = translation_service._cache_key("hello", "zh-CN")
    sha1.assert_called_once_with(b"hello", usedforsecurity=False)
    assert key.endswith(":zh-CN:aaf4c61ddcc5e8a2dabede0f3b482cd9aea9434d")
