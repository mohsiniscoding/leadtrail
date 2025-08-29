"""
VAT Lookup CSV Export Module.

This module provides functionality to export VAT lookup data
to CSV format for campaign analysis and reporting.
"""
import csv
from datetime import datetime
from typing import Optional

from django.http import HttpResponse
from django.db.models import QuerySet

from leadtrail.portal.models import Campaign, CompanyNumber


def generate_vat_lookup_csv(campaign: Campaign) -> HttpResponse:
    """
    Generate a CSV export of VAT lookup data for a campaign.
    
    Args:
        campaign: The campaign to export data for
        
    Returns:
        HttpResponse with CSV data as attachment
    """
    # Create HTTP response with CSV content type
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="vat_lookup_{campaign.name}_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv"'
    
    # Create CSV writer
    writer = csv.writer(response)
    
    # Write CSV header
    headers = [
        'Company Number',
        'VAT Number',
        'Company Name (from VAT)',
        'Search Terms',
        'Status',
        'Processing Notes',
        'Proxy Used',
        'Created At'
    ]
    writer.writerow(headers)
    
    # Get company numbers for the campaign with related VAT data
    companies = CompanyNumber.objects.filter(
        campaign=campaign
    ).select_related('vat_lookup').order_by('company_number')
    
    # Write data rows
    for company in companies:
        vat_data = company.vat_lookup
        
        # Extract data with fallback to empty strings
        row = [
            company.company_number,
            vat_data.vat_number if vat_data and vat_data.vat_number else '',
            vat_data.company_name if vat_data and vat_data.company_name else '',
            vat_data.search_terms if vat_data and vat_data.search_terms else '',
            vat_data.status if vat_data and vat_data.status else 'NOT_PROCESSED',
            vat_data.processing_notes if vat_data and vat_data.processing_notes else '',
            vat_data.proxy_used if vat_data and vat_data.proxy_used else '',
            vat_data.created_at.strftime('%Y-%m-%d %H:%M:%S') if vat_data and vat_data.created_at else ''
        ]
        
        writer.writerow(row)
    
    return response


def get_vat_lookup_summary(campaign: Campaign) -> dict:
    """
    Get a summary of VAT lookup data for a campaign.
    
    Args:
        campaign: The campaign to get summary for
        
    Returns:
        Dictionary with summary statistics
    """
    companies = CompanyNumber.objects.filter(campaign=campaign).select_related('vat_lookup')
    
    total_companies = companies.count()
    with_vat_data = companies.filter(vat_lookup__isnull=False).count()
    
    # Count companies with valid VAT numbers (not empty, not "NOT_FOUND")
    valid_vat_count = 0
    for company in companies:
        if (company.vat_lookup and 
            company.vat_lookup.vat_number and 
            company.vat_lookup.vat_number.strip() and 
            company.vat_lookup.vat_number != "NOT_FOUND"):
            valid_vat_count += 1
    
    # Count by status
    status_counts = {}
    for company in companies:
        if company.vat_lookup and company.vat_lookup.status:
            status = company.vat_lookup.status
            status_counts[status] = status_counts.get(status, 0) + 1
        else:
            status_counts['NOT_PROCESSED'] = status_counts.get('NOT_PROCESSED', 0) + 1
    
    return {
        'total_companies': total_companies,
        'with_vat_data': with_vat_data,
        'without_vat_data': total_companies - with_vat_data,
        'valid_vat_numbers': valid_vat_count,
        'completion_percentage': round((with_vat_data / total_companies) * 100, 1) if total_companies > 0 else 0,
        'valid_vat_percentage': round((valid_vat_count / total_companies) * 100, 1) if total_companies > 0 else 0,
        'status_breakdown': status_counts
    }