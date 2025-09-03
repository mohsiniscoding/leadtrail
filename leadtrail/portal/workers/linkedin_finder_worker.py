#!/usr/bin/env python
"""
LinkedIn Finder Worker
=====================

A standalone worker script using the schedule library to process LinkedIn profile
finding operations on companies in campaigns where LinkedIn lookup is enabled.

Usage:
    python leadtrail/portal/workers/linkedin_finder_worker.py

Schedule:
    Runs every 10 seconds
"""

import os
import sys
import time
import signal
import logging
from typing import Dict, Any, Optional
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
    Campaign,
    CompanyNumber, 
    LinkedinLookup
)
from leadtrail.portal.modules.linkedin_finder import LinkedInFinder

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Configuration
DEFAULT_BATCH_SIZE = 10

# Global flag for graceful shutdown
shutdown_requested = False


def signal_handler(signum, frame):
    """Handle shutdown signals gracefully."""
    global shutdown_requested
    logger.info(f"Received signal {signum}, requesting shutdown...")
    shutdown_requested = True


def _build_company_data(company_number_obj: CompanyNumber) -> Dict[str, Any]:
    """
    Build company data dict from available sources for LinkedIn search.
    
    Args:
        company_number_obj: CompanyNumber model instance
        
    Returns:
        Dict containing company identifiers and approved domain
    """
    company_data = {
        'company_number': company_number_obj.company_number,
        'company_name': '',
        'approved_domain': None
    }
    
    # Get company name from Companies House data
    if hasattr(company_number_obj, 'house_data') and company_number_obj.house_data:
        house_data = company_number_obj.house_data
        if house_data.company_name:
            company_data['company_name'] = house_data.company_name
    
    # Get approved domain from website hunting (if available)
    try:
        if hasattr(company_number_obj, 'website_hunting_result') and company_number_obj.website_hunting_result:
            hunting_result = company_number_obj.website_hunting_result
            if hunting_result.approved_domain:
                company_data['approved_domain'] = hunting_result.approved_domain
    except CompanyNumber.website_hunting_result.RelatedObjectDoesNotExist:
        # No website hunting result available
        pass
    
    logger.debug(f"Built company data for {company_number_obj.company_number}: "
                f"name='{company_data['company_name']}', domain='{company_data['approved_domain']}'")
    
    return company_data


def _process_linkedin_search(company_number_obj: CompanyNumber, 
                           linkedin_finder: LinkedInFinder) -> bool:
    """
    Process LinkedIn search for a single company.
    
    Args:
        company_number_obj: CompanyNumber model instance
        linkedin_finder: LinkedInFinder instance
        
    Returns:
        bool: True if processing was successful, False otherwise
    """
    try:
        logger.info(f"Processing LinkedIn search for company: {company_number_obj.company_number}")
        
        # Build company data from all available sources
        company_data = _build_company_data(company_number_obj)
        
        if not company_data['company_name']:
            logger.warning(f"No company name available for {company_number_obj.company_number}")
            # Create record with error status
            linkedin_lookup = LinkedinLookup(
                company_number=company_number_obj,
                company_urls=[],
                employee_urls=[],
                search_query="",
                search_status="NO_COMPANY_NAME",
                processing_notes="No company name available for LinkedIn search",
                total_results_found=0,
                approved_domain_used=company_data.get('approved_domain')
            )
            
            with transaction.atomic():
                linkedin_lookup.save()
            
            return True  # Successfully handled (with error record)
        
        logger.info(f"Searching LinkedIn for: {company_data['company_name']}")
        if company_data['approved_domain']:
            logger.info(f"Using approved domain for enhanced matching: {company_data['approved_domain']}")
        
        # Perform LinkedIn search
        search_result = linkedin_finder.find_linkedin_profiles(
            company_data['company_name'], 
            company_data['approved_domain']
        )
        
        # Convert LinkedInResult objects to JSON-serializable format
        company_urls = []
        for result in search_result.company_urls:
            company_urls.append({
                'url': result.url,
                'title': result.title,
                'description': result.description,
                'position': result.position,
                'score': result.score,
                'match_details': result.match_details
            })
        
        employee_urls = []
        for result in search_result.employee_urls:
            employee_urls.append({
                'url': result.url,
                'title': result.title,
                'description': result.description,
                'position': result.position,
                'score': result.score,
                'match_details': result.match_details
            })
        
        # Create LinkedinLookup record
        linkedin_lookup = LinkedinLookup(
            company_number=company_number_obj,
            company_urls=company_urls,
            employee_urls=employee_urls,
            search_query=search_result.search_query,
            search_status=search_result.search_status,
            processing_notes=search_result.processing_notes,
            total_results_found=search_result.total_results_found,
            approved_domain_used=company_data['approved_domain']
        )
        
        with transaction.atomic():
            linkedin_lookup.save()
        
        logger.info(f"LinkedIn search completed for {company_number_obj.company_number}: "
                   f"{linkedin_lookup.total_linkedin_profiles} profiles found, status: {search_result.search_status}")
        return True
        
    except Exception as e:
        logger.error(f"Error processing LinkedIn search for {company_number_obj.company_number}: {str(e)}")
        
        # Create error record in database
        try:
            company_data = _build_company_data(company_number_obj)
            error_lookup = LinkedinLookup(
                company_number=company_number_obj,
                company_urls=[],
                employee_urls=[],
                search_query="",
                search_status="PROCESSING_ERROR",
                processing_notes=f"Processing error: {str(e)}",
                total_results_found=0,
                approved_domain_used=company_data.get('approved_domain')
            )
            
            with transaction.atomic():
                error_lookup.save()
                
        except Exception as save_error:
            logger.error(f"Failed to save error record for {company_number_obj.company_number}: {str(save_error)}")
        
        return False


def run_linkedin_finder():
    """
    Main worker function to perform LinkedIn profile finding for companies in enabled campaigns.
    
    Processes companies in campaigns where LinkedIn lookup is enabled and 
    no LinkedinLookup record exists yet. Uses approved domains for enhanced matching.
    
    Returns:
        str: Summary of processing results
    """
    logger.info("Starting LinkedIn finder")
    
    try:
        # Get companies ready for LinkedIn search (no LinkedIn lookup done yet)
        companies_to_process = CompanyNumber.objects.filter(
            linkedin_lookup__isnull=True  # No LinkedIn lookup done yet
        ).select_related('house_data', 'website_hunting_result', 'campaign').order_by('created_at')[:DEFAULT_BATCH_SIZE]
        
        if not companies_to_process:
            logger.info("No companies ready for LinkedIn search (all done)")
            return "No companies ready for LinkedIn search"
        
        logger.info(f"Processing {len(companies_to_process)} companies for LinkedIn search")
        
        # Initialize LinkedIn finder
        try:
            linkedin_finder = LinkedInFinder()
            logger.info("LinkedIn finder initialized successfully")
        except ValueError as e:
            logger.error(f"Failed to initialize LinkedIn finder: {str(e)}")
            return f"LinkedIn finder initialization failed: {str(e)}"
        
        # Process each company
        successful_count = 0
        failed_count = 0
        
        for company in companies_to_process:
            # Check for shutdown signal
            if shutdown_requested:
                logger.info("Shutdown requested, stopping processing")
                break
                
            try:
                success = _process_linkedin_search(company, linkedin_finder)
                
                if success:
                    successful_count += 1
                else:
                    failed_count += 1
                    
            except Exception as e:
                logger.error(f"Error processing company {company.company_number}: {str(e)}")
                failed_count += 1
        
        # Return summary
        summary = f"LinkedIn search completed: {successful_count} successful, {failed_count} failed out of {len(companies_to_process)} companies"
        logger.info(summary)
        return summary
        
    except Exception as e:
        error_msg = f"LinkedIn finder failed: {str(e)}"
        logger.error(error_msg)
        return error_msg


def main():
    """Main entry point for the worker."""
    logger.info("Starting LinkedIn Finder Worker")
    logger.info("Press Ctrl+C to stop the worker")
    
    # Set up signal handlers for graceful shutdown
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Schedule the job to run every 10 seconds
    schedule.every(10).seconds.do(run_linkedin_finder)
    
    # Run immediately on startup
    logger.info("Running initial LinkedIn finder...")
    run_linkedin_finder()
    
    # Main worker loop
    while not shutdown_requested:
        try:
            schedule.run_pending()
            time.sleep(10)  # Check every 10 seconds
        except KeyboardInterrupt:
            logger.info("Received keyboard interrupt, shutting down...")
            break
        except Exception as e:
            logger.error(f"Unexpected error in worker loop: {str(e)}")
            time.sleep(30)  # Wait before retrying
    
    logger.info("LinkedIn Finder Worker stopped")


if __name__ == "__main__":
    main()