#!/usr/bin/env python
"""
Website Contact Extraction Worker
==================================

A standalone worker script using the schedule library to process website contact
extraction for companies with approved domains from WebsiteHuntingResult records.

This worker extracts contact information including phone numbers, email addresses, 
and social media links using the ContactExtractor for companies that have been 
human-approved through the website hunting process.

Usage:
    python leadtrail/portal/workers/website_contact_extraction_worker.py

Schedule:
    Runs every 30 seconds
"""

import os
import sys
import time
import signal
import logging
from pathlib import Path

import schedule
import django
from django.db import transaction

# Add project root to Python path for imports
project_root = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(project_root))

# Django setup
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.local")
django.setup()

from leadtrail.portal.models import (
    CompanyNumber, 
    WebsiteContactLookup
)
from leadtrail.portal.modules.contact_extractor import ContactExtractor, ContactCrawlConfig

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Configuration
DEFAULT_BATCH_SIZE = 3
RUN_EVERY_SECONDS = 5

# Global flag for graceful shutdown
shutdown_requested = False


def signal_handler(signum, frame):
    """Handle shutdown signals gracefully."""
    global shutdown_requested
    logger.info(f"Received signal {signum}, requesting shutdown...")
    shutdown_requested = True


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


def run_website_contact_extraction():
    """
    Main worker function to perform website contact extraction for companies with approved domains.
    
    This function:
    1. Finds companies with approved domains that have been human-approved but no contact extraction done
    2. Initializes ContactExtractor with optimized configuration for web crawling
    3. Extracts contact information including phones, emails, and social media links
    4. Creates WebsiteContactLookup records for tracking and audit purposes
    5. Respects rate limiting and batch processing limits
    
    Returns:
        str: Summary message of processing results
    """
    # Get batch size from environment or use default
    batch_size = int(os.environ.get('CONTACT_EXTRACTION_BATCH_SIZE', DEFAULT_BATCH_SIZE))
    
    logger.info(f"Starting website contact extraction (batch size: {batch_size})")
    
    try:
        # Get companies ready for contact extraction (approved domains without contact lookup)
        companies_to_process = CompanyNumber.objects.filter(
            website_hunting_result__approved_domain__isnull=False,  # Has approved domain
            website_hunting_result__approved_by_human=True,  # Human approved
            website_contact_lookup__isnull=True  # No contact lookup done yet
        ).select_related('house_data', 'website_hunting_result').order_by('created_at')[:batch_size]
        
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
            # Check for shutdown signal
            if shutdown_requested:
                logger.info("Shutdown requested, stopping processing")
                break
                
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
        error_msg = f"Website contact extraction failed: {str(e)}"
        logger.error(error_msg)
        return error_msg


def main():
    """Main entry point for the worker."""
    logger.info("Starting Website Contact Extraction Worker")
    logger.info("Press Ctrl+C to stop the worker")
    
    # Set up signal handlers for graceful shutdown
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Schedule the job to run every RUN_EVERY_SECONDS seconds
    schedule.every(RUN_EVERY_SECONDS).seconds.do(run_website_contact_extraction)
    
    # Run immediately on startup
    logger.info("Running initial website contact extraction...")
    run_website_contact_extraction()
    
    # Main worker loop
    while not shutdown_requested:
        try:
            schedule.run_pending()
            time.sleep(RUN_EVERY_SECONDS)  # Check every RUN_EVERY_SECONDS seconds
        except KeyboardInterrupt:
            logger.info("Received keyboard interrupt, shutting down...")
            break
        except Exception as e:
            logger.error(f"Unexpected error in worker loop: {str(e)}")
            time.sleep(RUN_EVERY_SECONDS)  # Wait before retrying
    
    logger.info("Website Contact Extraction Worker stopped")


if __name__ == "__main__":
    main()