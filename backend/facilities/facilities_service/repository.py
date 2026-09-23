"""Every query the facilities service runs.

Rows are selected, then changed as ORM objects, so each mutation is visible in
one place and nothing bypasses the unit of work (S6). Nothing here decides
who may see what: the service passes the visibility it has already computed.
"""

from __future__ import annotations
