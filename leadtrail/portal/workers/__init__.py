"""
Workers Module
==============

This module contains standalone worker scripts that use the schedule library
as an alternative to Celery for background task processing.

Each worker script can be run independently using:
    python leadtrail/portal/workers/<script_name>.py

Workers in this module:
- companies_house_worker.py: Processes Companies House API lookups
"""