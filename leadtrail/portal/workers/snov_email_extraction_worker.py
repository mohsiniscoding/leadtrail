#!/usr/bin/env python
"""
Snov.io Email Extraction Worker
===============================

A standalone worker script using the schedule library to process email extraction
for companies with approved LinkedIn employee profiles from LinkedinEmployeeReview records.

This worker extracts professional email addresses from LinkedIn profiles using the 
Snov.io API for companies that have been human-approved through the LinkedIn 
employee review process.

Usage:
    python leadtrail/portal/workers/snov_email_extraction_worker.py

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
    LinkedinEmployeeReview,
    SnovLookup
)
from leadtrail.portal.utils.snov_client import SnovClient, SnovResult, SnovAuthenticationError, SnovAPIError

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


def _process_snov_email_extraction(company_number_obj: CompanyNumber, 
                                  snov_client: SnovClient) -> bool:
    """
    Process Snov.io email extraction for a single company.
    
    Args:
        company_number_obj: CompanyNumber model instance
        snov_client: SnovClient instance
        
    Returns:
        bool: True if processing was successful, False otherwise
    """
    try:
        logger.info(f"Processing Snov email extraction for company: {company_number_obj.company_number}")
        
        # Get the approved LinkedIn employee profiles
        employee_review = company_number_obj.linkedin_employee_review
        approved_urls = employee_review.approved_employee_urls
        
        if not approved_urls:
            logger.warning(f"No approved LinkedIn employee URLs for company {company_number_obj.company_number}")
            return False
        
        logger.info(f"Processing {len(approved_urls)} LinkedIn profiles for email extraction")
        
        # Process each LinkedIn profile
        all_emails_found = []
        profiles_processed = []
        successful_profiles = 0
        failed_profiles = 0
        processing_notes = []
        
        for profile_data in approved_urls:
            # Check for shutdown signal
            if shutdown_requested:
                logger.info("Shutdown requested, stopping profile processing")
                break
                
            try:
                # Extract LinkedIn URL from profile data
                linkedin_url = profile_data.get('url') if isinstance(profile_data, dict) else str(profile_data)
                
                if not linkedin_url:
                    logger.warning(f"Invalid profile data format: {profile_data}")
                    failed_profiles += 1
                    continue
                
                logger.info(f"Extracting emails from LinkedIn profile: {linkedin_url}")
                
                # Process the profile through Snov.io
                snov_result: SnovResult = snov_client.process_linkedin_profile(linkedin_url)
                
                # Store the processed profile information
                profile_result = {
                    'url': linkedin_url,
                    'position': snov_result.position,
                    'emails': snov_result.emails,
                    'status': snov_result.status,
                    'message': snov_result.message
                }
                profiles_processed.append(profile_result)
                
                # Add emails to the overall collection
                if snov_result.emails:
                    all_emails_found.extend(snov_result.emails)
                    successful_profiles += 1
                    logger.info(f"Found {len(snov_result.emails)} emails for profile {linkedin_url}")
                else:
                    failed_profiles += 1
                    logger.info(f"No emails found for profile {linkedin_url}: {snov_result.message}")
                
                # Add processing notes if there are issues
                if snov_result.status != 'SUCCESS':
                    processing_notes.append(f"Profile {linkedin_url}: {snov_result.message}")
                    
            except Exception as profile_error:
                logger.error(f"Error processing profile {linkedin_url}: {str(profile_error)}")
                failed_profiles += 1
                processing_notes.append(f"Profile {linkedin_url}: Processing error - {str(profile_error)}")
        
        # Determine overall processing status
        if successful_profiles > 0 and failed_profiles == 0:
            processing_status = "SUCCESS"
        elif successful_profiles > 0 and failed_profiles > 0:
            processing_status = "PARTIAL_SUCCESS"
        elif successful_profiles == 0 and failed_profiles > 0:
            processing_status = "NO_EMAILS_FOUND" if not processing_notes else "API_ERROR"
        else:
            processing_status = "PROCESSING_ERROR"
        
        # Create SnovLookup record
        snov_lookup = SnovLookup(
            company_number=company_number_obj,
            linkedin_profiles_processed=profiles_processed,
            emails_found=all_emails_found,
            processing_status=processing_status,
            processing_notes="\n".join(processing_notes) if processing_notes else "",
            profiles_processed_count=len(profiles_processed),
            total_emails_found=len(all_emails_found)
        )
        
        with transaction.atomic():
            snov_lookup.save()
        
        logger.info(f"Snov email extraction completed for {company_number_obj.company_number}: "
                   f"{len(all_emails_found)} emails found from {successful_profiles}/{len(approved_urls)} profiles, "
                   f"status: {processing_status}")
        return True
        
    except Exception as e:
        logger.error(f"Error processing Snov email extraction for {company_number_obj.company_number}: {str(e)}")
        
        # Create error record in database
        try:
            error_lookup = SnovLookup(
                company_number=company_number_obj,
                linkedin_profiles_processed=[],
                emails_found=[],
                processing_status="PROCESSING_ERROR",
                processing_notes=f"Processing error: {str(e)}",
                profiles_processed_count=0,
                total_emails_found=0
            )
            
            with transaction.atomic():
                error_lookup.save()
                
        except Exception as save_error:
            logger.error(f"Failed to save error record for {company_number_obj.company_number}: {str(save_error)}")
        
        return False


def run_snov_email_extraction():
    """
    Main worker function to perform Snov.io email extraction for companies with approved LinkedIn profiles.
    
    This function:
    1. Finds companies with approved LinkedIn employee profiles that have no Snov lookup done yet
    2. Initializes SnovClient for API interaction
    3. Extracts email information from approved LinkedIn employee profiles
    4. Creates SnovLookup records for tracking and audit purposes
    5. Respects rate limiting and batch processing limits
    
    Returns:
        str: Summary message of processing results
    """
    logger.info(f"Starting Snov email extraction (batch size: {DEFAULT_BATCH_SIZE})")
    
    try:
        # Get companies ready for Snov email extraction
        companies_to_process = CompanyNumber.objects.filter(
            linkedin_employee_review__isnull=False,  # Has LinkedIn employee review
            snov_lookup__isnull=True  # No Snov lookup done yet
        ).select_related('house_data', 'linkedin_employee_review').order_by('created_at')[:DEFAULT_BATCH_SIZE]
        
        # Filter out companies with no approved employee URLs (done in Python since JSONField filtering can be tricky)
        companies_with_urls = []
        for company in companies_to_process:
            if company.linkedin_employee_review.approved_employee_urls:
                companies_with_urls.append(company)
        
        companies_to_process = companies_with_urls
        
        if not companies_to_process:
            logger.info("No companies ready for Snov email extraction")
            return "No companies ready for Snov email extraction"
        
        logger.info(f"Processing {len(companies_to_process)} companies for Snov email extraction")
        
        # Initialize Snov client
        try:
            snov_client = SnovClient()
            logger.info("Snov client initialized successfully")
        except SnovAuthenticationError as auth_error:
            error_msg = f"Snov authentication failed: {str(auth_error)}"
            logger.error(error_msg)
            return error_msg
        
        # Process each company
        successful_count = 0
        failed_count = 0
        
        for company in companies_to_process:
            # Check for shutdown signal
            if shutdown_requested:
                logger.info("Shutdown requested, stopping processing")
                break
                
            try:
                success = _process_snov_email_extraction(company, snov_client)
                
                if success:
                    successful_count += 1
                else:
                    failed_count += 1
                    
            except Exception as e:
                logger.error(f"Error processing company {company.company_number}: {str(e)}")
                failed_count += 1
        
        # Return summary
        summary = f"Snov email extraction completed: {successful_count} successful, {failed_count} failed out of {len(companies_to_process)} companies"
        logger.info(summary)
        return summary
        
    except Exception as e:
        error_msg = f"Snov email extraction failed: {str(e)}"
        logger.error(error_msg)
        return error_msg


def main():
    """Main entry point for the worker."""
    logger.info("Starting Snov.io Email Extraction Worker")
    logger.info("Press Ctrl+C to stop the worker")
    
    # Set up signal handlers for graceful shutdown
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Schedule the job to run every RUN_EVERY_SECONDS seconds
    schedule.every(RUN_EVERY_SECONDS).seconds.do(run_snov_email_extraction)
    
    # Run immediately on startup
    logger.info("Running initial Snov email extraction...")
    run_snov_email_extraction()
    
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
    
    logger.info("Snov.io Email Extraction Worker stopped")


if __name__ == "__main__":
    main()