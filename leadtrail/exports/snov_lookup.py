"""
Snov.io Lookup CSV Export Module.

This module provides functionality to export Snov.io email extraction data
to CSV format for campaign analysis and reporting.
"""
import csv
import json
from datetime import datetime
from typing import Optional

from django.http import HttpResponse
from django.db.models import QuerySet

from leadtrail.portal.models import Campaign, CompanyNumber


def generate_snov_lookup_csv(campaign: Campaign) -> HttpResponse:
    """
    Generate a CSV export of Snov.io lookup data for a campaign.
    
    Args:
        campaign: The campaign to export data for
        
    Returns:
        HttpResponse with CSV data as attachment
    """
    # Create HTTP response with CSV content type
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="snov_lookup_{campaign.name}_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv"'
    
    # Create CSV writer
    writer = csv.writer(response)
    
    # Write CSV header
    headers = [
        'Company Number',
        'Company Name',
        'LinkedIn Profiles Processed',
        'LinkedIn Profiles Count',
        'Emails Found',
        'Total Emails Found',
        'Processing Status',
        'Processing Notes',
        'Profiles Processed Count',
        'Processed At',
        'Updated At'
    ]
    writer.writerow(headers)
    
    # Get company numbers for the campaign with related Snov lookup data
    companies_with_snov = CompanyNumber.objects.filter(
        campaign=campaign,
        snov_lookup__isnull=False
    ).select_related('snov_lookup', 'house_data').order_by('company_number')
    
    # Process each company and write to CSV
    for company in companies_with_snov:
        snov_data = company.snov_lookup
        
        # Get company name from house data if available
        company_name = ""
        if hasattr(company, 'house_data') and company.house_data:
            company_name = company.house_data.company_name or ""
        
        # Format LinkedIn profiles processed
        linkedin_profiles_text = ""
        if snov_data.linkedin_profiles_processed:
            profiles_list = []
            for profile in snov_data.linkedin_profiles_processed:
                if isinstance(profile, dict):
                    url = profile.get('url', '')
                    position = profile.get('position', 'Unknown')
                    status = profile.get('status', 'Unknown')
                    profiles_list.append(f"{url} ({position} - {status})")
                else:
                    profiles_list.append(str(profile))
            linkedin_profiles_text = "; ".join(profiles_list)
        
        # Format emails found
        emails_text = ""
        if snov_data.emails_found:
            # Convert list of emails to semicolon-separated string
            if isinstance(snov_data.emails_found, list):
                emails_text = "; ".join(str(email) for email in snov_data.emails_found)
            else:
                emails_text = str(snov_data.emails_found)
        
        # Write row data
        row_data = [
            company.company_number,
            company_name,
            linkedin_profiles_text,
            len(snov_data.linkedin_profiles_processed) if snov_data.linkedin_profiles_processed else 0,
            emails_text,
            snov_data.total_emails_found,
            snov_data.processing_status,
            snov_data.processing_notes or "",
            snov_data.profiles_processed_count,
            snov_data.processed_at.strftime("%Y-%m-%d %H:%M:%S") if snov_data.processed_at else "",
            snov_data.updated_at.strftime("%Y-%m-%d %H:%M:%S") if snov_data.updated_at else ""
        ]
        
        writer.writerow(row_data)
    
    return response


def get_snov_lookup_summary(campaign: Campaign) -> dict:
    """
    Get summary statistics for Snov.io lookups in a campaign.
    
    Args:
        campaign: The campaign to analyze
        
    Returns:
        Dictionary containing summary statistics
    """
    companies_with_snov = CompanyNumber.objects.filter(
        campaign=campaign,
        snov_lookup__isnull=False
    ).select_related('snov_lookup')
    
    total_processed = companies_with_snov.count()
    
    if total_processed == 0:
        return {
            'total_processed': 0,
            'total_emails_found': 0,
            'total_profiles_processed': 0,
            'successful_extractions': 0,
            'success_rate': 0,
            'companies_with_emails': 0
        }
    
    total_emails = sum(company.snov_lookup.total_emails_found for company in companies_with_snov)
    total_profiles = sum(company.snov_lookup.profiles_processed_count for company in companies_with_snov)
    successful_extractions = sum(1 for company in companies_with_snov if company.snov_lookup.has_emails)
    companies_with_emails = sum(1 for company in companies_with_snov if company.snov_lookup.total_emails_found > 0)
    
    success_rate = round((successful_extractions / total_processed) * 100) if total_processed > 0 else 0
    
    return {
        'total_processed': total_processed,
        'total_emails_found': total_emails,
        'total_profiles_processed': total_profiles,
        'successful_extractions': successful_extractions,
        'success_rate': success_rate,
        'companies_with_emails': companies_with_emails
    }