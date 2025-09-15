release: python manage.py migrate
web: gunicorn config.wsgi:application
companies-house-worker: python leadtrail/portal/workers/companies_house_worker.py
vat-lookup-worker: python leadtrail/portal/workers/vat_lookup_worker.py
website-hunting-worker: python leadtrail/portal/workers/website_hunting_worker.py
website-contact-extraction-worker: python leadtrail/portal/workers/website_contact_extraction_worker.py
linkedin-profile-discovery-worker: python leadtrail/portal/workers/linkedin_finder_worker.py
snov-email-extraction-worker: python leadtrail/portal/workers/snov_email_extraction_worker.py
hunter-domain-search-worker: python leadtrail/portal/workers/hunter_domain_search_worker.py