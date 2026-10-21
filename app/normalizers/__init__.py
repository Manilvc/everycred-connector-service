"""Response normalizers, one module per source format.

Importing this package imports every normalizer module, which registers
it. Add new modules to the import list below.
"""

from app.normalizers import everycred_dcs  # noqa: F401 - registers itself
