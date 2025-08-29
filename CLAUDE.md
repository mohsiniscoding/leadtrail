# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

LeadTrail is a Django-based lead enrichment application that transforms company numbers into complete outreach-ready profiles. It enriches leads with verified company data from Companies House, VAT information, website details, LinkedIn pages, and key contacts through automated background tasks.

## Development Commands

### Running the Application
```bash
python manage.py runserver
```

### Database Operations
```bash
python manage.py makemigrations
python manage.py migrate
python manage.py createsuperuser
```

### Testing
```bash
pytest                           # Run all tests
pytest leadtrail/users/tests/    # Run specific app tests
coverage run -m pytest          # Run tests with coverage
coverage html                   # Generate HTML coverage report
```

### Code Quality
```bash
mypy leadtrail                   # Type checking
ruff check                       # Linting
ruff format                      # Code formatting
djlint leadtrail/templates/      # Template linting
```

### Background Tasks (Celery)
```bash
# CORRECT WAY - Run separate processes to prevent duplicate key constraints:

# Terminal 1 - Single worker (prevents race conditions)
celery -A config.celery_app worker --concurrency=1 -l info

# Terminal 2 - Separate beat scheduler 
celery -A config.celery_app beat -l info

# Terminal 3 - Flower monitoring (optional)
celery -A config.celery_app flower --port=5555

# IMPORTANT: Never use -B flag with worker as it creates multiple schedulers!
# OLD WAY (causes duplicate key errors): celery -A config.celery_app worker -B -l info
```

### Frontend Assets
```bash
npm install                      # Install Tailwind CSS dependencies
```

## Architecture

### Core Applications
- **leadtrail.users**: User management with django-allauth authentication
- **leadtrail.portal**: Main business logic for campaigns, company data, and lead enrichment
- **leadtrail.contrib.sites**: Custom site migrations

### Background Processing
The application uses Celery with Redis for asynchronous task processing. Scheduled tasks handle:
- Companies House API lookups (every 2 minutes)
- VAT number lookups (every minute)  
- Website discovery via SERP (every 3 minutes)
- Contact extraction from websites (every 4 minutes)
- LinkedIn page finding (every 5 minutes)
- ZenSERP quota monitoring (every 5 minutes)

### Data Models
- **Campaign**: Groups company numbers for processing
- **CompanyNumber**: Individual company registration numbers
- **CompanyHouseData**: Detailed company information from Companies House API
- **VATLookup**: VAT registration details
- **SERPExcludedDomain/BlacklistDomain**: Domain filtering for web crawling

### External APIs
- Companies House API for company data
- VAT lookup services
- ZenSERP for search engine results
- Various website crawling and contact extraction services

## Settings Structure
- `config/settings/base.py`: Core Django settings and Celery configuration
- `config/settings/local.py`: Development settings with debug tools
- `config/settings/production.py`: Production-ready settings
- `config/settings/test.py`: Test environment settings

## Key Dependencies
- Django 5.1 with PostgreSQL database
- Celery + Redis for background tasks
- django-allauth for authentication (registration disabled for internal use)
- Tailwind CSS for styling
- BeautifulSoup4 + requests for web scraping

## Development Notes
- The application is designed as an internal tool (user registration is disabled)
- All company data processing happens asynchronously via Celery tasks
- Uses Cookiecutter Django project structure
- Configured for Heroku deployment with Procfile
- Type checking with mypy and code quality enforced with ruff