"""
Companies House Lookup CSV Export Module.

This module provides functionality to export Companies House lookup data
to CSV format for campaign analysis and reporting.
"""
import csv
from datetime import datetime
from io import StringIO
from typing import Optional

from django.http import HttpResponse
from django.db.models import QuerySet

from leadtrail.portal.models import Campaign, CompanyNumber


def generate_companies_house_csv(campaign: Campaign) -> HttpResponse:
    """
    Generate a CSV export of Companies House lookup data for a campaign.
    
    Args:
        campaign: The campaign to export data for
        
    Returns:
        HttpResponse with CSV data as attachment
    """
    # Create HTTP response with CSV content type
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="companies_house_lookup_{campaign.name}_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv"'
    
    # Create CSV writer
    writer = csv.writer(response)
    
    # Write CSV header
    headers = [
        'Company Number',
        'Company Name', 
        'Company Status',
        'Company Type',
        'Incorporation Date',
        'Jurisdiction',
        'Registered Office Address',
        'Address Line 1',
        'Address Line 2', 
        'Locality',
        'Region',
        'Postal Code',
        'Country',
        'SIC Codes',
        'Can File',
        'Has Been Liquidated',
        'Has Charges',
        'Has Insolvency History',
        'Last Accounts Date',
        'Next Accounts Due',
        'Accounts Overdue',
        'Confirmation Statement Date',
        'Confirmation Statement Next Due',
        'Confirmation Statement Overdue',
        'Officers Total Count',
        'Officers Active Count',
        'Key Officers',
        'Error Message',
        'Lookup Status',
        'Created At'
    ]
    writer.writerow(headers)
    
    # Get company numbers for the campaign with related house data
    companies = CompanyNumber.objects.filter(
        campaign=campaign
    ).select_related('house_data').order_by('company_number')
    
    # Write data rows
    for company in companies:
        house_data = company.house_data
        
        # Extract data with fallback to empty strings
        row = [
            company.company_number,
            house_data.company_name if house_data and house_data.company_name else '',
            house_data.company_status if house_data and house_data.company_status else '',
            house_data.company_type if house_data and house_data.company_type else '',
            house_data.incorporation_date if house_data and house_data.incorporation_date else '',
            house_data.jurisdiction if house_data and house_data.jurisdiction else '',
            house_data.registered_office_address if house_data and house_data.registered_office_address else '',
            house_data.address_line_1 if house_data and house_data.address_line_1 else '',
            house_data.address_line_2 if house_data and house_data.address_line_2 else '',
            house_data.locality if house_data and house_data.locality else '',
            house_data.region if house_data and house_data.region else '',
            house_data.postal_code if house_data and house_data.postal_code else '',
            house_data.country if house_data and house_data.country else '',
            house_data.sic_codes if house_data and house_data.sic_codes else '',
            house_data.can_file if house_data and house_data.can_file else '',
            house_data.has_been_liquidated if house_data and house_data.has_been_liquidated else '',
            house_data.has_charges if house_data and house_data.has_charges else '',
            house_data.has_insolvency_history if house_data and house_data.has_insolvency_history else '',
            house_data.last_accounts_date if house_data and house_data.last_accounts_date else '',
            house_data.next_accounts_due if house_data and house_data.next_accounts_due else '',
            house_data.accounts_overdue if house_data and house_data.accounts_overdue else '',
            house_data.confirmation_statement_date if house_data and house_data.confirmation_statement_date else '',
            house_data.confirmation_statement_next_due if house_data and house_data.confirmation_statement_next_due else '',
            house_data.confirmation_statement_overdue if house_data and house_data.confirmation_statement_overdue else '',
            house_data.officers_total_count if house_data and house_data.officers_total_count else '',
            house_data.officers_active_count if house_data and house_data.officers_active_count else '',
            house_data.key_officers if house_data and house_data.key_officers else '',
            house_data.error_message if house_data and house_data.error_message else '',
            house_data.status if house_data and house_data.status else 'NOT_PROCESSED',
            house_data.created_at.strftime('%Y-%m-%d %H:%M:%S') if house_data and house_data.created_at else ''
        ]
        
        writer.writerow(row)
    
    return response


def get_companies_house_summary(campaign: Campaign) -> dict:
    """
    Get a summary of Companies House lookup data for a campaign.
    
    Args:
        campaign: The campaign to get summary for
        
    Returns:
        Dictionary with summary statistics
    """
    companies = CompanyNumber.objects.filter(campaign=campaign).select_related('house_data')
    
    total_companies = companies.count()
    with_house_data = companies.filter(house_data__isnull=False).count()
    
    # Count by status
    status_counts = {}
    for company in companies:
        if company.house_data and company.house_data.status:
            status = company.house_data.status
            status_counts[status] = status_counts.get(status, 0) + 1
        else:
            status_counts['NOT_PROCESSED'] = status_counts.get('NOT_PROCESSED', 0) + 1
    
    return {
        'total_companies': total_companies,
        'with_house_data': with_house_data,
        'without_house_data': total_companies - with_house_data,
        'completion_percentage': round((with_house_data / total_companies) * 100, 1) if total_companies > 0 else 0,
        'status_breakdown': status_counts
    }