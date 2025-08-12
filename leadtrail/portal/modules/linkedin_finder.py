#!/usr/bin/env python3
"""
LinkedIn Finder Module
=======================

This module provides functionality for finding LinkedIn company and employee profiles
using SERP API queries. It searches LinkedIn specifically and scores results based on
company name and website matches.

Features:
- SERP-based LinkedIn company profile discovery
- Employee profile identification  
- Intelligent query construction with/without website
- Result scoring based on description matches
- Separation of company vs employee URLs
- Rate limiting and error handling
"""

import logging
import os
import re
import time
from datetime import datetime
from typing import Optional, Dict, Any, List, Tuple
from enum import Enum
from dataclasses import dataclass, field
from urllib.parse import urlparse, parse_qs
import requests
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Set up logging
logger = logging.getLogger(__name__)


class LinkedInSearchStatus(Enum):
    """Enumeration for LinkedIn search status codes."""
    SUCCESS = "SUCCESS"
    PARTIAL_SUCCESS = "PARTIAL_SUCCESS"
    NO_RESULTS_FOUND = "NO_RESULTS_FOUND"
    INVALID_COMPANY_NAME = "INVALID_COMPANY_NAME"
    API_ERROR = "API_ERROR"
    QUOTA_EXCEEDED = "QUOTA_EXCEEDED"
    NETWORK_ERROR = "NETWORK_ERROR"
    PARSING_ERROR = "PARSING_ERROR"


@dataclass
class LinkedInResult:
    """Data structure for individual LinkedIn search result."""
    url: str
    title: str
    description: str
    position: int
    score: int = 0
    match_details: str = ""
    
    @property
    def is_company_url(self) -> bool:
        """Check if this is a LinkedIn company URL."""
        return "/company/" in self.url.lower()
    
    @property
    def is_employee_url(self) -> bool:
        """Check if this is a LinkedIn employee/person URL."""
        return "/in/" in self.url.lower()


@dataclass
class LinkedInSearchResult:
    """Data structure for LinkedIn search results."""
    company_name: str
    website: Optional[str]
    search_query: str
    company_urls: List[LinkedInResult] = field(default_factory=list)
    employee_urls: List[LinkedInResult] = field(default_factory=list)
    total_results_found: int = 0
    search_status: str = LinkedInSearchStatus.SUCCESS.value
    processing_notes: str = ""
    extraction_timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    api_quota_remaining: Optional[int] = None
    
    @property
    def is_success(self) -> bool:
        """Check if the search was successful."""
        return self.search_status in [
            LinkedInSearchStatus.SUCCESS.value,
            LinkedInSearchStatus.PARTIAL_SUCCESS.value
        ]
    
    @property
    def has_results(self) -> bool:
        """Check if any LinkedIn profiles were found."""
        return len(self.company_urls) > 0 or len(self.employee_urls) > 0
    
    @property
    def total_linkedin_profiles(self) -> int:
        """Get total count of LinkedIn profiles found."""
        return len(self.company_urls) + len(self.employee_urls)
    
    @property
    def best_company_match(self) -> Optional[LinkedInResult]:
        """Get the highest-scoring company URL."""
        if not self.company_urls:
            return None
        return max(self.company_urls, key=lambda x: x.score)
    
    @property
    def status_enum(self) -> LinkedInSearchStatus:
        """Get the status as an enum value."""
        try:
            return LinkedInSearchStatus(self.search_status)
        except ValueError:
            return LinkedInSearchStatus.PARSING_ERROR


class LinkedInFinder:
    """
    LinkedIn profile finder using ZenSERP API for comprehensive LinkedIn searches.
    
    Searches all LinkedIn profiles (both company and employee) using broad site: queries
    and scores results based on company name and website matches. Only returns results
    with score > 0 to ensure relevance.
    
    Usage:
        finder = LinkedInFinder()
        result = finder.find_linkedin_profiles("ACME Corp", "acme.com")
    """
    
    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize LinkedIn finder with ZenSERP API configuration.
        
        Args:
            api_key: ZenSERP API key. If None, uses ZENSERP_API_KEY env variable.
            
        Raises:
            ValueError: If API key is not provided and env variable is not set
        """
        # Get API key from environment variable or parameter
        self.api_key = api_key or os.getenv('ZENSERP_API_KEY')
        
        if not self.api_key:
            raise ValueError(
                "ZenSERP API key is required. Please provide it as a parameter "
                "or set the ZENSERP_API_KEY environment variable."
            )
        
        # ZenSERP API configuration
        self.base_url = "https://app.zenserp.com/api/v2"
        self.search_url = f"{self.base_url}/search"
        
        # Rate limiting
        self.last_request_time = 0
        self.min_request_delay = 1.0  # Minimum delay between requests
        
        # Configure session
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'LinkedInFinder/1.0 (Company Profile Discovery)',
            'apikey': self.api_key
        })
        
        logger.info("Initialized LinkedIn finder with ZenSERP API")
    
    def _rate_limit(self) -> None:
        """Implement rate limiting between API requests."""
        current_time = time.time()
        time_since_last = current_time - self.last_request_time
        
        if time_since_last < self.min_request_delay:
            sleep_time = self.min_request_delay - time_since_last
            logger.debug(f"Rate limiting: sleeping {sleep_time:.2f} seconds")
            time.sleep(sleep_time)
        
        self.last_request_time = time.time()
    
    def _build_linkedin_query(self, company_name: str, website: Optional[str] = None) -> str:
        """
        Build LinkedIn-specific SERP query.
        
        Args:
            company_name: Company name to search for
            website: Optional website domain
            
        Returns:
            Formatted LinkedIn search query string
        """
        # Extract domain from website if provided
        domain = None
        if website:
            try:
                if not website.startswith(('http://', 'https://')):
                    website = f"https://{website}"
                parsed = urlparse(website)
                domain = parsed.netloc.lower()
                # Remove www. prefix
                if domain.startswith('www.'):
                    domain = domain[4:]
            except Exception as e:
                logger.warning(f"Error parsing website '{website}': {e}")
        
        # Build query based on available information
        if domain:
            query = f'site:linkedin.com/ "{company_name}" OR "{domain}"'
        else:
            query = f'site:linkedin.com/ "{company_name}"'
        
        logger.debug(f"Built LinkedIn query: {query}")
        return query
    
    def _make_zenserp_request(self, query: str) -> Optional[Dict[str, Any]]:
        """
        Make ZenSERP API request for LinkedIn search.
        
        Args:
            query: Search query string
            
        Returns:
            ZenSERP API response or None if error
        """
        try:
            self._rate_limit()
            
            params = {'q': query}
            
            logger.debug(f"Making ZenSERP request with query: {query}")
            response = self.session.get(
                self.search_url,
                params=params,
                timeout=30
            )
            
            if response.status_code == 401:
                logger.error("ZenSERP API authentication failed - check your API key")
                return None
            elif response.status_code == 429:
                logger.warning("ZenSERP API rate limit exceeded")
                return None
            elif response.status_code == 402:
                logger.error("ZenSERP API quota exceeded - payment required")
                return None
            
            response.raise_for_status()
            
            data = response.json()
            logger.debug(f"ZenSERP request successful, found {len(data.get('organic', []))} organic results")
            
            return data
            
        except requests.RequestException as e:
            logger.error(f"ZenSERP API request failed: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error in ZenSERP request: {e}")
            return None
    
    def _extract_domain_from_website(self, website: str) -> Optional[str]:
        """
        Extract clean domain from website URL.
        
        Args:
            website: Website URL
            
        Returns:
            Clean domain or None if invalid
        """
        try:
            if not website.startswith(('http://', 'https://')):
                website = f"https://{website}"
            parsed = urlparse(website)
            domain = parsed.netloc.lower()
            # Remove www. prefix
            if domain.startswith('www.'):
                domain = domain[4:]
            return domain
        except Exception:
            return None
    
    def _score_linkedin_result(self, result: Dict[str, Any], company_name: str, 
                             website: Optional[str] = None) -> Tuple[int, str]:
        """
        Score LinkedIn search result based on company name and website matches.
        
        Scoring system:
        - +1 for company name match in description
        - +2 for website domain match in description
        
        Args:
            result: ZenSERP result dictionary
            company_name: Company name to match against
            website: Optional website to match against
            
        Returns:
            Tuple of (score, match_details)
        """
        score = 0
        matches = []
        
        description = result.get('description', '').lower()
        
        # Normalize company name for matching
        company_lower = company_name.lower()
        
        # Check for company name match in description only (+1)
        if company_lower in description:
            score += 1
            matches.append("CompanyName(Desc)")
        
        # Check for website/domain matches if provided
        if website:
            domain = self._extract_domain_from_website(website)
            if domain:
                # +2 for domain match in description
                if domain in description:
                    score += 2
                    matches.append("Domain(Desc:+2)")
        
        match_details = "; ".join(matches) if matches else "No matches"
        
        logger.debug(f"Scored result: {score} points - {match_details}")
        return score, match_details
    
    def _process_zenserp_results(self, zenserp_data: Dict[str, Any], company_name: str,
                               website: Optional[str] = None) -> Tuple[List[LinkedInResult], List[LinkedInResult]]:
        """
        Process ZenSERP results and separate company vs employee URLs.
        
        Args:
            zenserp_data: ZenSERP API response data
            company_name: Company name for scoring
            website: Optional website for scoring
            
        Returns:
            Tuple of (company_urls, employee_urls)
        """
        company_urls = []
        employee_urls = []
        
        organic_results = zenserp_data.get('organic', [])
        
        for result in organic_results:
            url = result.get('url', '')
            title = result.get('title', '')
            description = result.get('description', '')
            position = result.get('position', 0)
            
            # Skip if not a LinkedIn URL
            if 'linkedin.com' not in url.lower():
                continue
            
            # Score the result
            score, match_details = self._score_linkedin_result(result, company_name, website)
            
            # Skip results with score 0 (no matches)
            if score == 0:
                logger.debug(f"Skipping URL with score 0: {url}")
                continue
            
            # Create LinkedIn result object
            linkedin_result = LinkedInResult(
                url=url,
                title=title,
                description=description,
                position=position,
                score=score,
                match_details=match_details
            )
            
            # Categorize as company or employee URL
            if linkedin_result.is_company_url:
                company_urls.append(linkedin_result)
                logger.debug(f"Found company URL: {url} (score: {score})")
            elif linkedin_result.is_employee_url:
                employee_urls.append(linkedin_result)
                logger.debug(f"Found employee URL: {url} (score: {score})")
            else:
                logger.debug(f"Skipping non-standard LinkedIn URL: {url}")
        
        # Sort by score (highest first)
        company_urls.sort(key=lambda x: x.score, reverse=True)
        employee_urls.sort(key=lambda x: x.score, reverse=True)
        
        logger.info(f"Processed results: {len(company_urls)} company URLs, {len(employee_urls)} employee URLs")
        
        return company_urls, employee_urls
    
    def _create_error_result(self, company_name: str, website: Optional[str], 
                           status: LinkedInSearchStatus, message: str, 
                           query: str = "") -> LinkedInSearchResult:
        """Create a LinkedInSearchResult for error cases."""
        return LinkedInSearchResult(
            company_name=company_name,
            website=website,
            search_query=query,
            search_status=status.value,
            processing_notes=message
        )
    
    def find_linkedin_profiles(self, company_name: str, website: Optional[str] = None) -> LinkedInSearchResult:
        """
        Find LinkedIn company and employee profiles for a given company.
        
        This is the main method that orchestrates the LinkedIn search process:
        1. Validates company name
        2. Builds LinkedIn-specific SERP query
        3. Makes SERP API request
        4. Processes and scores results
        5. Separates company vs employee URLs
        
        Args:
            company_name: Company name to search for
            website: Optional website domain for enhanced matching
            
        Returns:
            LinkedInSearchResult object (never returns None)
        """
        # Validate company name
        if not company_name or not company_name.strip():
            return self._create_error_result(
                "",
                website,
                LinkedInSearchStatus.INVALID_COMPANY_NAME,
                "Company name cannot be empty"
            )
        
        company_name = company_name.strip()
        
        logger.info(f"Starting LinkedIn search for company: {company_name}")
        if website:
            logger.info(f"Using website for enhanced matching: {website}")
        
        try:
            # Build LinkedIn search query
            query = self._build_linkedin_query(company_name, website)
            
            # Make ZenSERP API request
            zenserp_data = self._make_zenserp_request(query)
            
            if not zenserp_data:
                return self._create_error_result(
                    company_name,
                    website,
                    LinkedInSearchStatus.API_ERROR,
                    "Failed to get search results from ZenSERP API",
                    query
                )
            
            # Check for API quota information
            quota_remaining = None
            if 'query' in zenserp_data:
                query_info = zenserp_data['query']
                # ZenSERP quota information
                quota_remaining = query_info.get('credits_remaining')
            
            # Process results
            company_urls, employee_urls = self._process_zenserp_results(zenserp_data, company_name, website)
            
            total_results = len(company_urls) + len(employee_urls)
            
            # Determine status
            if total_results == 0:
                status = LinkedInSearchStatus.NO_RESULTS_FOUND
                notes = f"No LinkedIn profiles found for '{company_name}'"
            else:
                status = LinkedInSearchStatus.SUCCESS
                notes = f"Found {len(company_urls)} company profiles and {len(employee_urls)} employee profiles"
            
            # Create result object
            result = LinkedInSearchResult(
                company_name=company_name,
                website=website,
                search_query=query,
                company_urls=company_urls,
                employee_urls=employee_urls,
                total_results_found=total_results,
                search_status=status.value,
                processing_notes=notes,
                api_quota_remaining=quota_remaining
            )
            
            logger.info(f"LinkedIn search completed: {total_results} profiles found")
            return result
            
        except Exception as e:
            logger.error(f"LinkedIn search failed for '{company_name}': {e}")
            return self._create_error_result(
                company_name,
                website,
                LinkedInSearchStatus.PARSING_ERROR,
                f"Search failed: {str(e)}",
                query if 'query' in locals() else ""
            )


def validate_company_name(company_name: str) -> bool:
    """
    Validate company name format for LinkedIn search.
    
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
def find_linkedin_profiles(company_name: str, website: Optional[str] = None) -> LinkedInSearchResult:
    """
    Convenience function to find LinkedIn profiles for a company.
    
    Args:
        company_name: Company name to search for
        website: Optional website domain for enhanced matching
        
    Returns:
        LinkedInSearchResult object (never returns None - check search_status for success/failure)
    """
    if not validate_company_name(company_name):
        logger.error(f"Invalid company name: {company_name}")
        return LinkedInSearchResult(
            company_name=company_name or "",
            website=website,
            search_query="",
            search_status=LinkedInSearchStatus.INVALID_COMPANY_NAME.value,
            processing_notes=f"Invalid company name format: '{company_name}'. Must be 2-200 characters."
        )
    
    finder = LinkedInFinder()
    return finder.find_linkedin_profiles(company_name, website)


if __name__ == "__main__":
    # Test the module with sample companies
    test_companies = [
        ("TIM PHILLIPS & CO. LTD", "tpaccounts.co.uk"),
        ("TIM TAYLOR & CO LTD", "timtayloraccountants.co.uk"),
        ("TIMOTHY HIGNETT AND PARTNERS LIMITED", "timothyhignett.com"),
        ("TINGLE ASHMORE LIMITED", "tingleashmore.co.uk"),
        ("TLA BUSINESS SERVICES LIMITED", None)  # Test without website
    ]
    
    print(f"🔍 Testing LinkedIn Finder for {len(test_companies)} companies:")
    print("=" * 80)
    
    results = []
    
    for i, (company_name, website) in enumerate(test_companies, 1):
        print(f"\n[{i}/{len(test_companies)}] Searching: {company_name}")
        if website:
            print(f"🌐 Website: {website}")
        print("-" * 60)
        
        try:
            result = find_linkedin_profiles(company_name, website)
            results.append(result)
            
            # Print results for this company
            print(f"✅ Status: {result.search_status}")
            print(f"🔍 Query: {result.search_query}")
            print(f"🏢 Company Profiles ({len(result.company_urls)}):")
            for company_url in result.company_urls[:3]:  # Show first 3
                print(f"   • {company_url.url} (score: {company_url.score})")
                if company_url.match_details != "No matches":
                    print(f"     Matches: {company_url.match_details}")
            if len(result.company_urls) > 3:
                print(f"   ... and {len(result.company_urls) - 3} more")
            
            print(f"👥 Employee Profiles ({len(result.employee_urls)}):")
            for employee_url in result.employee_urls[:3]:  # Show first 3
                print(f"   • {employee_url.url} (score: {employee_url.score})")
                if employee_url.match_details != "No matches":
                    print(f"     Matches: {employee_url.match_details}")
            if len(result.employee_urls) > 3:
                print(f"   ... and {len(result.employee_urls) - 3} more")
            
            print(f"📊 Total LinkedIn Profiles: {result.total_linkedin_profiles}")
            print(f"📝 Notes: {result.processing_notes}")
            
            if result.api_quota_remaining:
                print(f"🔋 API Quota Remaining: {result.api_quota_remaining}")
            
        except Exception as e:
            print(f"❌ Error processing '{company_name}': {e}")
            results.append(LinkedInSearchResult(
                company_name=company_name,
                website=website,
                search_query="",
                search_status=LinkedInSearchStatus.PARSING_ERROR.value,
                processing_notes=f"Test failed: {str(e)}"
            ))
    
    # Summary
    print("\n" + "=" * 80)
    print("LINKEDIN FINDER SUMMARY")
    print("=" * 80)
    
    successful_searches = [r for r in results if r.is_success]
    with_results = [r for r in results if r.has_results]
    total_company_profiles = sum(len(r.company_urls) for r in results)
    total_employee_profiles = sum(len(r.employee_urls) for r in results)
    
    print(f"📊 Total Companies Searched: {len(results)}")
    print(f"✅ Successful Searches: {len(successful_searches)}")
    print(f"🎯 Companies with LinkedIn Profiles: {len(with_results)}")
    print(f"🏢 Total Company Profiles Found: {total_company_profiles}")
    print(f"👥 Total Employee Profiles Found: {total_employee_profiles}")
    print(f"📈 Success Rate: {len(successful_searches)/len(results)*100:.1f}%")
    print(f"🎯 Profile Discovery Rate: {len(with_results)/len(results)*100:.1f}%")
    
    if with_results:
        print(f"\n🏆 BEST LINKEDIN DISCOVERIES:")
        # Sort by total profiles found
        sorted_results = sorted(results, key=lambda x: x.total_linkedin_profiles, reverse=True)
        for result in sorted_results[:3]:  # Show top 3
            if result.has_results:
                print(f"   • {result.company_name}: {result.total_linkedin_profiles} profiles")
                if result.best_company_match:
                    print(f"     Best match: {result.best_company_match.url} (score: {result.best_company_match.score})")
    
    print(f"\n✅ LinkedIn finder testing completed!")
