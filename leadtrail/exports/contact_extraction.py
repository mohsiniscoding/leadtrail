"""
Contact Extraction CSV Export Module.

This module provides functionality to export website contact extraction data
to CSV format for campaign analysis and reporting.
"""
import csv
import json
from datetime import datetime
from typing import Optional

from django.http import HttpResponse
from django.db.models import QuerySet

from leadtrail.portal.models import Campaign, CompanyNumber


def generate_contact_extraction_csv(campaign: Campaign) -> HttpResponse:
    """
    Generate a CSV export of contact extraction data for a campaign.
    
    Args:
        campaign: The campaign to export data for
        
    Returns:
        HttpResponse with CSV data as attachment
    """
    # Create HTTP response with CSV content type
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="contact_extraction_{campaign.name}_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv"'
    
    # Create CSV writer
    writer = csv.writer(response)
    
    # Write CSV header
    headers = [
        'Company Number',
        'Domain Searched',
        'Phone Numbers',
        'Phone Numbers Count',
        'Email Addresses',
        'Email Addresses Count',
        'Social Media Links',
        'Social Media Count',
        'Facebook Links',
        'Instagram Links',
        'LinkedIn Links',
        'Total Contacts Found',
        'Pages Crawled',
        'Status',
        'Processing Notes',
        'Created At'
    ]
    writer.writerow(headers)
    
    # Get company numbers for the campaign with related contact lookup data
    # Only include companies that have website_contact_lookup data
    companies = CompanyNumber.objects.filter(
        campaign=campaign,
        website_contact_lookup__isnull=False
    ).select_related('website_contact_lookup').order_by('company_number')
    
    # Write data rows
    for company in companies:
        # Get contact data (guaranteed to exist due to filter)
        contact_data = company.website_contact_lookup
        
        # Initialize variables
        phone_numbers_str = ''
        phone_count = 0
        email_addresses_str = ''
        email_count = 0
        social_media_str = ''
        social_count = 0
        facebook_links = ''
        instagram_links = ''
        linkedin_links = ''
        total_contacts = 0
        
        if contact_data:
            # Handle phone numbers
            if contact_data.phone_numbers and isinstance(contact_data.phone_numbers, list):
                phone_count = len(contact_data.phone_numbers)
                phone_numbers_str = '; '.join(contact_data.phone_numbers)
            
            # Handle email addresses
            if contact_data.email_addresses and isinstance(contact_data.email_addresses, list):
                email_count = len(contact_data.email_addresses)
                email_addresses_str = '; '.join(contact_data.email_addresses)
            
            # Handle social media links
            if contact_data.social_media_links and isinstance(contact_data.social_media_links, dict):
                social_media_parts = []
                
                # Facebook links
                facebook = contact_data.social_media_links.get('facebook', [])
                if isinstance(facebook, list) and facebook:
                    facebook_links = '; '.join(facebook)
                    social_media_parts.append(f"Facebook: {facebook_links}")
                    social_count += len(facebook)
                elif isinstance(facebook, str) and facebook.strip():
                    facebook_links = facebook
                    social_media_parts.append(f"Facebook: {facebook}")
                    social_count += 1
                
                # Instagram links
                instagram = contact_data.social_media_links.get('instagram', [])
                if isinstance(instagram, list) and instagram:
                    instagram_links = '; '.join(instagram)
                    social_media_parts.append(f"Instagram: {instagram_links}")
                    social_count += len(instagram)
                elif isinstance(instagram, str) and instagram.strip():
                    instagram_links = instagram
                    social_media_parts.append(f"Instagram: {instagram}")
                    social_count += 1
                
                # LinkedIn links
                linkedin = contact_data.social_media_links.get('linkedin', [])
                if isinstance(linkedin, list) and linkedin:
                    linkedin_links = '; '.join(linkedin)
                    social_media_parts.append(f"LinkedIn: {linkedin_links}")
                    social_count += len(linkedin)
                elif isinstance(linkedin, str) and linkedin.strip():
                    linkedin_links = linkedin
                    social_media_parts.append(f"LinkedIn: {linkedin}")
                    social_count += 1
                
                social_media_str = ' | '.join(social_media_parts)
            
            # Calculate total contacts
            total_contacts = phone_count + email_count + social_count
        
        # Extract data with fallback to empty strings
        row = [
            company.company_number,
            contact_data.domain_searched if contact_data and contact_data.domain_searched else '',
            phone_numbers_str,
            phone_count,
            email_addresses_str,
            email_count,
            social_media_str,
            social_count,
            facebook_links,
            instagram_links,
            linkedin_links,
            total_contacts,
            contact_data.pages_crawled if contact_data and contact_data.pages_crawled else 0,
            contact_data.status if contact_data and contact_data.status else 'NOT_PROCESSED',
            contact_data.processing_notes if contact_data and contact_data.processing_notes else '',
            contact_data.created_at.strftime('%Y-%m-%d %H:%M:%S') if contact_data and contact_data.created_at else ''
        ]
        
        writer.writerow(row)
    
    return response


def get_contact_extraction_summary(campaign: Campaign) -> dict:
    """
    Get a summary of contact extraction data for a campaign.
    
    Args:
        campaign: The campaign to get summary for
        
    Returns:
        Dictionary with summary statistics
    """
    companies = CompanyNumber.objects.filter(campaign=campaign).select_related('website_contact_lookup')
    
    total_companies = companies.count()
    with_contact_data = companies.filter(website_contact_lookup__isnull=False).count()
    
    # Count different types of contacts found
    companies_with_emails = 0
    companies_with_phones = 0
    companies_with_social = 0
    companies_with_any_contact = 0
    total_emails_found = 0
    total_phones_found = 0
    total_social_found = 0
    
    for company in companies:
        # Safely get contact data or None if it doesn't exist
        try:
            contact_data = company.website_contact_lookup
            if contact_data:
                has_any_contact = False
                
                # Check emails
                if contact_data.email_addresses and len(contact_data.email_addresses) > 0:
                    companies_with_emails += 1
                    total_emails_found += len(contact_data.email_addresses)
                    has_any_contact = True
                
                # Check phones
                if contact_data.phone_numbers and len(contact_data.phone_numbers) > 0:
                    companies_with_phones += 1
                    total_phones_found += len(contact_data.phone_numbers)
                    has_any_contact = True
                
                # Check social media
                if contact_data.social_media_links:
                    social_count = 0
                    for platform, links in contact_data.social_media_links.items():
                        if isinstance(links, list):
                            social_count += len(links)
                        elif isinstance(links, str) and links.strip():
                            social_count += 1
                    
                    if social_count > 0:
                        companies_with_social += 1
                        total_social_found += social_count
                        has_any_contact = True
                
                if has_any_contact:
                    companies_with_any_contact += 1
        except CompanyNumber.website_contact_lookup.RelatedObjectDoesNotExist:
            # No contact data exists for this company, skip
            continue
    
    return {
        'total_companies': total_companies,
        'with_contact_data': with_contact_data,
        'without_contact_data': total_companies - with_contact_data,
        'companies_with_emails': companies_with_emails,
        'companies_with_phones': companies_with_phones,
        'companies_with_social': companies_with_social,
        'companies_with_any_contact': companies_with_any_contact,
        'total_emails_found': total_emails_found,
        'total_phones_found': total_phones_found,
        'total_social_found': total_social_found,
        'completion_percentage': round((with_contact_data / total_companies) * 100, 1) if total_companies > 0 else 0,
        'email_success_percentage': round((companies_with_emails / total_companies) * 100, 1) if total_companies > 0 else 0,
        'phone_success_percentage': round((companies_with_phones / total_companies) * 100, 1) if total_companies > 0 else 0,
        'social_success_percentage': round((companies_with_social / total_companies) * 100, 1) if total_companies > 0 else 0,
        'any_contact_percentage': round((companies_with_any_contact / total_companies) * 100, 1) if total_companies > 0 else 0
    }