# Workers Module

This directory contains standalone worker scripts using the `schedule` library as an alternative to Celery-based background tasks.

## Purpose

These workers provide a simpler alternative to Celery for background processing:
- No need for Redis/broker setup
- Direct Python script execution
- Built-in scheduling with the `schedule` library
- Easier debugging and monitoring

## Usage

Each worker script can be run directly:

```bash
# Run Companies House lookup worker
python leadtrail/portal/workers/companies_house_worker.py

# Run VAT lookup worker
python leadtrail/portal/workers/vat_lookup_worker.py

# Run website hunting worker
python leadtrail/portal/workers/website_hunting_worker.py

# Run LinkedIn finder worker
python leadtrail/portal/workers/linkedin_finder_worker.py
```

## Worker Scripts

### companies_house_worker.py
- **Purpose**: Processes Companies House API lookups for unprocessed company numbers
- **Schedule**: Every 10 seconds
- **Batch Size**: 100 companies per run (configurable via `COMPANIES_HOUSE_BATCH_SIZE` env var)

### vat_lookup_worker.py
- **Purpose**: Processes VAT lookups for companies that completed Companies House processing
- **Schedule**: Every 10 seconds
- **Batch Size**: 10 companies per run (configurable via `VAT_LOOKUP_BATCH_SIZE` env var)

### website_hunting_worker.py
- **Purpose**: Performs website hunting using SERP discovery + website crawling for domain ranking
- **Schedule**: Every 3 minutes
- **Batch Size**: 5 companies per run

### linkedin_finder_worker.py
- **Purpose**: Searches for LinkedIn company pages and employee profiles for companies in enabled campaigns
- **Schedule**: Every 5 minutes
- **Batch Size**: 3 companies per run

## Migration from Celery

During the transition period:
- Celery tasks remain in `leadtrail/portal/tasks/`
- New schedule-based workers are in this directory
- Both can coexist until fully migrated

## Dependencies

Make sure to install the `schedule` library:
```bash
pip install schedule
```