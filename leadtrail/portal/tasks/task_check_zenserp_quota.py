"""
ZenSERP Quota Check Task
======================

This task checks the available ZenSERP API quota and updates the database.
"""
import logging
from config.celery_app import app
from leadtrail.portal.models import ZenSERPQuota
from leadtrail.portal.modules.website_hunter_api import WebsiteHunterClient

logger = logging.getLogger(__name__)


@app.task
def run():
    """
    Task to check ZenSERP API quota.
    
    Retrieves the current quota from the ZenSERP API and updates the database.
    
    Returns:
        str: Message indicating the task has completed.
    """
    logger.info("Checking ZenSERP API quota...")
    
    try:
        # Create WebsiteHunterClient instance (it will load API key from .env)
        client = WebsiteHunterClient()
        
        # Check API quota
        quota_data = client.check_api_quota()
        
        if not quota_data:
            logger.error("Failed to retrieve ZenSERP API quota")
            return "Failed to retrieve ZenSERP API quota"
        
        # Extract available credits
        available_credits = quota_data.get('remaining_requests', 0)
        
        # Update or create quota record
        quota = ZenSERPQuota.get_current_quota()
        quota.available_credits = available_credits
        quota.save()
        
        logger.info(f"ZenSERP API quota updated: {available_credits} credits available")
        return f"ZenSERP API quota updated: {available_credits} credits available"
        
    except Exception as e:
        logger.error(f"Error checking ZenSERP API quota: {str(e)}")
        return f"Error checking ZenSERP API quota: {str(e)}"
