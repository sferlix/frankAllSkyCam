# __init__.py

# Version of frankAllSkyCam, read from the installed package metadata (the
# pyproject.toml [project] version)
from importlib.metadata import version, PackageNotFoundError

try:
    __version__ = version("frankAllSkyCam")
except PackageNotFoundError:
    __version__ = "unknown"
