"""
Website Hunting CSV Export Module.

This module provides functionality to export website hunting data
to CSV format for campaign analysis and reporting.
"""
import csv
import json
from datetime import datetime
from typing import Optional

from django.http import HttpResponse
from django.db.models import QuerySet

from leadtrail.portal.models import Campaign, CompanyNumber


def generate_website_hunting_csv(campaign: Campaign) -> HttpResponse:
    """
    Generate a CSV export of website hunting data for a campaign.
    
    Args:
        campaign: The campaign to export data for
        
    Returns:
        HttpResponse with CSV data as attachment
    """
    # Create HTTP response with CSV content type
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="website_hunting_{campaign.name}_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv"'
    
    # Create CSV writer
    writer = csv.writer(response)
    
    # Write CSV header
    headers = [
        'Company Number',
        'Domains Found (SERP)',
        'Domains Found Count',
        'Ranked Domains (with Scores)',
        'Ranked Domains Count',
        'Best Scoring Domain',
        'Best Score',
        'SERP Status',
        'Crawl Status',
        'Processing Notes',
        'Approved Domain',
        'Approved by Human',
        'Created At'
    ]
    writer.writerow(headers)
    
    # Get company numbers for the campaign with related website hunting data
    companies = CompanyNumber.objects.filter(
        campaign=campaign
    ).select_related('website_hunting_result').order_by('company_number')
    
    # Write data rows
    for company in companies:
        hunting_data = company.website_hunting_result
        
        # Parse domains found and ranked domains
        domains_found_str = ''
        domains_found_count = 0
        ranked_domains_str = ''
        ranked_domains_count = 0
        best_domain = ''
        best_score = ''
        
        if hunting_data:
            # Handle domains found
            if hunting_data.domains_found:
                domains_found_count = len(hunting_data.domains_found)
                domains_found_str = '; '.join(hunting_data.domains_found) if isinstance(hunting_data.domains_found, list) else str(hunting_data.domains_found)
            
            # Handle ranked domains
            if hunting_data.ranked_domains:
                ranked_domains_count = len(hunting_data.ranked_domains)
                
                # Create readable string with domain and score
                if isinstance(hunting_data.ranked_domains, list):
                    domain_scores = []
                    best_score_val = 0
                    
                    for domain_data in hunting_data.ranked_domains:
                        if isinstance(domain_data, dict):
                            domain = domain_data.get('domain', 'Unknown')
                            score = domain_data.get('score', 0)
                            domain_scores.append(f"{domain} ({score})")
                            
                            # Track best scoring domain
                            if score > best_score_val:
                                best_score_val = score
                                best_domain = domain
                                best_score = str(score)
                    
                    ranked_domains_str = '; '.join(domain_scores)
                else:
                    ranked_domains_str = str(hunting_data.ranked_domains)
        
        # Extract data with fallback to empty strings
        row = [
            company.company_number,
            domains_found_str,
            domains_found_count,
            ranked_domains_str,
            ranked_domains_count,
            best_domain,
            best_score,
            hunting_data.serp_status if hunting_data and hunting_data.serp_status else '',
            hunting_data.crawl_status if hunting_data and hunting_data.crawl_status else '',
            hunting_data.processing_notes if hunting_data and hunting_data.processing_notes else '',
            hunting_data.approved_domain if hunting_data and hunting_data.approved_domain else '',
            'Yes' if hunting_data and hunting_data.approved_by_human else 'No',
            hunting_data.created_at.strftime('%Y-%m-%d %H:%M:%S') if hunting_data and hunting_data.created_at else ''
        ]
        
        writer.writerow(row)
    
    return response


def get_website_hunting_summary(campaign: Campaign) -> dict:
    """
    Get a summary of website hunting data for a campaign.
    
    Args:
        campaign: The campaign to get summary for
        
    Returns:
        Dictionary with summary statistics
    """
    companies = CompanyNumber.objects.filter(campaign=campaign).select_related('website_hunting_result')
    
    total_companies = companies.count()
    with_hunting_data = companies.filter(website_hunting_result__isnull=False).count()
    
    # Count companies with domains found
    domains_found_count = 0
    ranked_domains_count = 0
    approved_count = 0
    
    for company in companies:
        if company.website_hunting_result:
            hunting_data = company.website_hunting_result
            
            # Count domains found
            if hunting_data.domains_found and len(hunting_data.domains_found) > 0:
                domains_found_count += 1
            
            # Count ranked domains (with scores)
            if hunting_data.ranked_domains and len(hunting_data.ranked_domains) > 0:
                ranked_domains_count += 1
            
            # Count approved domains
            if hunting_data.approved_by_human and hunting_data.approved_domain:
                approved_count += 1
    
    return {
        'total_companies': total_companies,
        'with_hunting_data': with_hunting_data,
        'without_hunting_data': total_companies - with_hunting_data,
        'domains_found_count': domains_found_count,
        'ranked_domains_count': ranked_domains_count,
        'approved_count': approved_count,
        'completion_percentage': round((with_hunting_data / total_companies) * 100, 1) if total_companies > 0 else 0,
        'domains_found_percentage': round((domains_found_count / total_companies) * 100, 1) if total_companies > 0 else 0,
        'ranked_percentage': round((ranked_domains_count / total_companies) * 100, 1) if total_companies > 0 else 0,
        'approval_percentage': round((approved_count / total_companies) * 100, 1) if total_companies > 0 else 0
    }