import hashlib
import logging
from pathlib import Path


def configure_logging(verbose: bool = False) -> None:
    """Configura el logging raíz para la CLI."""
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )


def clean_url(url_val: str) -> str:
    """
    Limpia un URI y lo devuelve como string.
    
    Args:
        url_val (str): URI a limpiar.
    
    Returns:
        str: URI limpio.
    """
    if not url_val:
        return ""
    val = str(url_val).split("/")[-1] if "///" in str(url_val) else str(url_val)
    if not val.startswith(("http://", "https://")):
        val = "https://" + val
    return val

def extract_uri_slug(val: str) -> str:
    """
    Extrae el último fragmento de un URI.

    Args:
        val (str): URI a extraer.

    Returns:
        str: Último fragmento del URI.
    """
    return str(val).split("/")[-1] if val else ""


def compute_md5(path: Path, chunk_size: int = 1024 * 1024) -> str:
    """Calcula el hash MD5 de un archivo leyendo en bloques."""
    digest = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()
