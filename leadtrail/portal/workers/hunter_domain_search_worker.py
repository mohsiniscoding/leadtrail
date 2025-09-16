#!/usr/bin/env python
"""
Hunter.io Domain Search Worker
==============================

A standalone worker script using the schedule library to process Hunter.io domain
search for companies with approved domains from the Website Hunting Review process.

This worker extracts professional email addresses from approved domains using the 
Hunter.io API for companies that have been human-approved through the website 
hunting review process.

Usage:
    python leadtrail/portal/workers/hunter_domain_search_worker.py

Schedule:
    Runs every 10 seconds
"""

import os
import sys
import time
import signal
import logging
from pathlib import Path
from typing import List, Dict, Any

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
    WebsiteHuntingResult,
    HunterLookup
)
from leadtrail.portal.utils.hunter_client import HunterClient, HunterAuthenticationError, HunterAPIError

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Configuration
DEFAULT_BATCH_SIZE = 2
RUN_EVERY_SECONDS = 10

# Global flag for graceful shutdown
shutdown_requested = False


def signal_handler(signum, frame):
    """Handle shutdown signals gracefully."""
    global shutdown_requested
    logger.info(f"Received signal {signum}, requesting shutdown...")
    shutdown_requested = True


def _process_hunter_domain_search(company_number_obj: CompanyNumber, 
                                hunter_client: HunterClient) -> bool:
    """
    Process Hunter.io domain search for a single company.
    
    Args:
        company_number_obj: CompanyNumber model instance
        hunter_client: HunterClient instance
        
    Returns:
        bool: True if processing was successful, False otherwise
    """
    try:
        logger.info(f"Processing Hunter domain search for company: {company_number_obj.company_number}")
        
        # Get the approved domain from website hunting result
        website_hunting_result = company_number_obj.website_hunting_result
        approved_domain = website_hunting_result.approved_domain
        
        if not approved_domain:
            logger.warning(f"No approved domain for company {company_number_obj.company_number}")
            return False
        
        logger.info(f"Searching emails for domain: {approved_domain}")
        
        # Process the domain through Hunter.io
        search_result = hunter_client.domain_search(approved_domain)
        
        # Extract data from result
        emails_found = search_result.get('emails', [])
        processing_status = search_result.get('status', 'API_ERROR')
        
        # Determine processing notes
        processing_notes = ""
        if processing_status == "API_ERROR":
            processing_notes = f"Hunter.io API error occurred for domain {approved_domain}"
        elif processing_status == "NO_EMAILS_FOUND":
            processing_notes = f"No emails found for domain {approved_domain}"
        elif processing_status == "SUCCESS":
            processing_notes = f"Successfully found {len(emails_found)} emails for domain {approved_domain}"
        
        # Create HunterLookup record
        hunter_lookup = HunterLookup(
            company_number=company_number_obj,
            domain_searched=approved_domain,
            emails_found=emails_found,
            processing_status=processing_status,
            processing_notes=processing_notes,
            total_emails_found=len(emails_found)
        )
        
        with transaction.atomic():
            hunter_lookup.save()
        
        logger.info(f"Hunter domain search completed for {company_number_obj.company_number}: "
                   f"{len(emails_found)} emails found for domain {approved_domain}, "
                   f"status: {processing_status}")
        return True
        
    except Exception as e:
        logger.error(f"Error processing Hunter domain search for {company_number_obj.company_number}: {str(e)}")
        
        # Create error record in database
        try:
            error_lookup = HunterLookup(
                company_number=company_number_obj,
                domain_searched=getattr(company_number_obj.website_hunting_result, 'approved_domain', 'unknown'),
                emails_found=[],
                processing_status="PROCESSING_ERROR",
                processing_notes=f"Processing error: {str(e)}",
                total_emails_found=0
            )
            
            with transaction.atomic():
                error_lookup.save()
                
        except Exception as save_error:
            logger.error(f"Failed to save error record for {company_number_obj.company_number}: {str(save_error)}")
        
        return False


def run_hunter_domain_search():
    """
    Main worker function to perform Hunter.io domain search for companies with approved domains.
    
    This function:
    1. Finds companies with approved domains that have no Hunter lookup done yet
    2. Initializes HunterClient for API interaction
    3. Extracts email information from approved domains
    4. Creates HunterLookup records for tracking and audit purposes
    5. Respects rate limiting and batch processing limits
    
    Returns:
        str: Summary message of processing results
    """
    logger.info(f"Starting Hunter domain search (batch size: {DEFAULT_BATCH_SIZE})")
    
    try:
        # Get companies ready for Hunter domain search
        companies_to_process = CompanyNumber.objects.filter(
            website_hunting_result__approved_domain__isnull=False,  # Has approved domain
            website_hunting_result__approved_by_human=True,  # Domain is human-approved
            hunter_lookup__isnull=True  # No Hunter lookup done yet
        ).select_related('house_data', 'website_hunting_result').order_by('created_at')[:DEFAULT_BATCH_SIZE]
        
        if not companies_to_process:
            logger.info("No companies ready for Hunter domain search")
            return "No companies ready for Hunter domain search"
        
        logger.info(f"Processing {len(companies_to_process)} companies for Hunter domain search")
        
        # Initialize Hunter client
        try:
            hunter_client = HunterClient()
            logger.info("Hunter client initialized successfully")
        except HunterAuthenticationError as auth_error:
            error_msg = f"Hunter authentication failed: {str(auth_error)}"
            logger.error(error_msg)
            return error_msg

        ## check quota
        quota_data = hunter_client.check_api_quota()
        if not quota_data:
            logger.error("Failed to retrieve Hunter API quota")
            return "Failed to retrieve Hunter API quota"
        available_credits = quota_data.get('available_credits', 0)
        if available_credits < DEFAULT_BATCH_SIZE:
            logger.error(f"Hunter API quota is less than {DEFAULT_BATCH_SIZE} - stopping Hunter domain search")
            return "Hunter API quota is less than {DEFAULT_BATCH_SIZE} - stopping Hunter domain search"
        
        # Process each company
        successful_count = 0
        failed_count = 0
        
        for company in companies_to_process:
            # Check for shutdown signal
            if shutdown_requested:
                logger.info("Shutdown requested, stopping processing")
                break
                
            try:
                success = _process_hunter_domain_search(company, hunter_client)
                
                if success:
                    successful_count += 1
                else:
                    failed_count += 1
                    
            except Exception as e:
                logger.error(f"Error processing company {company.company_number}: {str(e)}")
                failed_count += 1
        
        # Return summary
        summary = f"Hunter domain search completed: {successful_count} successful, {failed_count} failed out of {len(companies_to_process)} companies"
        logger.info(summary)
        return summary
        
    except Exception as e:
        error_msg = f"Hunter domain search failed: {str(e)}"
        logger.error(error_msg)
        return error_msg


def main():
    """Main entry point for the worker."""
    logger.info("Starting Hunter.io Domain Search Worker")
    logger.info("Press Ctrl+C to stop the worker")
    
    # Set up signal handlers for graceful shutdown
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Schedule the job to run every RUN_EVERY_SECONDS seconds
    schedule.every(RUN_EVERY_SECONDS).seconds.do(run_hunter_domain_search)
    
    # Run immediately on startup
    logger.info("Running initial Hunter domain search...")
    run_hunter_domain_search()
    
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
    
    logger.info("Hunter.io Domain Search Worker stopped")


if __name__ == "__main__":
    main()