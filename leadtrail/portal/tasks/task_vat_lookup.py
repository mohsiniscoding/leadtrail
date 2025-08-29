"""
VAT Lookup Task
==============

This task performs VAT lookup operations by fetching company numbers
that have completed Companies House processing and performing VAT lookups
using company names from the Companies House data.
"""
import os
import json
import logging
from typing import Optional
from django.conf import settings
from django.db import transaction

from config.celery_app import app
from celery_singleton import Singleton
from leadtrail.portal.models import CompanyNumber, VATLookup, CompanyHouseData
from leadtrail.portal.modules.vat_lookup import VATLookupClient, VATData, VATSearchStatus
from leadtrail.portal.modules.companies_house_api_search import CompanySearchStatus

logger = logging.getLogger(__name__)

# Configuration
DEFAULT_BATCH_SIZE = 5


def _map_vat_data_to_model(vat_data: VATData, company_number_obj: CompanyNumber) -> VATLookup:
    """
    Map VATData dataclass to VATLookup model fields.
    
    Args:
        vat_data: VATData instance from VAT lookup module
        company_number_obj: CompanyNumber model instance
        
    Returns:
        VATLookup model instance (not saved to database)
    """
    # Convert search_terms list to JSON string for database storage
    search_terms_json = json.dumps(vat_data.search_terms) if vat_data.search_terms else "[]"
    
    return VATLookup(
        company_number=company_number_obj,
        vat_number=vat_data.vat_number,
        company_name=vat_data.company_name,
        search_terms=search_terms_json,
        status=vat_data.search_status,
        processing_notes=vat_data.processing_notes,
        proxy_used=vat_data.proxy_used
    )


def _create_error_vat_record(company_number_obj: CompanyNumber, reason: str) -> VATLookup:
    """
    Create a VATLookup error record for companies where VAT lookup cannot be performed.
    
    Args:
        company_number_obj: CompanyNumber model instance
        reason: Reason why VAT lookup couldn't be performed
        
    Returns:
        VATLookup model instance (not saved to database)
    """
    return VATLookup(
        company_number=company_number_obj,
        vat_number="NOT_FOUND",
        company_name="",
        search_terms="[]",
        status=VATSearchStatus.INVALID_COMPANY_NAME.value,
        processing_notes=reason,
        proxy_used="none"
    )


def _process_company_vat_lookup(company_number_obj: CompanyNumber, vat_client: VATLookupClient) -> bool:
    """
    Process VAT lookup for a single company based on its Companies House data status.
    
    Args:
        company_number_obj: CompanyNumber model instance
        vat_client: VATLookupClient instance (can be None if proxy not configured)
        
    Returns:
        bool: True if processing was successful, False otherwise
    """
    try:
        house_data = company_number_obj.house_data
        logger.info(f"Processing VAT lookup for company number: {company_number_obj.company_number}")
        
        # Check Companies House data status
        if house_data.status == CompanySearchStatus.SUCCESS.value:
            # Companies House was successful - attempt VAT lookup
            company_name = house_data.company_name
            
            if not company_name or company_name.strip() == "":
                # No company name available even though status is success
                logger.warning(f"Company {company_number_obj.company_number} has SUCCESS status but no company name")
                vat_record = _create_error_vat_record(
                    company_number_obj,
                    "Cannot perform VAT lookup - Company name is empty despite successful Companies House lookup"
                )
            elif not vat_client:
                # VAT client not available (proxy not configured)
                logger.warning(f"VAT client not available for {company_number_obj.company_number}")
                vat_record = _create_error_vat_record(
                    company_number_obj,
                    "Cannot perform VAT lookup - VAT service not configured (missing proxy configuration)"
                )
            else:
                # Perform actual VAT lookup
                logger.info(f"Performing VAT lookup for: {company_name}")
                vat_data = vat_client.lookup_vat_by_company_name(company_name)
                vat_record = _map_vat_data_to_model(vat_data, company_number_obj)
                
                # Log result
                if vat_data.is_success:
                    logger.info(f"VAT lookup successful for {company_number_obj.company_number}: {vat_data.vat_number}")
                else:
                    logger.info(f"VAT lookup completed with status {vat_data.search_status} for {company_number_obj.company_number}")
        else:
            # Companies House failed - create error record without API call
            logger.info(f"Skipping VAT lookup for {company_number_obj.company_number} - Companies House status: {house_data.status}")
            vat_record = _create_error_vat_record(
                company_number_obj,
                f"Cannot perform VAT lookup - Companies House data unavailable (status: {house_data.status})"
            )
        
        # Save to database
        with transaction.atomic():
            vat_record.save()
        
        logger.info(f"VAT lookup record created for {company_number_obj.company_number}")
        return True
        
    except Exception as e:
        logger.error(f"Error processing VAT lookup for company number {company_number_obj.company_number}: {str(e)}")
        
        # Create an error record in the database
        try:
            error_record = _create_error_vat_record(
                company_number_obj,
                f"Processing error during VAT lookup: {str(e)}"
            )
            
            with transaction.atomic():
                error_record.save()
                
        except Exception as save_error:
            logger.error(f"Failed to save error record for {company_number_obj.company_number}: {str(save_error)}")
        
        return False


@app.task(base=Singleton, lock_expiry=120, raise_on_duplicate=False)
def run():
    """
    Task to perform VAT lookup for companies that have completed Companies House processing.
    
    This task:
    1. Finds company numbers with Companies House data but no VAT lookup records
    2. For successful Companies House data: Performs VAT lookup using company name
    3. For failed Companies House data: Creates error VAT records without API calls
    4. Always creates VATLookup records for tracking and audit purposes
    5. Respects rate limiting and batch processing limits
    
    Returns:
        str: Summary message of processing results
    """
    # Get batch size from environment or use default
    batch_size = int(os.environ.get('VAT_LOOKUP_BATCH_SIZE', DEFAULT_BATCH_SIZE))
    
    logger.info(f"[SINGLETON] Starting VAT lookup task (batch size: {batch_size}) - Lock expiry: 120s")
    
    try:
        # Get companies that have completed Companies House processing but no VAT lookup
        unprocessed_companies = CompanyNumber.objects.filter(
            house_data__isnull=False,
            vat_lookup__isnull=True
        ).order_by('created_at')[:batch_size]
        
        if not unprocessed_companies:
            logger.info("No companies ready for VAT lookup (waiting for Companies House completion)")
            return "No companies ready for VAT lookup"
        
        logger.info(f"Found {len(unprocessed_companies)} companies ready for VAT lookup")
        
        # Initialize VAT client (may be None if proxy not configured)
        vat_client = None
        try:
            vat_client = VATLookupClient()
            logger.info("VAT lookup client initialized successfully")
        except ValueError as e:
            logger.warning(f"VAT lookup client not available: {str(e)}")
            logger.info("Will create error records for companies requiring VAT lookup")
        
        # Process each company
        processed_count = 0
        success_count = 0
        error_count = 0
        
        for company_number_obj in unprocessed_companies:
            try:
                success = _process_company_vat_lookup(company_number_obj, vat_client)
                processed_count += 1
                
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
            f"VAT lookup completed: {processed_count} processed, "
            f"{success_count} successful, {error_count} errors"
        )
        logger.info(summary)
        return summary
        
    except Exception as e:
        error_msg = f"VAT lookup task failed: {str(e)}"
        logger.error(error_msg)
        return error_msg
