# __init__.py

# Version of the frankAllSkyCam - read from the installed package's own
# metadata (single source of truth: pyproject.toml's [project] version) so
# this can never drift out of sync with what pip actually installed, the
# way a hand-maintained string here previously did (stuck at "19" through
# five subsequent releases).
from importlib.metadata import version, PackageNotFoundError

try:
    __version__ = version("frankAllSkyCam")
except PackageNotFoundError:
    __version__ = "unknown"
