"""
Tasks module for portal app.
"""

from leadtrail.portal.tasks.task_vat_lookup import run  # noqa
from leadtrail.portal.tasks.task_companies_house_lookup import run as companies_house_run  # noqa
from leadtrail.portal.tasks.task_website_hunting import run as website_hunting_run  # noqa
from leadtrail.portal.tasks.task_website_contact_finder import run as website_contact_finder_run  # noqa
from leadtrail.portal.tasks.task_linkedin_finder import run as linkedin_finder_run  # noqa
from leadtrail.portal.tasks.task_check_zenserp_quota import run as check_zenserp_quota_run  # noqa