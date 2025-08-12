#!/usr/bin/env python3

"""
Companies House API Search Module
=================================

This module provides functionality for searching and extracting company data
from the Companies House API using multiple endpoints.

Features:
- Multiple API endpoint integration
- Rate limiting compliance
- Enhanced data extraction (40+ fields)
- Error handling and retry logic
"""

import logging
import os
import time
from datetime import datetime
from typing import Optional, Dict, Any
from enum import Enum
import requests
from dataclasses import dataclass
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Set up logging
logger = logging.getLogger(__name__)


class CompanySearchStatus(Enum):
    """Enumeration for company search status codes."""
    SUCCESS = "SUCCESS"
    INVALID_COMPANY_NUMBER = "INVALID_COMPANY_NUMBER"
    COMPANY_NOT_FOUND = "COMPANY_NOT_FOUND"
    API_ERROR = "API_ERROR" 
    EXTRACTION_ERROR = "EXTRACTION_ERROR"
    RATE_LIMIT_ERROR = "RATE_LIMIT_ERROR"


@dataclass
class CompanyData:
    """Data structure for Companies House company information."""
    company_number: str
    company_name: str
    company_status: str
    company_type: str
    incorporation_date: str
    jurisdiction: str
    
    # Basic registered office address
    registered_office_address: str
    
    # Detailed address components from registered-office-address endpoint
    address_line_1: str
    address_line_2: str
    locality: str
    region: str
    postal_code: str
    country: str
    
    # Address status indicators
    registered_office_is_in_dispute: str
    undeliverable_registered_office_address: str
    
    # Business activity and classification
    sic_codes: str
    
    # Company status and risk indicators
    can_file: str
    has_been_liquidated: str
    has_charges: str
    has_insolvency_history: str
    
    # Previous company names
    previous_company_names: str
    
    # Accounts information (enhanced)
    last_accounts_date: str
    last_accounts_period_start: str
    last_accounts_period_end: str
    last_accounts_type: str
    next_accounts_due: str
    next_accounts_period_end: str
    accounts_overdue: str
    accounting_reference_date: str
    
    # Confirmation statement details
    confirmation_statement_date: str
    confirmation_statement_next_due: str
    confirmation_statement_overdue: str
    
    # Officers information (enhanced)
    officers_total_count: int
    officers_active_count: int
    officers_resigned_count: int
    officers_inactive_count: int
    key_officers: str  # CEO, directors, company secretary
    
    # Additional dates
    last_full_members_list_date: str
    
    # Processing metadata
    extraction_timestamp: str
    api_response_status: str
    endpoints_called: str
    rate_limit_status: str
    notes: str
    
    @property
    def is_success(self) -> bool:
        """Check if the search was successful."""
        return self.api_response_status == CompanySearchStatus.SUCCESS.value
    
    @property
    def has_error(self) -> bool:
        """Check if there was an error during search."""
        return not self.is_success
    
    @property
    def status_enum(self) -> CompanySearchStatus:
        """Get the status as an enum value."""
        try:
            return CompanySearchStatus(self.api_response_status)
        except ValueError:
            return CompanySearchStatus.EXTRACTION_ERROR


class CompaniesHouseAPIClient:
    """
    Companies House API client for extracting company data.
    
    Implements rate limiting as per Companies House documentation:
    - 600 requests per 5 minutes (default)
    - Automatic retry with exponential backoff on rate limit
    
    Usage:
        client = CompaniesHouseAPIClient(api_key="your_key")
        company_data = client.extract_company_data("00445790")
    """
    
    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize Companies House API client.
        
        Args:
            api_key: Companies House API key. If None, tries environment variable.
            
        Raises:
            ValueError: If API key is not provided and COMPANIES_HOUSE_API_KEY env var is not set
        """
        self.base_url = "https://api.company-information.service.gov.uk"
        
        # Get API key from environment variable or parameter
        self.api_key = api_key or os.getenv('COMPANIES_HOUSE_API_KEY')
        
        if not self.api_key:
            raise ValueError(
                "Companies House API key is required. Please provide it as a parameter "
                "or set the COMPANIES_HOUSE_API_KEY environment variable."
            )
        
        # Rate limiting configuration
        self.rate_limit = int(os.getenv('COMPANIES_HOUSE_RATE_LIMIT', 600))
        self.requests_made = 0
        self.start_time = time.time()
        
        # Configure session
        self.session = requests.Session()
        self.session.auth = (self.api_key, '')
        self.session.headers.update({
            'User-Agent': 'CompanyVATSearch/1.0 (Modular Architecture)',
            'Accept': 'application/json'
        })
        
        logger.info(f"Initialized Companies House API client with rate limit: {self.rate_limit}/5min")
    
    def _check_rate_limit(self) -> None:
        """
        Check and enforce rate limiting as per Companies House guidelines.
        
        Rate limit: 600 requests per 5 minutes (300 seconds)
        """
        current_time = time.time()
        elapsed_time = current_time - self.start_time
        
        # Reset counter if 5 minutes have passed
        if elapsed_time >= 300:  # 5 minutes
            self.requests_made = 0
            self.start_time = current_time
            logger.debug("Rate limit window reset")
            return
        
        # Check if we're approaching the limit
        if self.requests_made >= self.rate_limit:
            wait_time = 300 - elapsed_time
            logger.warning(f"Rate limit reached. Waiting {wait_time:.1f} seconds...")
            time.sleep(wait_time)
            self.requests_made = 0
            self.start_time = time.time()
    
    def _make_api_request(self, url: str, endpoint_name: str) -> Optional[Dict[str, Any]]:
        """
        Make API request with rate limiting and error handling.
        
        Args:
            url: Full API URL
            endpoint_name: Name of endpoint for logging
            
        Returns:
            JSON response or None if error
        """
        try:
            self._check_rate_limit()
            
            logger.debug(f"Making API request to: {endpoint_name}")
            response = self.session.get(url, timeout=30)
            self.requests_made += 1
            
            if response.status_code == 401:
                logger.error("API authentication failed - check your API key")
                return None
            elif response.status_code == 404:
                logger.warning(f"Resource not found: {endpoint_name}")
                return None
            elif response.status_code == 429:
                logger.warning("Rate limit exceeded - retrying...")
                time.sleep(60)  # Wait 1 minute and retry
                return self._make_api_request(url, endpoint_name)
            
            response.raise_for_status()
            logger.debug(f"API request successful: {endpoint_name}")
            return response.json()
            
        except requests.RequestException as e:
            logger.error(f"API request failed for {endpoint_name}: {e}")
            return None
    
    def get_company_profile(self, company_number: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve company profile from Companies House API.
        
        Endpoint: GET /company/{companyNumber}
        
        Args:
            company_number: UK company registration number (8 digits)
            
        Returns:
            Company profile data or None if error
        """
        normalized_number = self._normalize_company_number(company_number)
        url = f"{self.base_url}/company/{normalized_number}"
        
        logger.info(f"Fetching company profile for: {normalized_number}")
        return self._make_api_request(url, f"company_profile_{normalized_number}")
    
    def get_registered_office_address(self, company_number: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve detailed registered office address from Companies House API.
        
        Endpoint: GET /company/{companyNumber}/registered-office-address
        
        Args:
            company_number: UK company registration number (8 digits)
            
        Returns:
            Registered office address data or None if error
        """
        normalized_number = self._normalize_company_number(company_number)
        url = f"{self.base_url}/company/{normalized_number}/registered-office-address"
        
        logger.info(f"Fetching registered office address for: {normalized_number}")
        return self._make_api_request(url, f"registered_office_{normalized_number}")
    
    def get_company_officers(self, company_number: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve company officers from Companies House API.
        
        Endpoint: GET /company/{companyNumber}/officers
        
        Args:
            company_number: UK company registration number
            
        Returns:
            Officers data or None if error
        """
        normalized_number = self._normalize_company_number(company_number)
        url = f"{self.base_url}/company/{normalized_number}/officers"
        
        logger.info(f"Fetching officers for: {normalized_number}")
        return self._make_api_request(url, f"officers_{normalized_number}")
    
    def _normalize_company_number(self, company_number: str) -> str:
        """
        Normalize company number to 8-digit format with leading zeros.
        
        Args:
            company_number: Raw company number input
            
        Returns:
            Normalized 8-digit company number
        """
        # Remove any non-numeric characters
        clean_number = ''.join(filter(str.isdigit, company_number))
        
        # Pad with leading zeros to 8 digits
        return clean_number.zfill(8)
    
    def _extract_key_officers(self, officers_data: Dict[str, Any]) -> str:
        """
        Extract key officers (CEO, directors, company secretary) from officers data.
        
        Args:
            officers_data: Officers API response data
            
        Returns:
            String with key officer names and roles
        """
        if not officers_data or 'items' not in officers_data:
            return "NOT_AVAILABLE"
        
        key_roles = ['ceo', 'director', 'secretary', 'company-secretary']
        key_officers = []
        
        for officer in officers_data['items']:
            role = officer.get('officer_role', '').lower()
            name = officer.get('name', '')
            
            if role in key_roles and name:
                # Format: "Name (Role)"
                formatted_role = role.replace('-', ' ').title()
                key_officers.append(f"{name} ({formatted_role})")
                
                # Limit to top 5 key officers to avoid overwhelming CSV
                if len(key_officers) >= 5:
                    break
        
        return '; '.join(key_officers) if key_officers else "NOT_AVAILABLE"
    
    def _create_error_record(self, company_number: str, status: CompanySearchStatus, message: str, 
                           endpoints: list, rate_info: str) -> CompanyData:
        """Create a CompanyData record for error cases."""
        return CompanyData(
            company_number=company_number,
            company_name="NOT_FOUND",
            company_status="NOT_FOUND",
            company_type="NOT_FOUND",
            incorporation_date="NOT_FOUND",
            jurisdiction="NOT_FOUND",
            registered_office_address="NOT_FOUND",
            address_line_1="NOT_FOUND",
            address_line_2="NOT_FOUND",
            locality="NOT_FOUND",
            region="NOT_FOUND",
            postal_code="NOT_FOUND",
            country="NOT_FOUND",
            registered_office_is_in_dispute="NOT_FOUND",
            undeliverable_registered_office_address="NOT_FOUND",
            sic_codes="NOT_FOUND",
            can_file="NOT_FOUND",
            has_been_liquidated="NOT_FOUND",
            has_charges="NOT_FOUND",
            has_insolvency_history="NOT_FOUND",
            previous_company_names="NOT_FOUND",
            last_accounts_date="NOT_FOUND",
            last_accounts_period_start="NOT_FOUND",
            last_accounts_period_end="NOT_FOUND",
            last_accounts_type="NOT_FOUND",
            next_accounts_due="NOT_FOUND",
            next_accounts_period_end="NOT_FOUND",
            accounts_overdue="NOT_FOUND",
            accounting_reference_date="NOT_FOUND",
            confirmation_statement_date="NOT_FOUND",
            confirmation_statement_next_due="NOT_FOUND",
            confirmation_statement_overdue="NOT_FOUND",
            officers_total_count=0,
            officers_active_count=0,
            officers_resigned_count=0,
            officers_inactive_count=0,
            key_officers="NOT_FOUND",
            last_full_members_list_date="NOT_FOUND",
            extraction_timestamp=datetime.now().isoformat(),
            api_response_status=status.value,
            endpoints_called=', '.join(endpoints),
            rate_limit_status=rate_info,
            notes=message,
        )
    
    def extract_company_data(self, company_number: str) -> CompanyData:
        """
        Extract and structure company data from multiple API endpoints.
        
        This is the main method that orchestrates data extraction from:
        - GET /company/{companyNumber}
        - GET /company/{companyNumber}/registered-office-address
        - GET /company/{companyNumber}/officers
        
        Args:
            company_number: UK company registration number
            
        Returns:
            Structured CompanyData (never returns None)
        """
        try:
            endpoints_called = []
            rate_limit_info = f"Requests made: {self.requests_made}/{self.rate_limit}"
            
            # Step 1: Get company profile
            logger.info("Step 1: Fetching company profile...")
            profile = self.get_company_profile(company_number)
            endpoints_called.append("company_profile")
            
            if not profile:
                return self._create_error_record(
                    company_number, 
                    CompanySearchStatus.COMPANY_NOT_FOUND,
                    "Company not found in Companies House database",
                    endpoints_called,
                    rate_limit_info
                )
            
            # Step 2: Get detailed registered office address
            logger.info("Step 2: Fetching registered office address...")
            registered_address = self.get_registered_office_address(company_number)
            endpoints_called.append("registered_office_address")
            
            # Step 3: Get officers data
            logger.info("Step 3: Fetching company officers...")
            officers = self.get_company_officers(company_number)
            endpoints_called.append("officers")
            
            # Process basic address from profile
            basic_address_parts = []
            basic_office = profile.get('registered_office_address', {})
            for field in ['address_line_1', 'address_line_2', 'locality', 'region', 'postal_code', 'country']:
                if basic_office.get(field):
                    basic_address_parts.append(basic_office[field])
            basic_full_address = ', '.join(basic_address_parts)
            
            # Process detailed address components
            if registered_address:
                address_line_1 = registered_address.get('address_line_1', '')
                address_line_2 = registered_address.get('address_line_2', '')
                locality = registered_address.get('locality', '')
                region = registered_address.get('region', '')
                postal_code = registered_address.get('postal_code', '')
                country = registered_address.get('country', '')
            else:
                # Fallback to basic address components
                address_line_1 = basic_office.get('address_line_1', '')
                address_line_2 = basic_office.get('address_line_2', '')
                locality = basic_office.get('locality', '')
                region = basic_office.get('region', '')
                postal_code = basic_office.get('postal_code', '')
                country = basic_office.get('country', '')
            
            # Extract business and risk data
            sic_codes = profile.get('sic_codes', [])
            sic_codes_str = ', '.join(sic_codes) if sic_codes else "NOT_AVAILABLE"
            
            # Company status and risk indicators
            can_file = str(profile.get('can_file', 'NOT_AVAILABLE'))
            has_been_liquidated = str(profile.get('has_been_liquidated', 'NOT_AVAILABLE'))
            has_charges = str(profile.get('has_charges', 'NOT_AVAILABLE'))
            has_insolvency_history = str(profile.get('has_insolvency_history', 'NOT_AVAILABLE'))
            
            # Address status indicators
            registered_office_is_in_dispute = str(profile.get('registered_office_is_in_dispute', 'NOT_AVAILABLE'))
            undeliverable_registered_office_address = str(profile.get('undeliverable_registered_office_address', 'NOT_AVAILABLE'))
            
            # Previous company names
            previous_names = profile.get('previous_company_names', [])
            previous_names_str = '; '.join([f"{name.get('name', '')} ({name.get('ceased_on', '')})" for name in previous_names]) if previous_names else "NOT_AVAILABLE"
            
            # Enhanced accounts data
            accounts = profile.get('accounts', {})
            last_accounts = accounts.get('last_accounts', {})
            next_accounts = accounts.get('next_accounts', {})
            accounting_ref = accounts.get('accounting_reference_date', {})
            
            # Confirmation statement details
            confirmation_statement = profile.get('confirmation_statement', {})
            
            # Officers data analysis
            officers_total = len(officers.get('items', [])) if officers else 0
            officers_active = officers.get('active_count', 0) if officers else 0
            officers_resigned = officers.get('resigned_count', 0) if officers else 0
            officers_inactive = officers.get('inactive_count', 0) if officers else 0
            key_officers = self._extract_key_officers(officers) if officers else "NOT_AVAILABLE"
            
            # Create and return structured data
            return CompanyData(
                company_number=profile.get('company_number', company_number),
                company_name=profile.get('company_name', 'NOT_AVAILABLE'),
                company_status=profile.get('company_status', 'NOT_AVAILABLE'),
                company_type=profile.get('type', 'NOT_AVAILABLE'),
                incorporation_date=profile.get('date_of_creation', 'NOT_AVAILABLE'),
                jurisdiction=profile.get('jurisdiction', 'NOT_AVAILABLE'),
                
                # Address information
                registered_office_address=basic_full_address,
                address_line_1=address_line_1,
                address_line_2=address_line_2,
                locality=locality,
                region=region,
                postal_code=postal_code,
                country=country,
                
                # Address status indicators
                registered_office_is_in_dispute=registered_office_is_in_dispute,
                undeliverable_registered_office_address=undeliverable_registered_office_address,
                
                # Business activity and classification
                sic_codes=sic_codes_str,
                
                # Company status and risk indicators
                can_file=can_file,
                has_been_liquidated=has_been_liquidated,
                has_charges=has_charges,
                has_insolvency_history=has_insolvency_history,
                
                # Previous company names
                previous_company_names=previous_names_str,
                
                # Accounts information (enhanced)
                last_accounts_date=last_accounts.get('made_up_to', 'NOT_AVAILABLE'),
                last_accounts_period_start=last_accounts.get('period_start_on', 'NOT_AVAILABLE'),
                last_accounts_period_end=last_accounts.get('period_end_on', 'NOT_AVAILABLE'),
                last_accounts_type=last_accounts.get('type', 'NOT_AVAILABLE'),
                next_accounts_due=accounts.get('next_due', 'NOT_AVAILABLE'),
                next_accounts_period_end=next_accounts.get('period_end_on', 'NOT_AVAILABLE'),
                accounts_overdue=str(accounts.get('overdue', 'NOT_AVAILABLE')),
                accounting_reference_date=f"{accounting_ref.get('day', '')}/{accounting_ref.get('month', '')}" if accounting_ref.get('day') and accounting_ref.get('month') else 'NOT_AVAILABLE',
                
                # Confirmation statement details
                confirmation_statement_date=confirmation_statement.get('last_made_up_to', 'NOT_AVAILABLE'),
                confirmation_statement_next_due=confirmation_statement.get('next_due', 'NOT_AVAILABLE'),
                confirmation_statement_overdue=str(confirmation_statement.get('overdue', 'NOT_AVAILABLE')),
                
                # Officers information (enhanced)
                officers_total_count=officers_total,
                officers_active_count=officers_active,
                officers_resigned_count=officers_resigned,
                officers_inactive_count=officers_inactive,
                key_officers=key_officers,
                
                # Additional dates
                last_full_members_list_date=profile.get('last_full_members_list_date', 'NOT_AVAILABLE'),
                
                # Processing metadata
                extraction_timestamp=datetime.now().isoformat(),
                api_response_status=CompanySearchStatus.SUCCESS.value,
                endpoints_called=', '.join(endpoints_called),
                rate_limit_status=rate_limit_info,
                notes=f"Successfully extracted enhanced data for {profile.get('company_name', 'company')} using {len(endpoints_called)} endpoints",
            )
            
        except Exception as e:
            logger.error(f"Data extraction failed: {e}")
            return self._create_error_record(
                company_number,
                CompanySearchStatus.EXTRACTION_ERROR, 
                f"Data extraction failed: {str(e)}",
                endpoints_called if 'endpoints_called' in locals() else [],
                f"Requests made: {self.requests_made}/{self.rate_limit}"
            )


def validate_company_number(company_number: str) -> bool:
    """
    Validate UK company number format.
    
    Args:
        company_number: Company number to validate
        
    Returns:
        True if valid format, False otherwise
    """
    
    # Must be between 1-8 characters
    return 1 <= len(company_number) <= 8


# Convenience function for direct usage
def search_company(company_number: str, api_key: Optional[str] = None) -> CompanyData:
    """
    Convenience function to search for a company using Companies House API.
    
    Args:
        company_number: UK company registration number
        api_key: Optional API key (uses environment variable if not provided)
        
    Returns:
        CompanyData object (never returns None - check api_response_status for success/failure)
    """
    if not validate_company_number(company_number):
        logger.error(f"Invalid company number format: {company_number}")
        return CompanyData(
            company_number=company_number,
            company_name="INVALID_INPUT",
            company_status="INVALID_INPUT", 
            company_type="INVALID_INPUT",
            incorporation_date="INVALID_INPUT",
            jurisdiction="INVALID_INPUT",
            registered_office_address="INVALID_INPUT",
            address_line_1="INVALID_INPUT",
            address_line_2="INVALID_INPUT", 
            locality="INVALID_INPUT",
            region="INVALID_INPUT",
            postal_code="INVALID_INPUT",
            country="INVALID_INPUT",
            registered_office_is_in_dispute="INVALID_INPUT",
            undeliverable_registered_office_address="INVALID_INPUT",
            sic_codes="INVALID_INPUT",
            can_file="INVALID_INPUT",
            has_been_liquidated="INVALID_INPUT",
            has_charges="INVALID_INPUT",
            has_insolvency_history="INVALID_INPUT",
            previous_company_names="INVALID_INPUT",
            last_accounts_date="INVALID_INPUT",
            last_accounts_period_start="INVALID_INPUT",
            last_accounts_period_end="INVALID_INPUT",
            last_accounts_type="INVALID_INPUT",
            next_accounts_due="INVALID_INPUT",
            next_accounts_period_end="INVALID_INPUT",
            accounts_overdue="INVALID_INPUT",
            accounting_reference_date="INVALID_INPUT",
            confirmation_statement_date="INVALID_INPUT",
            confirmation_statement_next_due="INVALID_INPUT",
            confirmation_statement_overdue="INVALID_INPUT",
            officers_total_count=0,
            officers_active_count=0,
            officers_resigned_count=0,
            officers_inactive_count=0,
            key_officers="INVALID_INPUT",
            last_full_members_list_date="INVALID_INPUT",
            extraction_timestamp=datetime.now().isoformat(),
            api_response_status=CompanySearchStatus.INVALID_COMPANY_NUMBER.value,
            endpoints_called="validation_failed",
            rate_limit_status="not_applicable",
            notes=f"Invalid company number format: {company_number}. Must be 1-8 digits.",
        )
    
    client = CompaniesHouseAPIClient(api_key=api_key)
    return client.extract_company_data(company_number) 


if __name__ == "__main__":
    company_number = "9938793"
    api_key = os.getenv("COMPANIES_HOUSE_API_KEY")
    company_data = search_company(company_number, api_key)
    print(company_data)
    print(company_data.is_success)