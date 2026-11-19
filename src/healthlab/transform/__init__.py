"""Turn raw Samsung tables into clean HealthLab tables, one module per domain.

Converts times to local time, renames columns to the data dictionary and applies the
content validations.

It does not read files and does not write to the database.
"""
