import logging
from importlib.metadata import PackageNotFoundError, version as _dist_version

try:
    __version__ = _dist_version("SpySWAT")
except PackageNotFoundError:  # running from a source checkout that is not installed
    __version__ = "0+unknown"

__author__ = 'Sondayyyy'



from spyswat.swat_project import SWATProject

__all__ = [
    'SWATProject'
]

logging.getLogger(__name__).addHandler(logging.NullHandler())
logging.getLogger('matplotlib').setLevel(logging.WARNING)
