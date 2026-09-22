"""The auth service: sign-in, sessions, and user administration.

A package rather than top-level modules because pip installs dependencies to
the root of the Lambda zip, where a module called `routes` or `service` could
be shadowed by -- or shadow -- a dependency of the same name.
"""
