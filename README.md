# LeadTrail

From a company number to a complete outreach-ready profile. Instantly enrich leads with verified company data, VAT info, website, LinkedIn pages, and key contacts.

[![Built with Cookiecutter Django](https://img.shields.io/badge/built%20with-Cookiecutter%20Django-ff69b4.svg?logo=cookiecutter)](https://github.com/cookiecutter/cookiecutter-django/)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)

## 🚀 Quick Start - Running Locally

### Prerequisites
- Python 3.12+
- PostgreSQL
- Redis
- Node.js (for Tailwind CSS)

### 1. Environment Setup
```bash
# Clone and navigate to the project
git clone <repository-url>
cd leadtrail

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements/local.txt
npm install
```

### 2. Database Setup
```bash
# Create and apply migrations
python manage.py makemigrations
python manage.py migrate

# Create superuser account
python manage.py createsuperuser
```

### 3. Start Services (4 Terminal Windows)

**Terminal 1 - Django Server:**
```bash
python manage.py runserver
```

**Terminal 2 - Celery Worker:**
```bash
celery -A config.celery_app worker --concurrency=1 -l info
```

**Terminal 3 - Celery Beat Scheduler:**
```bash
celery -A config.celery_app beat -l info
```

**Terminal 4 - Flower Monitor (Optional):**
```bash
celery -A config.celery_app flower --port=5555
```

### 4. Access Applications
- **Django App**: http://localhost:8000
- **Flower Monitor**: http://localhost:5555
- **Admin Panel**: http://localhost:8000/admin

### 5. Background Tasks
The application includes automated background workers that process:
- **Companies House API lookups** (every 2 minutes)
- **VAT number lookups** (every minute)
- **Website discovery and ranking** (every 3 minutes)

Monitor these tasks in real-time via Flower at http://localhost:5555

## Settings

Moved to [settings](https://cookiecutter-django.readthedocs.io/en/latest/1-getting-started/settings.html).

## Basic Commands

### Setting Up Your Users

- To create a **normal user account**, just go to Sign Up and fill out the form. Once you submit it, you'll see a "Verify Your E-mail Address" page. Go to your console to see a simulated email verification message. Copy the link into your browser. Now the user's email should be verified and ready to go.

- To create a **superuser account**, use this command:

      $ python manage.py createsuperuser

For convenience, you can keep your normal user logged in on Chrome and your superuser logged in on Firefox (or similar), so that you can see how the site behaves for both kinds of users.

### Type checks

Running type checks with mypy:

    $ mypy leadtrail

### Test coverage

To run the tests, check your test coverage, and generate an HTML coverage report:

    $ coverage run -m pytest
    $ coverage html
    $ open htmlcov/index.html

#### Running tests with pytest

    $ pytest

### Live reloading and Sass CSS compilation

Moved to [Live reloading and SASS compilation](https://cookiecutter-django.readthedocs.io/en/latest/2-local-development/developing-locally.html#using-webpack-or-gulp).

### Celery Background Processing

This app uses Celery with Redis for background task processing with singleton pattern to prevent duplicate processing.

**⚠️ IMPORTANT: Use the commands from the Quick Start section above. The configuration below prevents duplicate key constraint errors.**

**✅ CORRECT WAY - Separate processes:**

```bash
# Terminal 1 - Single worker (prevents race conditions)
celery -A config.celery_app worker --concurrency=1 -l info

# Terminal 2 - Separate beat scheduler
celery -A config.celery_app beat -l info

# Terminal 3 - Flower monitoring (optional)
celery -A config.celery_app flower --port=5555
```

**❌ OLD WAY (causes duplicate key errors):**
```bash
# DON'T USE: Creates multiple schedulers and race conditions
celery -A config.celery_app worker -B -l info
```

**Key Features:**
- **Singleton Tasks**: Only one instance of each task can run at a time
- **Sequential Processing**: Tasks execute one at a time to prevent conflicts
- **Real-time Monitoring**: Flower provides web interface for task monitoring
- **Automated Scheduling**: Background workers run on predefined intervals

### Email Server

In development, it is often nice to be able to see emails that are being sent from your application. If you choose to use [Mailpit](https://github.com/axllent/mailpit) when generating the project a local SMTP server with a web interface will be available.

1.  [Download the latest Mailpit release](https://github.com/axllent/mailpit/releases) for your OS.

2.  Copy the binary file to the project root.

3.  Make it executable:

        $ chmod +x mailpit

4.  Spin up another terminal window and start it there:

        ./mailpit

5.  Check out <http://127.0.0.1:8025/> to see how it goes.

Now you have your own mail server running locally, ready to receive whatever you send it.

### Sentry

Sentry is an error logging aggregator service. You can sign up for a free account at <https://sentry.io/signup/?code=cookiecutter> or download and host it yourself.
The system is set up with reasonable defaults, including 404 logging and integration with the WSGI application.

You must set the DSN url in production.

## Deployment

The following details how to deploy this application.

### Heroku

See detailed [cookiecutter-django Heroku documentation](https://cookiecutter-django.readthedocs.io/en/latest/3-deployment/deployment-on-heroku.html).
