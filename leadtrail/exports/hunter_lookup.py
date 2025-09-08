"""
Hunter.io Lookup CSV Export Module.

This module provides functionality to export Hunter.io domain search data
to CSV format for campaign analysis and reporting.
"""
import csv
import json
from datetime import datetime
from typing import Optional

from django.http import HttpResponse
from django.db.models import QuerySet

from leadtrail.portal.models import Campaign, CompanyNumber


def generate_hunter_lookup_csv(campaign: Campaign) -> HttpResponse:
    """
    Generate a CSV export of Hunter.io lookup data for a campaign.
    
    Args:
        campaign: The campaign to export data for
        
    Returns:
        HttpResponse with CSV data as attachment
    """
    # Create HTTP response with CSV content type
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="hunter_lookup_{campaign.name}_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv"'
    
    # Create CSV writer
    writer = csv.writer(response)
    
    # Write CSV header
    headers = [
        'Company Number',
        'Company Name',
        'Domain Searched',
        'Total Emails Found',
        'Email Addresses',
        'Email Details (First Name, Last Name, Position, Confidence)',
        'Processing Status',
        'Processing Notes',
        'Processed At',
        'Updated At'
    ]
    writer.writerow(headers)
    
    # Get company numbers for the campaign with related Hunter lookup data
    companies_with_hunter = CompanyNumber.objects.filter(
        campaign=campaign,
        hunter_lookup__isnull=False
    ).select_related('hunter_lookup', 'house_data').order_by('company_number')
    
    # Process each company and write to CSV
    for company in companies_with_hunter:
        hunter_data = company.hunter_lookup
        
        # Get company name from house data if available
        company_name = ""
        if hasattr(company, 'house_data') and company.house_data:
            company_name = company.house_data.company_name or ""
        
        # Format email addresses
        email_addresses_text = ""
        email_details_text = ""
        
        if hunter_data.emails_found:
            email_addresses = []
            email_details = []
            
            for email_data in hunter_data.emails_found:
                if isinstance(email_data, dict):
                    email = email_data.get('email', '')
                    first_name = email_data.get('first_name', '')
                    last_name = email_data.get('last_name', '')
                    position = email_data.get('position', '')
                    confidence = email_data.get('confidence', 0)
                    
                    email_addresses.append(email)
                    email_details.append(f"{email} ({first_name} {last_name}, {position}, {confidence}% confidence)")
                else:
                    email_addresses.append(str(email_data))
                    email_details.append(str(email_data))
            
            email_addresses_text = "; ".join(email_addresses)
            email_details_text = "; ".join(email_details)
        
        # Write row data
        row_data = [
            company.company_number,
            company_name,
            hunter_data.domain_searched,
            hunter_data.total_emails_found,
            email_addresses_text,
            email_details_text,
            hunter_data.processing_status,
            hunter_data.processing_notes or "",
            hunter_data.processed_at.strftime("%Y-%m-%d %H:%M:%S") if hunter_data.processed_at else "",
            hunter_data.updated_at.strftime("%Y-%m-%d %H:%M:%S") if hunter_data.updated_at else ""
        ]
        
        writer.writerow(row_data)
    
    return response


def get_hunter_lookup_summary(campaign: Campaign) -> dict:
    """
    Get summary statistics for Hunter.io lookups in a campaign.
    
    Args:
        campaign: The campaign to analyze
        
    Returns:
        Dictionary containing summary statistics
    """
    companies_with_hunter = CompanyNumber.objects.filter(
        campaign=campaign,
        hunter_lookup__isnull=False
    ).select_related('hunter_lookup')
    
    total_processed = companies_with_hunter.count()
    
    if total_processed == 0:
        return {
            'total_processed': 0,
            'total_emails_found': 0,
            'successful_extractions': 0,
            'success_rate': 0,
            'companies_with_emails': 0,
            'domains_searched': 0
        }
    
    total_emails = sum(company.hunter_lookup.total_emails_found for company in companies_with_hunter)
    successful_extractions = sum(1 for company in companies_with_hunter if company.hunter_lookup.has_emails)
    companies_with_emails = sum(1 for company in companies_with_hunter if company.hunter_lookup.total_emails_found > 0)
    domains_searched = len(set(company.hunter_lookup.domain_searched for company in companies_with_hunter))
    
    success_rate = round((successful_extractions / total_processed) * 100) if total_processed > 0 else 0
    
    return {
        'total_processed': total_processed,
        'total_emails_found': total_emails,
        'successful_extractions': successful_extractions,
        'success_rate': success_rate,
        'companies_with_emails': companies_with_emails,
        'domains_searched': domains_searched
    }