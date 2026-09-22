"""The incidents service: reports, workflow, notes, escalations and reporting.

A package rather than top-level modules because pip installs dependencies to
the root of the Lambda zip, where a module called `routes` or `service` could
be shadowed by -- or shadow -- a dependency of the same name.
"""
