"""
Website Contact Finder Task
=========================

This task performs website contact finding operations on approved domains
from WebsiteHuntingResult records. It extracts contact information including
phone numbers, email addresses, and social media links using the ContactExtractor.
"""
import logging
from typing import Dict, Any, Optional
from django.db import transaction

from config.celery_app import app
from celery_singleton import Singleton
from leadtrail.portal.models import (
    CompanyNumber, 
    WebsiteHuntingResult, 
    WebsiteContactLookup
)
from leadtrail.portal.modules.contact_extractor import ContactExtractor, ContactCrawlConfig

logger = logging.getLogger(__name__)

# Configuration
DEFAULT_BATCH_SIZE = 3


def _build_company_data(company_number_obj: CompanyNumber) -> Dict[str, Any]:
    """
    Build company data dict from available sources for contact extraction.
    
    Args:
        company_number_obj: CompanyNumber model instance
        
    Returns:
        Dict containing company identifiers
    """
    company_data = {
        'company_number': company_number_obj.company_number,
        'company_name': '',
        'domain': ''
    }
    
    # Get company name from Companies House data
    if hasattr(company_number_obj, 'house_data') and company_number_obj.house_data:
        house_data = company_number_obj.house_data
        if house_data.company_name:
            company_data['company_name'] = house_data.company_name
    
    # Get approved domain from website hunting
    if hasattr(company_number_obj, 'website_hunting_result') and company_number_obj.website_hunting_result:
        hunting_result = company_number_obj.website_hunting_result
        if hunting_result.approved_domain:
            company_data['domain'] = hunting_result.approved_domain
    
    logger.debug(f"Built company data for {company_number_obj.company_number}: "
                f"name='{company_data['company_name']}', domain='{company_data['domain']}'")
    
    return company_data


def _process_contact_extraction(company_number_obj: CompanyNumber, 
                              contact_extractor: ContactExtractor) -> bool:
    """
    Process contact extraction for a single company.
    
    Args:
        company_number_obj: CompanyNumber model instance
        contact_extractor: ContactExtractor instance
        
    Returns:
        bool: True if processing was successful, False otherwise
    """
    try:
        logger.info(f"Processing contact extraction for company: {company_number_obj.company_number}")
        
        # Get the approved domain
        hunting_result = company_number_obj.website_hunting_result
        approved_domain = hunting_result.approved_domain
        
        if not approved_domain:
            logger.warning(f"No approved domain for company {company_number_obj.company_number}")
            return False
        
        logger.info(f"Extracting contacts from domain: {approved_domain}")
        
        # Extract contact information
        contact_info = contact_extractor.extract_contact_info(approved_domain)
        
        # Prepare social media links in the expected format
        social_media_links = {
            'facebook': contact_info.facebook_links,
            'instagram': contact_info.instagram_links,
            'linkedin': contact_info.linkedin_links
        }
        
        # Create WebsiteContactLookup record
        contact_lookup = WebsiteContactLookup(
            company_number=company_number_obj,
            domain_searched=approved_domain,
            phone_numbers=contact_info.phone_numbers,
            email_addresses=contact_info.email_addresses,
            social_media_links=social_media_links,
            status=contact_info.extraction_status,
            processing_notes=contact_info.processing_notes,
            pages_crawled=contact_info.pages_crawled
        )
        
        with transaction.atomic():
            contact_lookup.save()
        
        logger.info(f"Contact extraction completed for {company_number_obj.company_number}: "
                   f"{contact_lookup.total_contacts_found} contacts found, status: {contact_info.extraction_status}")
        return True
        
    except Exception as e:
        logger.error(f"Error processing contact extraction for {company_number_obj.company_number}: {str(e)}")
        
        # Create error record in database
        try:
            approved_domain = getattr(company_number_obj.website_hunting_result, 'approved_domain', 'unknown')
            error_lookup = WebsiteContactLookup(
                company_number=company_number_obj,
                domain_searched=approved_domain,
                phone_numbers=[],
                email_addresses=[],
                social_media_links={},
                status="PROCESSING_ERROR",
                processing_notes=f"Processing error: {str(e)}",
                pages_crawled=0
            )
            
            with transaction.atomic():
                error_lookup.save()
                
        except Exception as save_error:
            logger.error(f"Failed to save error record for {company_number_obj.company_number}: {str(save_error)}")
        
        return False


@app.task(base=Singleton, lock_expiry=600, raise_on_duplicate=False)
def run():
    """
    Website contact finder background task.
    
    Processes approved domains from WebsiteHuntingResult records where no 
    WebsiteContactLookup exists yet. Extracts contact information and stores results.
    
    Returns:
        str: Summary of processing results
    """
    logger.info("[SINGLETON] Website contact finder task started - Lock expiry: 600s")
    
    try:
        # Get companies ready for contact extraction (approved domains without contact lookup)
        companies_to_process = CompanyNumber.objects.filter(
            website_hunting_result__approved_domain__isnull=False,  # Has approved domain
            website_hunting_result__approved_by_human=True,  # Human approved
            website_contact_lookup__isnull=True  # No contact lookup done yet
        ).select_related('house_data', 'website_hunting_result').order_by('created_at')[:DEFAULT_BATCH_SIZE]
        
        if not companies_to_process:
            logger.info("No companies ready for contact extraction")
            return "No companies ready for contact extraction"
        
        logger.info(f"Processing {len(companies_to_process)} companies for contact extraction")
        
        # Initialize contact extractor with optimized configuration
        contact_config = ContactCrawlConfig(
            max_pages_per_site=10,
            timeout_seconds=30,
            delay_between_requests=1.0,
            max_phone_numbers=15,
            max_email_addresses=15,
            max_social_links_per_platform=5
        )
        contact_extractor = ContactExtractor(contact_config)
        logger.info("Contact extractor initialized successfully")
        
        # Process each company
        successful_count = 0
        failed_count = 0
        
        for company in companies_to_process:
            try:
                success = _process_contact_extraction(company, contact_extractor)
                
                if success:
                    successful_count += 1
                else:
                    failed_count += 1
                    
            except Exception as e:
                logger.error(f"Error processing company {company.company_number}: {str(e)}")
                failed_count += 1
        
        # Return summary
        summary = f"Website contact extraction completed: {successful_count} successful, {failed_count} failed out of {len(companies_to_process)} companies"
        logger.info(summary)
        return summary
        
    except Exception as e:
        error_msg = f"Website contact finder task failed: {str(e)}"
        logger.error(error_msg)
        return error_msg
