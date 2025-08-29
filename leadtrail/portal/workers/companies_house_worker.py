#!/usr/bin/env python
"""
Companies House Lookup Worker
============================

A standalone worker script using the schedule library to process Companies House
API lookups for unprocessed company numbers.

Usage:
    python leadtrail/portal/workers/companies_house_worker.py

Schedule:
    Runs every 10 seconds
"""

import os
import sys
import time
import signal
import logging
from typing import Optional
from pathlib import Path

import schedule
import django
from django.conf import settings
from django.db import transaction

# Add project root to Python path for imports
project_root = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(project_root))

# Django setup
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.local")
django.setup()

from leadtrail.portal.models import CompanyNumber, CompanyHouseData
from leadtrail.portal.modules.companies_house_api_search import (
    CompaniesHouseAPIClient, 
    CompanyData, 
    CompanySearchStatus
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Configuration
DEFAULT_BATCH_SIZE = 100
SLEEP_BETWEEN_COMPANIES_SECONDS = 2

# Global flag for graceful shutdown
shutdown_requested = False


def signal_handler(signum, frame):
    """Handle shutdown signals gracefully."""
    global shutdown_requested
    logger.info(f"Received signal {signum}, requesting shutdown...")
    shutdown_requested = True


def _map_company_data_to_model(company_data: CompanyData, company_number_obj: CompanyNumber) -> CompanyHouseData:
    """
    Map CompanyData dataclass to CompanyHouseData model fields.
    
    Args:
        company_data: CompanyData instance from API module
        company_number_obj: CompanyNumber model instance
        
    Returns:
        CompanyHouseData model instance (not saved to database)
    """
    error_message = None
    if company_data.has_error:
        error_message = company_data.notes
    
    return CompanyHouseData(
        company_number=company_number_obj,
        company_name=company_data.company_name,
        company_status=company_data.company_status,
        company_type=company_data.company_type,
        incorporation_date=company_data.incorporation_date,
        jurisdiction=company_data.jurisdiction,
        
        # Address information
        registered_office_address=company_data.registered_office_address,
        address_line_1=company_data.address_line_1,
        address_line_2=company_data.address_line_2,
        locality=company_data.locality,
        region=company_data.region,
        postal_code=company_data.postal_code,
        country=company_data.country,
        
        # Address status indicators
        registered_office_is_in_dispute=company_data.registered_office_is_in_dispute,
        undeliverable_registered_office_address=company_data.undeliverable_registered_office_address,
        
        # Business activity and classification
        sic_codes=company_data.sic_codes,
        
        # Company status and risk indicators
        can_file=company_data.can_file,
        has_been_liquidated=company_data.has_been_liquidated,
        has_charges=company_data.has_charges,
        has_insolvency_history=company_data.has_insolvency_history,
        
        # Previous company names
        previous_company_names=company_data.previous_company_names,
        
        # Accounts information
        last_accounts_date=company_data.last_accounts_date,
        last_accounts_period_start=company_data.last_accounts_period_start,
        last_accounts_period_end=company_data.last_accounts_period_end,
        last_accounts_type=company_data.last_accounts_type,
        next_accounts_due=company_data.next_accounts_due,
        next_accounts_period_end=company_data.next_accounts_period_end,
        accounts_overdue=company_data.accounts_overdue,
        accounting_reference_date=company_data.accounting_reference_date,
        
        # Confirmation statement details
        confirmation_statement_date=company_data.confirmation_statement_date,
        confirmation_statement_next_due=company_data.confirmation_statement_next_due,
        confirmation_statement_overdue=company_data.confirmation_statement_overdue,
        
        # Officers information (convert integers to strings for model)
        officers_total_count=str(company_data.officers_total_count),
        officers_active_count=str(company_data.officers_active_count),
        officers_resigned_count=str(company_data.officers_resigned_count),
        officers_inactive_count=str(company_data.officers_inactive_count),
        key_officers=company_data.key_officers,
        
        # Additional dates
        last_full_members_list_date=company_data.last_full_members_list_date,
        
        # Status and error information
        status=company_data.api_response_status,
        error_message=error_message,
    )


def _process_company_number(company_number_obj: CompanyNumber, api_client: CompaniesHouseAPIClient) -> bool:
    """
    Process a single company number through the API and save to database.
    
    Args:
        company_number_obj: CompanyNumber model instance
        api_client: CompaniesHouseAPIClient instance
        
    Returns:
        bool: True if processing was successful, False otherwise
    """
    try:
        logger.info(f"Processing company number: {company_number_obj.company_number}")
        
        # Call the API to get company data
        company_data = api_client.extract_company_data(company_number_obj.company_number)
        
        # Map to model and save to database
        house_data = _map_company_data_to_model(company_data, company_number_obj)
        
        with transaction.atomic():
            house_data.save()
        
        # Log result
        if company_data.is_success:
            logger.info(f"Successfully processed {company_number_obj.company_number}: {company_data.company_name}")
        else:
            logger.warning(f"API error for {company_number_obj.company_number}: {company_data.api_response_status}")
        
        return True
        
    except Exception as e:
        logger.error(f"Error processing company number {company_number_obj.company_number}: {str(e)}")
        
        # Create an error record in the database
        try:
            error_record = CompanyHouseData(
                company_number=company_number_obj,
                company_name="PROCESSING_ERROR",
                company_status="PROCESSING_ERROR",
                company_type="PROCESSING_ERROR",
                incorporation_date="PROCESSING_ERROR",
                jurisdiction="PROCESSING_ERROR",
                registered_office_address="PROCESSING_ERROR",
                address_line_1="PROCESSING_ERROR",
                address_line_2="PROCESSING_ERROR",
                locality="PROCESSING_ERROR",
                region="PROCESSING_ERROR",
                postal_code="PROCESSING_ERROR",
                country="PROCESSING_ERROR",
                registered_office_is_in_dispute="PROCESSING_ERROR",
                undeliverable_registered_office_address="PROCESSING_ERROR",
                sic_codes="PROCESSING_ERROR",
                can_file="PROCESSING_ERROR",
                has_been_liquidated="PROCESSING_ERROR",
                has_charges="PROCESSING_ERROR",
                has_insolvency_history="PROCESSING_ERROR",
                previous_company_names="PROCESSING_ERROR",
                last_accounts_date="PROCESSING_ERROR",
                last_accounts_period_start="PROCESSING_ERROR",
                last_accounts_period_end="PROCESSING_ERROR",
                last_accounts_type="PROCESSING_ERROR",
                next_accounts_due="PROCESSING_ERROR",
                next_accounts_period_end="PROCESSING_ERROR",
                accounts_overdue="PROCESSING_ERROR",
                accounting_reference_date="PROCESSING_ERROR",
                confirmation_statement_date="PROCESSING_ERROR",
                confirmation_statement_next_due="PROCESSING_ERROR",
                confirmation_statement_overdue="PROCESSING_ERROR",
                officers_total_count="0",
                officers_active_count="0",
                officers_resigned_count="0",
                officers_inactive_count="0",
                key_officers="PROCESSING_ERROR",
                last_full_members_list_date="PROCESSING_ERROR",
                status=CompanySearchStatus.EXTRACTION_ERROR.value,
                error_message=f"Processing error: {str(e)}"
            )
            
            with transaction.atomic():
                error_record.save()
                
        except Exception as save_error:
            logger.error(f"Failed to save error record for {company_number_obj.company_number}: {str(save_error)}")
        
        return False


def run_companies_house_lookup():
    """
    Main worker function to perform Companies House lookup for unprocessed company numbers.
    
    This function:
    1. Finds company numbers without existing CompanyHouseData records
    2. Processes them through the Companies House API (oldest first)
    3. Saves results to database (both success and failure cases)
    4. Respects API rate limits and batch processing limits
    
    Returns:
        str: Summary message of processing results
    """
    # Get batch size from environment or use default
    batch_size = int(os.environ.get('COMPANIES_HOUSE_BATCH_SIZE', DEFAULT_BATCH_SIZE))
    
    logger.info(f"Starting Companies House lookup (batch size: {batch_size})")
    
    try:
        # Get unprocessed company numbers (oldest first)
        unprocessed_companies = CompanyNumber.objects.filter(
            house_data__isnull=True
        ).order_by('created_at')[:batch_size]
        
        if not unprocessed_companies:
            logger.info("No unprocessed company numbers found")
            return "No unprocessed company numbers found"
        
        logger.info(f"Found {len(unprocessed_companies)} unprocessed company numbers")
        
        # Initialize API client
        try:
            api_client = CompaniesHouseAPIClient()
        except ValueError as e:
            logger.error(f"Failed to initialize Companies House API client: {str(e)}")
            return f"API client initialization failed: {str(e)}"
        
        # Process each company number
        processed_count = 0
        success_count = 0
        error_count = 0
        
        for company_number_obj in unprocessed_companies:
            # Check for shutdown signal
            if shutdown_requested:
                logger.info("Shutdown requested, stopping processing")
                break
                
            try:
                success = _process_company_number(company_number_obj, api_client)
                processed_count += 1
                logger.info(f"sleeping for {SLEEP_BETWEEN_COMPANIES_SECONDS} seconds")
                time.sleep(SLEEP_BETWEEN_COMPANIES_SECONDS)
                
                if success:
                    success_count += 1
                else:
                    error_count += 1
                    
            except Exception as e:
                logger.error(f"Unexpected error processing {company_number_obj.company_number}: {str(e)}")
                error_count += 1
                processed_count += 1
        
        # Log and return summary
        summary = (
            f"Companies House lookup completed: {processed_count} processed, "
            f"{success_count} successful, {error_count} errors"
        )
        logger.info(summary)
        return summary
        
    except Exception as e:
        error_msg = f"Companies House lookup failed: {str(e)}"
        logger.error(error_msg)
        return error_msg


def main():
    """Main entry point for the worker."""
    logger.info("Starting Companies House Worker")
    logger.info("Press Ctrl+C to stop the worker")
    
    # Set up signal handlers for graceful shutdown
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Schedule the job to run every 10 seconds
    schedule.every(10).seconds.do(run_companies_house_lookup)
    
    # Run immediately on startup
    logger.info("Running initial Companies House lookup...")
    run_companies_house_lookup()
    
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
    
    logger.info("Companies House Worker stopped")


if __name__ == "__main__":
    main()