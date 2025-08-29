"""
LinkedIn Finder CSV Export Module.

This module provides functionality to export LinkedIn lookup data
to CSV format for campaign analysis and reporting.
"""
import csv
import json
from datetime import datetime
from typing import Optional

from django.http import HttpResponse
from django.db.models import QuerySet

from leadtrail.portal.models import Campaign, CompanyNumber


def generate_linkedin_finder_csv(campaign: Campaign) -> HttpResponse:
    """
    Generate a CSV export of LinkedIn finder data for a campaign.
    
    Args:
        campaign: The campaign to export data for
        
    Returns:
        HttpResponse with CSV data as attachment
    """
    # Create HTTP response with CSV content type
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="linkedin_finder_{campaign.name}_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv"'
    
    # Create CSV writer
    writer = csv.writer(response)
    
    # Write CSV header
    headers = [
        'Company Number',
        'Company URLs',
        'Company URLs Count',
        'Employee URLs',
        'Employee URLs Count',
        'Best Company Profile URL',
        'Best Company Profile Score',
        'Total Results Found',
        'Total LinkedIn Profiles',
        'Search Query',
        'Search Status',
        'Processing Notes',
        'Approved Domain Used',
        'Created At'
    ]
    writer.writerow(headers)
    
    # Get company numbers for the campaign with related LinkedIn lookup data
    companies = CompanyNumber.objects.filter(
        campaign=campaign
    ).select_related('linkedin_lookup').order_by('company_number')
    
    # Write data rows
    for company in companies:
        # Safely get LinkedIn data or None if it doesn't exist
        try:
            linkedin_data = company.linkedin_lookup
        except CompanyNumber.linkedin_lookup.RelatedObjectDoesNotExist:
            linkedin_data = None
        
        # Initialize variables
        company_urls_str = ''
        company_urls_count = 0
        employee_urls_str = ''
        employee_urls_count = 0
        best_company_url = ''
        best_company_score = ''
        total_profiles = 0
        
        if linkedin_data:
            # Handle company URLs
            if linkedin_data.company_urls and isinstance(linkedin_data.company_urls, list):
                company_urls_count = len(linkedin_data.company_urls)
                
                # Create readable string with URL and score
                if company_urls_count > 0:
                    company_url_parts = []
                    best_score = 0
                    
                    for company_profile in linkedin_data.company_urls:
                        if isinstance(company_profile, dict):
                            url = company_profile.get('url', 'Unknown URL')
                            score = company_profile.get('score', 0)
                            company_url_parts.append(f"{url} ({score})")
                            
                            # Track best scoring company profile
                            if score > best_score:
                                best_score = score
                                best_company_url = url
                                best_company_score = str(score)
                        elif isinstance(company_profile, str):
                            company_url_parts.append(company_profile)
                    
                    company_urls_str = '; '.join(company_url_parts)
            
            # Handle employee URLs
            if linkedin_data.employee_urls and isinstance(linkedin_data.employee_urls, list):
                employee_urls_count = len(linkedin_data.employee_urls)
                
                # Create readable string
                if employee_urls_count > 0:
                    employee_url_parts = []
                    
                    for employee_profile in linkedin_data.employee_urls:
                        if isinstance(employee_profile, dict):
                            url = employee_profile.get('url', 'Unknown URL')
                            score = employee_profile.get('score', 0)
                            employee_url_parts.append(f"{url} ({score})")
                        elif isinstance(employee_profile, str):
                            employee_url_parts.append(employee_profile)
                    
                    employee_urls_str = '; '.join(employee_url_parts)
            
            # Calculate total profiles
            total_profiles = company_urls_count + employee_urls_count
        
        # Extract data with fallback to empty strings
        row = [
            company.company_number,
            company_urls_str,
            company_urls_count,
            employee_urls_str,
            employee_urls_count,
            best_company_url,
            best_company_score,
            linkedin_data.total_results_found if linkedin_data and linkedin_data.total_results_found else 0,
            total_profiles,
            linkedin_data.search_query if linkedin_data and linkedin_data.search_query else '',
            linkedin_data.search_status if linkedin_data and linkedin_data.search_status else 'NOT_PROCESSED',
            linkedin_data.processing_notes if linkedin_data and linkedin_data.processing_notes else '',
            linkedin_data.approved_domain_used if linkedin_data and linkedin_data.approved_domain_used else '',
            linkedin_data.created_at.strftime('%Y-%m-%d %H:%M:%S') if linkedin_data and linkedin_data.created_at else ''
        ]
        
        writer.writerow(row)
    
    return response


def get_linkedin_finder_summary(campaign: Campaign) -> dict:
    """
    Get a summary of LinkedIn finder data for a campaign.
    
    Args:
        campaign: The campaign to get summary for
        
    Returns:
        Dictionary with summary statistics
    """
    companies = CompanyNumber.objects.filter(campaign=campaign).select_related('linkedin_lookup')
    
    total_companies = companies.count()
    with_linkedin_data = companies.filter(linkedin_lookup__isnull=False).count()
    
    # Count different types of LinkedIn profiles found
    companies_with_company_profiles = 0
    companies_with_employee_profiles = 0
    companies_with_any_profiles = 0
    total_company_profiles_found = 0
    total_employee_profiles_found = 0
    
    for company in companies:
        # Safely get LinkedIn data or None if it doesn't exist
        try:
            linkedin_data = company.linkedin_lookup
            if linkedin_data:
                has_any_profile = False
                
                # Check company profiles
                if linkedin_data.company_urls and len(linkedin_data.company_urls) > 0:
                    companies_with_company_profiles += 1
                    total_company_profiles_found += len(linkedin_data.company_urls)
                    has_any_profile = True
                
                # Check employee profiles
                if linkedin_data.employee_urls and len(linkedin_data.employee_urls) > 0:
                    companies_with_employee_profiles += 1
                    total_employee_profiles_found += len(linkedin_data.employee_urls)
                    has_any_profile = True
                
                if has_any_profile:
                    companies_with_any_profiles += 1
        except CompanyNumber.linkedin_lookup.RelatedObjectDoesNotExist:
            # No LinkedIn data exists for this company, skip
            continue
    
    return {
        'total_companies': total_companies,
        'with_linkedin_data': with_linkedin_data,
        'without_linkedin_data': total_companies - with_linkedin_data,
        'companies_with_company_profiles': companies_with_company_profiles,
        'companies_with_employee_profiles': companies_with_employee_profiles,
        'companies_with_any_profiles': companies_with_any_profiles,
        'total_company_profiles_found': total_company_profiles_found,
        'total_employee_profiles_found': total_employee_profiles_found,
        'total_profiles_found': total_company_profiles_found + total_employee_profiles_found,
        'completion_percentage': round((with_linkedin_data / total_companies) * 100, 1) if total_companies > 0 else 0,
        'company_profile_percentage': round((companies_with_company_profiles / total_companies) * 100, 1) if total_companies > 0 else 0,
        'employee_profile_percentage': round((companies_with_employee_profiles / total_companies) * 100, 1) if total_companies > 0 else 0,
        'any_profile_percentage': round((companies_with_any_profiles / total_companies) * 100, 1) if total_companies > 0 else 0
    }