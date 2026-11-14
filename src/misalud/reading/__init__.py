"""Read a Samsung Health export: open the archive, parse CSV and JSON files.

Compares each file with its contract and reports what is missing, extra or retyped.

It knows nothing about the database and never writes to disk outside a temporary folder.
"""
