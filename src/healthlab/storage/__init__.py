"""Own the database: schema, merge, backups, change history and the import log.

Applies the four merge rules and is the only layer that changes detail tables.

It computes no metrics and knows nothing about Samsung file formats.
"""
