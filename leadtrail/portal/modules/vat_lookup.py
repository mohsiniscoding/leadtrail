#!/usr/bin/env python3

"""
VAT Lookup Module
=================

This module provides functionality for searching VAT numbers by UK company name
using the vat-lookup.co.uk service with Webshare.io residential proxies.

Features:
- Company name-based VAT lookup
- Webshare.io proxy support (new IP per request)
- Consistent error handling (always returns structured data)
- Simple retry logic for request failures
- Intelligent company name sanitization and retry logic
- Exact matching for multiple results
"""

import logging
import os
import re
import time
import random
from datetime import datetime
from typing import Optional, Dict, Any, List
from enum import Enum
import requests
from dataclasses import dataclass
from dotenv import load_dotenv
from bs4 import BeautifulSoup
from urllib.parse import quote_plus

# Load environment variables
load_dotenv()

# Set up logging
logger = logging.getLogger(__name__)

class VATSearchStatus(Enum):
    """Enumeration for VAT search status codes."""
    SUCCESS = "SUCCESS"
    INVALID_COMPANY_NAME = "INVALID_COMPANY_NAME"
    VAT_NOT_FOUND = "VAT_NOT_FOUND"
    SERVICE_BLOCKED = "SERVICE_BLOCKED"
    NETWORK_ERROR = "NETWORK_ERROR"
    PARSING_ERROR = "PARSING_ERROR"
    MULTIPLE_RESULTS_NO_MATCH = "MULTIPLE_RESULTS_NO_MATCH"


@dataclass
class VATData:
    """Data structure for VAT lookup results."""
    company_name: str
    search_terms: List[str]  # All search terms attempted
    vat_number: str
    search_status: str
    extraction_timestamp: str
    processing_notes: str
    proxy_used: str
    
    @property
    def is_success(self) -> bool:
        """Check if the VAT search was successful."""
        return self.search_status == VATSearchStatus.SUCCESS.value
    
    @property
    def has_error(self) -> bool:
        """Check if there was an error during VAT search."""
        return not self.is_success
    
    @property
    def status_enum(self) -> VATSearchStatus:
        """Get the status as an enum value."""
        try:
            return VATSearchStatus(self.search_status)
        except ValueError:
            return VATSearchStatus.PARSING_ERROR
    
    @property
    def vat_found(self) -> bool:
        """Check if a VAT number was found."""
        return self.is_success and self.vat_number != "NOT_FOUND"


class VATLookupClient:
    """
    VAT Lookup client for searching VAT numbers by UK company name.
    
    Uses vat-lookup.co.uk service with Webshare.io residential proxies (new IP per request).
    Implements consistent error handling - always returns VATData objects.
    
    Usage:
        client = VATLookupClient()
        vat_data = client.lookup_vat_by_company_name("TESCO PLC")
    """
    
    def __init__(self):
        """
        Initialize VAT lookup client with proxy configuration.
        
        Raises:
            ValueError: If WEBSHARE_PROXY_URL environment variable is not set
        """
        self.base_url = "https://vat-lookup.co.uk"
        self.search_url = f"{self.base_url}/verify/search.php"
        
        # Proxy configuration
        self.proxy_url = os.getenv('WEBSHARE_PROXY_URL')
        if not self.proxy_url:
            raise ValueError(
                "WEBSHARE_PROXY_URL environment variable is required for VAT lookup functionality. "
                "Please set this environment variable with your Webshare.io proxy URL."
            )
        
        # Simple retry configuration
        self.max_retries = 3
        
        # Soft block detection patterns
        self.soft_block_patterns = [
            "Sorry it looks like you might be a robot",
            "too many requests"
        ]
        
        # Not found detection patterns
        self.not_found_patterns = [
            "Sorry we were unable to find any matches for your search"
        ]
        
        logger.info(f"Initialized VAT lookup client with proxy: {self.proxy_url}")
    
    def _get_proxy_config(self) -> Optional[Dict[str, str]]:
        """
        Get proxy configuration for requests.
        
        Returns:
            Proxy configuration dict or None if no proxy configured
        """
        if not self.proxy_url:
            return None
        
        return {
            'http': self.proxy_url,
            'https': self.proxy_url
        }
    
    def _create_session(self) -> requests.Session:
        """
        Create a new session with realistic headers and proxy configuration.
        
        Returns:
            Configured requests session
        """
        session = requests.Session()
        
        # Realistic browser headers (without cookies)
        session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'same-origin',
            'Sec-Fetch-User': '?1',
            'sec-ch-ua': '"Google Chrome";v="137", "Chromium";v="137", "Not/A)Brand";v="24"',
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': '"macOS"'
        })
        
        # Configure proxy
        proxy_config = self._get_proxy_config()
        if proxy_config:
            session.proxies.update(proxy_config)
            logger.debug(f"Session configured with proxy: {self.proxy_url}")
        
        return session
    
    
    def _sanitize_company_name(self, company_name: str) -> List[str]:
        """
        Generate multiple variations of company name for better search results.
        
        Args:
            company_name: Original company name
            
        Returns:
            List of sanitized company name variations to try
        """
        if not company_name or not company_name.strip():
            return []
        
        variations = []
        original = company_name.strip()
        variations.append(original)
        
        # Convert to uppercase for processing
        upper_name = original.upper()
        
        # Common transformations for better matching
        transformations = [
            # & CO variations
            (r'\s*&\s*CO\.\s*LTD\s*$', ' & COMPANY LIMITED'),
            (r'\s*&\s*CO\s*LTD\s*$', ' & COMPANY LIMITED'),
            (r'\s*&\s*CO\.\s*$', ' & COMPANY'),
            (r'\s*&\s*CO\s*$', ' & COMPANY'),
            
            # Standard abbreviations
            (r'\bLTD\.\s*$', 'LIMITED'),
            (r'\bLTD\s*$', 'LIMITED'),
            (r'\bCO\.\s*$', 'COMPANY'),
            (r'\bCO\s*$', 'COMPANY'),
            (r'\bCORP\.\s*$', 'CORPORATION'),
            (r'\bCORP\s*$', 'CORPORATION'),
            (r'\bINC\.\s*$', 'INCORPORATED'),
            (r'\bINC\s*$', 'INCORPORATED'),
            
            # Services and other common abbreviations
            (r'\bSVCS\b', 'SERVICES'),
            (r'\bSVC\b', 'SERVICE'),
            (r'\bGRP\b', 'GROUP'),
            (r'\bHLDGS?\b', 'HOLDINGS'),
            (r'\bMGMT\b', 'MANAGEMENT'),
            (r'\bMGT\b', 'MANAGEMENT'),
            (r'\bTECH\b', 'TECHNOLOGY'),
            (r'\bSYS\b', 'SYSTEMS'),
        ]
        
        # Apply transformations
        current_name = upper_name
        for pattern, replacement in transformations:
            if re.search(pattern, current_name):
                transformed = re.sub(pattern, replacement, current_name).strip()
                if transformed != current_name and transformed not in variations:
                    variations.append(transformed)
                current_name = transformed
        
        # Remove duplicates while preserving order
        unique_variations = []
        for variation in variations:
            if variation not in unique_variations:
                unique_variations.append(variation)
        
        logger.debug(f"Generated variations for '{original}': {unique_variations}")
        return unique_variations
    
    def _make_search_request(self, company_name: str, session: requests.Session) -> Optional[str]:
        """
        Make HTTP request to VAT lookup service.
        
        Args:
            company_name: Company name to search for
            session: Requests session to use
            
        Returns:
            HTML response or None if error
        """
        try:
            
            # Prepare form data exactly as in the CURL request
            form_data = f'CompanyName={quote_plus(company_name)}'
            
            # Set headers for POST request
            headers = {
                'Content-Type': 'application/x-www-form-urlencoded',
                'Origin': self.base_url,
                'Referer': f"{self.base_url}/",
                'Cache-Control': 'max-age=0'
            }
            
            logger.debug(f"Making VAT lookup request for company: {company_name}")
            response = session.post(
                self.search_url,
                data=form_data,
                headers=headers,
                timeout=30,
                allow_redirects=True
            )
            
            response.raise_for_status()
            
            logger.debug(f"VAT lookup request successful (status: {response.status_code})")
            return response.text
            
        except requests.RequestException as e:
            logger.error(f"VAT lookup request failed: {e}")
            return None
    
    def _detect_response_type(self, html_content: str) -> str:
        """
        Detect the type of response from the VAT lookup service.
        
        Args:
            html_content: HTML response content
            
        Returns:
            Response type: 'soft_block', 'not_found', 'results_found', or 'unknown'
        """
        # Check for soft block
        for pattern in self.soft_block_patterns:
            if pattern in html_content:
                logger.warning(f"Soft block detected: {pattern}")
                return 'soft_block'
        
        # Check for not found
        for pattern in self.not_found_patterns:
            if pattern in html_content:
                logger.info("No results found")
                return 'not_found'
        
        # Check for results table
        if '<table border=1' in html_content and 'VAT Number' in html_content:
            logger.debug("Results table found")
            return 'results_found'
        
        return 'unknown'
    
    def _parse_vat_results(self, html_content: str, search_term: str) -> Optional[Dict[str, str]]:
        """
        Parse VAT results from HTML response.
        
        Args:
            html_content: HTML response content
            search_term: Original search term for exact matching
            
        Returns:
            Dict with VAT info or None if not found/error
        """
        try:
            soup = BeautifulSoup(html_content, 'html.parser')
            
            # Find the results table
            table = soup.find('table', {'border': '1'})
            if not table:
                logger.warning("Results table not found in HTML")
                return None
            
            # Get all rows except header
            rows = table.find_all('tr')[1:]  # Skip header row
            if not rows:
                logger.warning("No data rows found in results table")
                return None
            
            results = []
            
            # Extract data from each row
            for row in rows:
                cells = row.find_all('td')
                if len(cells) >= 4:
                    company_name = cells[0].get_text(strip=True)
                    trade_name = cells[1].get_text(strip=True)
                    
                    # Extract VAT number from link
                    vat_link = cells[2].find('a')
                    vat_number = vat_link.get_text(strip=True) if vat_link else ""
                    
                    # Extract company ID from link
                    company_link = cells[3].find('a')
                    company_id = company_link.get_text(strip=True) if company_link else ""
                    
                    if vat_number and self._validate_vat_format(vat_number):
                        results.append({
                            'company_name': company_name,
                            'trade_name': trade_name,
                            'vat_number': vat_number,
                            'company_id': company_id
                        })
            
            if not results:
                logger.info("No valid VAT numbers found in results")
                return None
            
            logger.info(f"Found {len(results)} VAT result(s)")
            
            # If only one result, return it
            if len(results) == 1:
                logger.info(f"Single result found: {results[0]['vat_number']}")
                return results[0]
            
            # Multiple results - find exact match
            search_upper = search_term.upper().strip()
            for result in results:
                if result['company_name'].upper().strip() == search_upper:
                    logger.info(f"Exact match found: {result['vat_number']} for {result['company_name']}")
                    return result
            
            # No exact match found
            logger.warning(f"Multiple results found but no exact match for '{search_term}'")
            logger.debug(f"Available results: {[r['company_name'] for r in results]}")
            return None
            
        except Exception as e:
            logger.error(f"Error parsing VAT results: {e}")
            return None
    
    def _validate_vat_format(self, vat_number: str) -> bool:
        """
        Validate UK VAT number format.
        
        Args:
            vat_number: VAT number to validate
            
        Returns:
            True if valid format, False otherwise
        """
        if not vat_number:
            return False
        
        # UK VAT number format: GB followed by 9 digits
        pattern = r'^GB\d{9}$'
        return bool(re.match(pattern, vat_number.upper().replace(' ', '')))
    
    def _create_error_record(self, company_name: str, search_terms: List[str], 
                           status: VATSearchStatus, message: str, proxy_info: str = "none") -> VATData:
        """Create a VATData record for error cases."""
        return VATData(
            company_name=company_name,
            search_terms=search_terms,
            vat_number="NOT_FOUND",
            search_status=status.value,
            extraction_timestamp=datetime.now().isoformat(),
            processing_notes=message,
            proxy_used=proxy_info
        )
    
    def lookup_vat_by_company_name(self, company_name: str) -> VATData:
        """
        Search for VAT number by UK company name.
        
        This is the main method that orchestrates the VAT lookup process:
        1. Validates and sanitizes company name with variations
        2. Makes HTTP requests to VAT lookup service with Webshare.io proxy
        3. Handles different response types (soft block, not found, results)
        4. Implements simple retry logic with new IP per request
        5. Performs exact matching for multiple results
        
        Args:
            company_name: UK company name to search for
            
        Returns:
            VATData object (never returns None)
        """
        # Validate company name
        if not company_name or not company_name.strip():
            return self._create_error_record(
                "",
                [],
                VATSearchStatus.INVALID_COMPANY_NAME,
                "Company name cannot be empty"
            )
        
        original_name = company_name.strip()
        proxy_info = self.proxy_url if self.proxy_url else "direct"
        
        # Generate search variations
        search_variations = self._sanitize_company_name(original_name)
        if not search_variations:
            return self._create_error_record(
                original_name,
                [],
                VATSearchStatus.INVALID_COMPANY_NAME,
                "Could not generate valid search variations"
            )
        
        logger.info(f"Starting VAT lookup for company: {original_name}")
        logger.debug(f"Will try {len(search_variations)} search variations")
        
        # Try each search variation
        for variation_index, search_term in enumerate(search_variations):
            logger.info(f"Trying search variation {variation_index + 1}/{len(search_variations)}: {search_term}")
            
            # Implement exponential backoff with retries for soft blocks
            for attempt in range(self.max_retries):
                try:
                    # Create fresh session for each attempt
                    session = self._create_session()
                    
                    logger.debug(f"Attempt {attempt + 1}/{self.max_retries} for variation: {search_term}")
                    
                    # Make the search request
                    html_response = self._make_search_request(search_term, session)
                    
                    if not html_response:
                        if attempt < self.max_retries - 1:
                            logger.warning(f"Request failed, retrying...")
                            continue
                        else:
                            # Try next variation if available
                            break
                    
                    # Detect response type
                    response_type = self._detect_response_type(html_response)
                    
                    if response_type == 'soft_block':
                        if attempt < self.max_retries - 1:
                            logger.warning(f"Soft block detected, retrying with new IP...")
                            continue
                        else:
                            # Try next variation if available
                            break
                    
                    elif response_type == 'not_found':
                        # Try next variation
                        logger.info(f"No results for variation: {search_term}")
                        break
                    
                    elif response_type == 'results_found':
                        # Parse results
                        vat_result = self._parse_vat_results(html_response, search_term)
                        
                        if vat_result:
                            # Success!
                            logger.info(f"VAT lookup successful: {vat_result['vat_number']} for {vat_result['company_name']}")
                            return VATData(
                                company_name=original_name,
                                search_terms=search_variations[:variation_index + 1],
                                vat_number=vat_result['vat_number'],
                                search_status=VATSearchStatus.SUCCESS.value,
                                extraction_timestamp=datetime.now().isoformat(),
                                processing_notes=f"Successfully found VAT number {vat_result['vat_number']} using search term '{search_term}'",
                                proxy_used=proxy_info
                            )
                        else:
                            # Multiple results but no exact match
                            logger.warning(f"Multiple results found but no exact match for: {search_term}")
                            break
                    
                    else:
                        # Unknown response type
                        logger.warning(f"Unknown response type for: {search_term}")
                        break
                        
                except Exception as e:
                    logger.error(f"Attempt {attempt + 1} failed for variation '{search_term}': {e}")
                    if attempt < self.max_retries - 1:
                        continue
                    else:
                        # Try next variation if available
                        break
        
        # No results found after trying all variations
        logger.info(f"No VAT number found for: {original_name} (tried {len(search_variations)} variations)")
        return VATData(
            company_name=original_name,
            search_terms=search_variations,
            vat_number="NOT_FOUND",
            search_status=VATSearchStatus.VAT_NOT_FOUND.value,
            extraction_timestamp=datetime.now().isoformat(),
            processing_notes=f"No VAT registration found after trying {len(search_variations)} search variations",
            proxy_used=proxy_info
        )


def validate_company_name(company_name: str) -> bool:
    """
    Validate company name format for VAT lookup.
    
    Args:
        company_name: Company name to validate
        
    Returns:
        True if valid format, False otherwise
    """
    if not company_name or not company_name.strip():
        return False
    
    # Basic validation - must not be empty and reasonable length
    clean_name = company_name.strip()
    return 2 <= len(clean_name) <= 200  # Reasonable company name length


# Convenience function for direct usage
def lookup_vat_number(company_name: str) -> VATData:
    """
    Convenience function to lookup VAT number by UK company name.
    
    Args:
        company_name: UK company name to search for
        
    Returns:
        VATData object (never returns None - check search_status for success/failure)
    """
    client = VATLookupClient()
    return client.lookup_vat_by_company_name(company_name)


if __name__ == "__main__":
    # Test the module with 20 companies from 50_companies.csv
    test_companies = [
        "TIM O'BRIEN ACCOUNTANTS LTD",
        "TIM PHILLIPS & CO. LTD", 
        "TIM POLLARD LIMITED",
        "TIM RENNIE ASSOCIATES LIMITED",
        "TIM TAYLOR & CO LTD",
        "TIM WHITE LTD",
        "TIMBERLINE JOINERY LTD",
        "TIMBERS ACCOUNTANTS LTD",
        "TIME 4 BUSINESS SERVICES LTD",
        "TIME ACCOUNTANCY LIMITED",
        "TIME ACCOUNTS LIMITED",
        "TIME BUSINESS SERVICES LIMITED",
        "TIME FREEDOM ALCHEMIST LTD",
        "TIME IS LTD",
        "TIME TO FILE LIMITED",
        "TIME ZONE ACCOUNTANCY LTD",
        "TIMES ACCOUNTANCY SERVICES LIMITED",
        "TIMMS ACCOUNTANTS LIMITED", 
        "TIMOTHY HIGNETT AND PARTNERS LIMITED",
        "TIMOTHY JOHNSON LIMITED"
    ]
    
    print(f"Testing VAT lookup for {len(test_companies)} companies:")
    print("=" * 80)
    
    results = []
    for i, company_name in enumerate(test_companies, 1):
        print(f"\n[{i:2d}/20] Testing: {company_name}")
        print("-" * 60)
        
        try:
            vat_data = lookup_vat_number(company_name)
            
            # Store results for summary
            results.append({
                'company': company_name,
                'vat_number': vat_data.vat_number,
                'status': vat_data.search_status,
                'success': vat_data.is_success,
                'vat_found': vat_data.vat_found,
                'search_terms_count': len(vat_data.search_terms),
                'proxy': vat_data.proxy_used
            })
            
            # Print individual result
            print(f"✅ Status: {vat_data.search_status}")
            print(f"📞 VAT Number: {vat_data.vat_number}")
            print(f"🔍 Search Terms Tried: {len(vat_data.search_terms)}")
            print(f"📝 Notes: {vat_data.processing_notes[:100]}{'...' if len(vat_data.processing_notes) > 100 else ''}")
            print(f"🌐 Proxy: {vat_data.proxy_used}")
            
        except Exception as e:
            print(f"❌ Error processing '{company_name}': {e}")
            results.append({
                'company': company_name,
                'vat_number': 'ERROR',
                'status': 'ERROR',
                'success': False,
                'vat_found': False,
                'search_terms_count': 0,
                'proxy': 'unknown'
            })
    
    # Print summary
    print("\n" + "=" * 80)
    print("SUMMARY RESULTS")
    print("=" * 80)
    
    success_count = sum(1 for r in results if r['success'])
    vat_found_count = sum(1 for r in results if r['vat_found'])
    error_count = sum(1 for r in results if r['status'] == 'ERROR')
    
    print(f"📊 Total Companies Tested: {len(results)}")
    print(f"✅ Successful Requests: {success_count}")
    print(f"📞 VAT Numbers Found: {vat_found_count}")
    print(f"❌ Errors: {error_count}")
    print(f"📈 Success Rate: {success_count/len(results)*100:.1f}%")
    print(f"📞 VAT Discovery Rate: {vat_found_count/len(results)*100:.1f}%")
    
    print(f"\n📞 Companies with VAT Numbers Found:")
    for result in results:
        if result['vat_found']:
            print(f"  • {result['company']}: {result['vat_number']}")
    
    print(f"\n❌ Companies with Errors:")
    for result in results:
        if result['status'] == 'ERROR':
            print(f"  • {result['company']}")
    
    print(f"\n🔍 Companies Not Found:")
    for result in results:
        if result['status'] == 'VAT_NOT_FOUND':
            print(f"  • {result['company']} (tried {result['search_terms_count']} variations)") 