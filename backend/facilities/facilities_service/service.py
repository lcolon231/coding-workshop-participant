"""The facilities service's rules: what an admin may create, change and remove.

Routes stay thin: they parse, call one function here, and shape the response.
Every decision -- who may see a retired record, which reference must exist,
when a delete is refused because something still depends on the row -- is in
this module, where it can be read in one place and pinned by the tests.
"""

from __future__ import annotations
