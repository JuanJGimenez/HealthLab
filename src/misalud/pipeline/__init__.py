"""Run an import from start to finish, coordinating the layers below.

Sequence: read, validate, load into a staging database, preview, back up, merge,
rebuild derived tables, log.

It holds no parsing, merge or calculation logic of its own.
"""
