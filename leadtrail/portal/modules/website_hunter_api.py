#!/usr/bin/env python3

"""
Website Hunter API Module
==========================

This module provides functionality for finding business websites using SERP API.
Implements cost-efficient combined search approach with query versioning.

Features:
- ZenSERP API integration for website search
- Combined identifier search (company number, VAT, name in single query)
- Dual query versions: standard keywords vs inurl: operators
- 66% API cost reduction (1 request vs 3 requests per company)
- Rate limiting and quota management
- Robust error handling and structured responses
- Domain extraction and filtering
"""

import logging
import os
import re
import time
from datetime import datetime
from typing import Optional, Dict, Any, List
from enum import Enum
import requests
from dataclasses import dataclass
from dotenv import load_dotenv
from urllib.parse import urlparse

# Load environment variables
load_dotenv()

# Set up logging
logger = logging.getLogger(__name__)


class WebsiteSearchStatus(Enum):
    """Enumeration for website search status codes."""
    SUCCESS = "SUCCESS"
    INVALID_IDENTIFIER = "INVALID_IDENTIFIER"
    NO_WEBSITES_FOUND = "NO_WEBSITES_FOUND"
    API_ERROR = "API_ERROR"
    QUOTA_EXCEEDED = "QUOTA_EXCEEDED"
    NETWORK_ERROR = "NETWORK_ERROR"
    PARSING_ERROR = "PARSING_ERROR"


@dataclass
class WebsiteSearchResult:
    """Data structure for website search results."""
    identifier: str
    search_query: str
    websites_found: List[str]
    search_status: str
    extraction_timestamp: str
    processing_notes: str
    api_quota_remaining: Optional[int]
    total_results_found: int
    
    @property
    def is_success(self) -> bool:
        """Check if the website search was successful."""
        return self.search_status == WebsiteSearchStatus.SUCCESS.value
    
    @property
    def has_error(self) -> bool:
        """Check if there was an error during website search."""
        return not self.is_success
    
    @property
    def status_enum(self) -> WebsiteSearchStatus:
        """Get the status as an enum value."""
        try:
            return WebsiteSearchStatus(self.search_status)
        except ValueError:
            return WebsiteSearchStatus.PARSING_ERROR
    
    @property
    def websites_found_count(self) -> int:
        """Get the count of unique websites found."""
        return len(self.websites_found)


class WebsiteHunterClient:
    """
    Website Hunter client for finding business websites using SERP data.
    
    Uses ZenSERP API to search for company websites based on company identifiers.
    Implements rate limiting and quota management.
    
    Usage:
        client = WebsiteHunterClient()
        result = client.find_company_website("13606514")
    """
    
    def __init__(self, api_key: Optional[str] = None, query_version: int = 1):
        """
        Initialize Website Hunter client.
        
        Args:
            api_key: ZenSERP API key. If None, tries environment variable.
            query_version: Query builder version (1 or 2). Default is 1.
                          1 = Standard keyword search ("keyword" OR "keyword")
                          2 = URL-based search (inurl:about OR inurl:contact)
            
        Raises:
            ValueError: If API key is not provided and ZENSERP_API_KEY env var is not set
        """
        self.base_url = "https://app.zenserp.com/api/v2"
        self.status_url = f"{self.base_url}/status"
        self.search_url = f"{self.base_url}/search"
        
        # Get API key from environment variable or parameter
        self.api_key = api_key or os.getenv('ZENSERP_API_KEY')
        
        if not self.api_key:
            raise ValueError(
                "ZenSERP API key is required. Please provide it as a parameter "
                "or set the ZENSERP_API_KEY environment variable."
            )
        
        # Query version control
        self.query_version = query_version
        if query_version not in [1, 2]:
            raise ValueError("query_version must be 1 or 2")
        
        # Rate limiting
        self.last_request_time = 0
        self.min_request_delay = 1.0  # 1 second between requests
        
        # Configure session
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'WebsiteHunter/1.0 (Business Website Discovery)',
            'apikey': self.api_key
        })
        
        logger.info(f"Initialized Website Hunter client with ZenSERP API (Query Version {query_version})")
    
    def _rate_limit(self) -> None:
        """Implement rate limiting between API requests."""
        current_time = time.time()
        time_since_last = current_time - self.last_request_time
        
        if time_since_last < self.min_request_delay:
            sleep_time = self.min_request_delay - time_since_last
            logger.debug(f"Rate limiting: sleeping {sleep_time:.2f} seconds")
            time.sleep(sleep_time)
        
        self.last_request_time = time.time()
    
    def check_api_quota(self) -> Optional[Dict[str, Any]]:
        """
        Check remaining API quota for ZenSERP.
        
        Returns:
            API status information or None if error
        """
        try:
            self._rate_limit()
            
            logger.debug("Checking ZenSERP API quota")
            response = self.session.get(self.status_url, timeout=30)
            
            if response.status_code == 401:
                logger.error("API authentication failed - check your API key")
                return None
            elif response.status_code == 403:
                logger.error("API access denied - check your API key")
                return None
            elif response.status_code == 429:
                logger.warning("API rate limit exceeded")
                return None
            
            response.raise_for_status()
            status_data = response.json()
            
            logger.debug(f"API quota check successful: {status_data}")
            return status_data
            
        except requests.RequestException as e:
            logger.error(f"API quota check failed: {e}")
            return None
        except Exception as e:
            logger.error(f"Error parsing API status response: {e}")
            return None
    
    def _build_search_query(self, identifiers: List[str], 
                           search_keywords: List[str],
                           excluded_domains: List[str]) -> str:
        """
        Build ZenSERP search query string (Version 1) with combined identifiers.
        
        Args:
            identifiers: List of company identifiers (company number, VAT, name, etc.)
            search_keywords: Keywords to search for
            excluded_domains: Domains to exclude
            
        Returns:
            Formatted search query string
        """
        # Filter out empty identifiers
        valid_identifiers = [id for id in identifiers if id and id.strip()]
        
        if not valid_identifiers:
            raise ValueError("At least one valid identifier is required")
        
        # Build the OR expression for identifiers
        identifiers_or = " OR ".join([f'"{identifier}"' for identifier in valid_identifiers])
        
        # Build the OR expression for keywords
        keywords_or = " OR ".join([f'"{keyword}"' for keyword in search_keywords])
        
        # Build the site exclusions
        site_exclusions = " ".join([f"-site:{domain}" for domain in excluded_domains])
        
        # Combine all parts
        query = f'({identifiers_or}) ({keywords_or}) {site_exclusions}'
        
        logger.debug(f"Built search query v1: {query}")
        return query
    
    def _build_search_query_v2(self, identifiers: List[str], 
                              search_keywords: List[str],
                              excluded_domains: List[str]) -> str:
        """
        Build ZenSERP search query string (Version 2) using inurl: operators with combined identifiers.
        
        This version searches for pages with specific URL patterns rather than content keywords.
        More targeted for finding relevant company pages like about, contact, privacy, etc.
        
        Args:
            identifiers: List of company identifiers (company number, VAT, name, etc.)
            search_keywords: Keywords to convert to inurl searches
            excluded_domains: Domains to exclude
            
        Returns:
            Formatted search query string with inurl: operators
        """
        # Filter out empty identifiers
        valid_identifiers = [id for id in identifiers if id and id.strip()]
        
        if not valid_identifiers:
            raise ValueError("At least one valid identifier is required")
        
        # Build the OR expression for identifiers
        identifiers_or = " OR ".join([f'"{identifier}"' for identifier in valid_identifiers])
        
        # Map keywords to inurl operators
        inurl_keywords = []
        for keyword in search_keywords:
            # Convert keywords to URL-friendly terms
            if "privacy policy" in keyword.lower():
                inurl_keywords.append("inurl:privacy")
            elif "terms" in keyword.lower():
                inurl_keywords.append("inurl:terms")
            elif "about us" in keyword.lower() or "about" in keyword.lower():
                inurl_keywords.append("inurl:about")
            elif "contact" in keyword.lower():
                inurl_keywords.append("inurl:contact")
            elif "company" in keyword.lower():
                inurl_keywords.append("inurl:company")
            else:
                # For other keywords, create inurl version
                clean_keyword = keyword.lower().replace(" ", "").replace("policy", "").replace("information", "")
                if clean_keyword:
                    inurl_keywords.append(f"inurl:{clean_keyword}")
        
        # Remove duplicates while preserving order
        unique_inurl_keywords = []
        for keyword in inurl_keywords:
            if keyword not in unique_inurl_keywords:
                unique_inurl_keywords.append(keyword)
        
        # Build the OR expression for inurl keywords
        inurl_or = " OR ".join(unique_inurl_keywords)
        
        # Build the site exclusions
        site_exclusions = " ".join([f"-site:{domain}" for domain in excluded_domains])
        
        # Combine all parts
        query = f'({identifiers_or}) ({inurl_or}) {site_exclusions}'
        
        logger.debug(f"Built search query v2: {query}")
        return query
    
    def _make_search_request(self, query: str) -> Optional[Dict[str, Any]]:
        """
        Make search request to ZenSERP API.
        
        Args:
            query: Search query string
            
        Returns:
            Search results or None if error
        """
        try:
            self._rate_limit()
            
            params = {'q': query}
            
            logger.debug(f"Making ZenSERP search request: {query}")
            response = self.session.get(self.search_url, params=params, timeout=30)
            
            if response.status_code == 401:
                logger.error("API authentication failed - check your API key")
                return None
            elif response.status_code == 429: 
                logger.warning("API rate limit exceeded")
                return None
            elif response.status_code == 402:
                logger.error("API quota exceeded - payment required")
                return None
            
            response.raise_for_status()
            search_results = response.json()
            
            logger.debug(f"Search request successful, got {len(search_results.get('organic', []))} organic results")
            return search_results
            
        except requests.RequestException as e:
            logger.error(f"Search request failed: {e}")
            return None
        except Exception as e:
            logger.error(f"Error parsing search response: {e}")
            return None
    
    def _extract_base_domain(self, url: str) -> Optional[str]:
        """
        Extract base domain from URL.
        
        Args:
            url: Full URL
            
        Returns:
            Base domain or None if invalid
        """
        try:
            if not url or not url.startswith(('http://', 'https://')):
                return None
            
            parsed = urlparse(url)
            domain = parsed.netloc.lower()
            
            # Remove www. prefix if present
            if domain.startswith('www.'):
                domain = domain[4:]
            
            # Basic domain validation
            if '.' not in domain or len(domain) < 3:
                return None
            
            return domain
            
        except Exception as e:
            logger.debug(f"Error extracting domain from {url}: {e}")
            return None
    
    def _extract_websites_from_results(self, search_results: Dict[str, Any]) -> List[str]:
        """
        Extract unique base domains from search results.
        
        Args:
            search_results: ZenSERP API response
            
        Returns:
            List of unique base domains
        """
        unique_domains = []
        
        try:
            # Extract from organic results
            organic_results = search_results.get('organic', [])
            
            for result in organic_results:
                url = result.get('url', '')
                if url:
                    domain = self._extract_base_domain(url)
                    if domain and domain not in unique_domains:
                        unique_domains.append(domain)
            
            logger.info(f"Extracted {len(unique_domains)} unique domains from search results")
            return unique_domains
            
        except Exception as e:
            logger.error(f"Error extracting websites from results: {e}")
            return []
    
    def _create_error_result(self, identifier: str, status: WebsiteSearchStatus, 
                           message: str, query: str = "") -> WebsiteSearchResult:
        """Create a WebsiteSearchResult record for error cases."""
        return WebsiteSearchResult(
            identifier=identifier,
            search_query=query,
            websites_found=[],
            search_status=status.value,
            extraction_timestamp=datetime.now().isoformat(),
            processing_notes=message,
            api_quota_remaining=None,
            total_results_found=0
        )
    
    def find_company_website(self, company_data: Dict[str, Any],
                           search_keywords: List[str],
                           excluded_domains: List[str]) -> WebsiteSearchResult:
        """
        Find company website using SERP search based on company data.
        
        This is the main method that orchestrates the website discovery process:
        1. Validates the company data
        2. Combines all available identifiers (company_number, vat_number, company_name) into one query
        3. Builds comprehensive search query with keywords and exclusions
        4. Makes single API request to ZenSERP (cost-efficient)
        5. Extracts and filters domains from results
        6. Returns structured results
        
        Args:
            company_data: Dict containing company_number, vat_number, etc.
            search_keywords: Search keywords to use
            excluded_domains: Domains to exclude from results
            
        Returns:
            WebsiteSearchResult object (never returns None)
        """
        # Validate company data
        if not company_data or not isinstance(company_data, dict):
            return self._create_error_result(
                "",
                WebsiteSearchStatus.INVALID_IDENTIFIER,
                "Company data cannot be empty and must be a dictionary"
            )
        
        company_number = company_data.get('company_number', '').strip()
        vat_number = company_data.get('vat_number', '').strip() if company_data.get('vat_number') else None
        company_name = company_data.get('company_name', '').strip()
        
        if not company_number:
            return self._create_error_result(
                "",
                WebsiteSearchStatus.INVALID_IDENTIFIER,
                "Company number is required in company data"
            )
        
        logger.info(f"Starting website search for company: {company_number}")
        
        try:
            # Check API quota first
            quota_info = self.check_api_quota()
            quota_remaining = None
            
            if quota_info:
                quota_remaining = quota_info.get('remaining_requests')
                if quota_remaining is not None and quota_remaining <= 0:
                    return self._create_error_result(
                        company_number,
                        WebsiteSearchStatus.QUOTA_EXCEEDED,
                        "API quota exceeded - no remaining requests"
                    )
            
            # Build comprehensive search with all available identifiers in one query
            identifiers = [company_number]  # Company number is always required
            
            # Add VAT number if available
            if vat_number:
                identifiers.append(vat_number)
            
            # Add company name if available
            if company_name:
                identifiers.append(company_name)
            
            identifier_used = " + ".join(identifiers)
            logger.info(f"Making single comprehensive search with identifiers: {identifier_used}")
            
            # Build single comprehensive query
            if self.query_version == 2:
                search_query = self._build_search_query_v2(identifiers, search_keywords, excluded_domains)
            else:
                search_query = self._build_search_query(identifiers, search_keywords, excluded_domains)
            
            # Make single API request
            search_results = self._make_search_request(search_query)
            
            if not search_results:
                return self._create_error_result(
                    company_number,
                    WebsiteSearchStatus.API_ERROR,
                    "Failed to get search results from API",
                    search_query
                )
            
            # Get organic results
            organic_results = search_results.get('organic', [])
            
            # Extract websites from results
            websites = self._extract_websites_from_results(search_results)
            
            # Calculate total results
            total_results = len(organic_results)
            
            # Determine status and notes
            if websites:
                status = WebsiteSearchStatus.SUCCESS
                identifier_count = len(identifiers)
                if identifier_count > 1:
                    identifier_type = f"combined identifiers ({identifier_count} identifiers)"
                else:
                    identifier_type = "company number"
                notes = f"Successfully found {len(websites)} unique website(s) from {total_results} search results using {identifier_type}"
            else:
                status = WebsiteSearchStatus.NO_WEBSITES_FOUND
                notes = f"No valid websites found from {total_results} search results using {len(identifiers)} identifier(s)"
            
            logger.info(f"Website search completed: {status.value} - {len(websites)} websites found")
            
            return WebsiteSearchResult(
                identifier=identifier_used,
                search_query=search_query,
                websites_found=websites,
                search_status=status.value,
                extraction_timestamp=datetime.now().isoformat(),
                processing_notes=notes,
                api_quota_remaining=quota_remaining,
                total_results_found=total_results
            )
            
        except Exception as e:
            logger.error(f"Website search failed for company '{company_number}': {e}")
            return self._create_error_result(
                company_number,
                WebsiteSearchStatus.PARSING_ERROR,
                f"Website search failed: {str(e)}",
                search_query if 'search_query' in locals() else ""
            )


def validate_identifier(identifier: str) -> bool:
    """
    Validate identifier format for website search.
    
    Args:
        identifier: Identifier to validate (e.g., company number)
        
    Returns:
        True if valid format, False otherwise
    """
    if not identifier or not identifier.strip():
        return False
    
    # Basic validation - must not be empty and reasonable length
    clean_identifier = identifier.strip()
    return 1 <= len(clean_identifier) <= 50  # Reasonable identifier length


# Convenience function for direct usage
def find_company_website(company_data: Dict[str, Any],
                        search_keywords: List[str],
                        excluded_domains: List[str],
                        query_version: int = 1) -> List[str]:
    """
    Convenience function to find company website by company data.
    
    Args:
        company_data: Dict containing company_number, vat_number, etc.
        search_keywords: Search keywords to use
        excluded_domains: Domains to exclude from results
        query_version: Query builder version (1 or 2). Default is 1.
        
    Returns:
        List of base domains or empty list
    """
    if not company_data or not company_data.get('company_number'):
        logger.error(f"Invalid company data: {company_data}")
        return []
    
    client = WebsiteHunterClient(query_version=query_version)
    result = client.find_company_website(company_data, search_keywords, excluded_domains)
    
    return result.websites_found


if __name__ == "__main__":
    # Test the module with sample company numbers
    test_identifiers = [
        {
            "company_number": "08894455",
            "postal_code": "SL3 9AS",
            "vat_number": None,
            "company_name": "TIM O'BRIEN ACCOUNTANTS LTD",
            "address_line_1": "Tim O'Brien Accountants The Green",
            "address_line_2": "Datchet",
        }
    ]
    
    # Define test parameters
    test_search_keywords = [
        "privacy policy",
        "terms",
        "about us", 
        "company number",
        "company information"
    ]
    
    test_excluded_domains = [
        "gov.uk",
        "endole.co.uk",
        "pappers.fr",
        "opencorporates.com",
        "company-information.service.gov.uk",
        "ebay.co.uk",
        "amazon.co.uk",
        "checkcompany.co.uk",
        "find-and-update.company-information.service.gov.uk",
        "bizstats.co.uk",
        "globaldatabase.com",
        "duedil.com",
        "chostar.co.uk",
        "britishlei.co.uk",
        "vat-lookup.co.uk"
    ]
    
    print(f"Testing Website Hunter for {len(test_identifiers)} company identifiers:")
    print("=" * 80)
    
    # Initialize client
    client = WebsiteHunterClient()
    
    # Check API quota first
    print("Checking API quota...")
    quota_info = client.check_api_quota()
    if quota_info:
        print(f"✅ API Status: {quota_info}")
    else:
        print("❌ Could not check API quota")
    
    print("\n" + "=" * 80)
    
    results = []
    for i, company_data in enumerate(test_identifiers, 1):
        company_number = company_data.get('company_number', 'Unknown')
        print(f"\n[{i:2d}/{len(test_identifiers)}] Testing company: {company_number} ({company_data.get('company_name', 'No name')})")
        print("-" * 60)
        
        try:
            result = client.find_company_website(company_data, test_search_keywords, test_excluded_domains)
            
            # Store results for summary
            results.append({
                'identifier': company_number,
                'company_data': company_data,
                'websites_count': len(result.websites_found),
                'status': result.search_status,
                'success': result.is_success,
                'total_results': result.total_results_found,
                'websites': result.websites_found
            })
            
            # Print individual result
            print(f"✅ Status: {result.search_status}")
            print(f"🌐 Websites Found: {len(result.websites_found)}")
            if result.websites_found:
                for domain in result.websites_found:
                    print(f"   • {domain}")
            print(f"📊 Total SERP Results: {result.total_results_found}")
            print(f"🔑 API Quota Remaining: {result.api_quota_remaining}")
            print(f"📝 Notes: {result.processing_notes}")
            
        except Exception as e:
            print(f"❌ Error processing '{company_number}': {e}")
            results.append({
                'identifier': company_number,
                'company_data': company_data,
                'websites_count': 0,
                'status': 'ERROR',
                'success': False,
                'total_results': 0,
                'websites': []
            })
    
    # Print summary
    print("\n" + "=" * 80)
    print("SUMMARY RESULTS")
    print("=" * 80)
    
    success_count = sum(1 for r in results if r['success'])
    total_websites = sum(r['websites_count'] for r in results)
    error_count = sum(1 for r in results if r['status'] == 'ERROR')
    
    print(f"📊 Total Identifiers Tested: {len(results)}")
    print(f"✅ Successful Searches: {success_count}")
    print(f"🌐 Total Websites Found: {total_websites}")
    print(f"❌ Errors: {error_count}")
    print(f"📈 Success Rate: {success_count/len(results)*100:.1f}%")
    print(f"🌐 Avg Websites per Search: {total_websites/len(results):.1f}")
    
    print(f"\n🌐 All Websites Found:")
    for result in results:
        if result['websites']:
            print(f"  {result['identifier']}: {', '.join(result['websites'])}")
        elif result['success']:
            print(f"  {result['identifier']}: No websites found")
    
    print(f"\n❌ Failed Searches:")
    for result in results:
        if not result['success']:
            print(f"  • {result['identifier']}: {result['status']}") 