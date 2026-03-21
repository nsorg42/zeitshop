"""zeitshop_converter package."""

from importlib.metadata import PackageNotFoundError, version

from .conversion import convert_diamond_file

__all__ = ["__version__", "convert_diamond_file"]

try:
    __version__ = version("zeitshop-converter")
except PackageNotFoundError:  # pragma: no cover - fallback for local source execution
    __version__ = "0.1.0"
