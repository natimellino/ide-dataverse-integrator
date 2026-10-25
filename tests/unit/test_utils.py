import hashlib
from pathlib import Path

import pytest

from ide_dataverse_integrator.utils import clean_url, compute_md5, extract_uri_slug


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("", ""),
        (None, ""),
        ("https://ide.rosario.gob.ar", "https://ide.rosario.gob.ar"),
        ("http://ide.rosario.gob.ar", "http://ide.rosario.gob.ar"),
        ("ide.rosario.gob.ar", "https://ide.rosario.gob.ar"),
        ("http:///ide.rosario.gob.ar", "https://ide.rosario.gob.ar"),
    ],
)
def test_clean_url(value, expected):
    assert clean_url(value) == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("http://publications.europa.eu/resource/authority/language/ENG", "ENG"),
        ("dataset", "dataset"),
        ("", ""),
        (None, ""),
    ],
)
def test_extract_uri_slug(value, expected):
    assert extract_uri_slug(value) == expected


class TestComputeMd5:
    def test_matches_reference_hash(self, tmp_path: Path):
        payload = b"hola geoserver\n"
        file = tmp_path / "layer.tif"
        file.write_bytes(payload)

        assert compute_md5(file) == hashlib.md5(payload).hexdigest()

    def test_streams_in_chunks(self, tmp_path: Path):
        # Archivo mayor al chunk_size: ejercita el loop de lectura.
        file = tmp_path / "big.bin"
        file.write_bytes(b"x" * (3 * 1024))

        expected = hashlib.md5(b"x" * (3 * 1024)).hexdigest()
        assert compute_md5(file, chunk_size=1024) == expected

    def test_empty_file(self, tmp_path: Path):
        file = tmp_path / "empty.bin"
        file.write_bytes(b"")

        assert compute_md5(file) == hashlib.md5(b"").hexdigest()
