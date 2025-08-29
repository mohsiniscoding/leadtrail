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
```

## Worker Scripts

### companies_house_worker.py
- **Purpose**: Processes Companies House API lookups for unprocessed company numbers
- **Schedule**: Every 2 minutes
- **Batch Size**: 10 companies per run (configurable via `COMPANIES_HOUSE_BATCH_SIZE` env var)

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