#!/usr/bin/env python3

"""
Website Crawler Module V2
=========================

Enhanced version that tracks detailed match information with specific page URLs.

Features:
- Website crawling with configurable page limits
- Company data verification (VAT, name, company number, address, postal code)
- Ranking system based on data matches (0-6 points)
- Detailed tracking of which page contains which match
- Concurrent crawling for performance
- Robust error handling and timeouts
"""

import logging
import re
import time
from datetime import datetime
from typing import Optional, Dict, Any, List
from enum import Enum
from dataclasses import dataclass, field
from urllib.parse import urljoin, urlparse
from concurrent.futures import ThreadPoolExecutor
import requests
from bs4 import BeautifulSoup

# Load environment variables
from dotenv import load_dotenv
load_dotenv()

# Set up logging
logger = logging.getLogger(__name__)


class CrawlStatus(Enum):
    """Enumeration for crawl status codes."""
    SUCCESS = "SUCCESS"
    PARTIAL_SUCCESS = "PARTIAL_SUCCESS"
    NO_MATCHES_FOUND = "NO_MATCHES_FOUND"
    CRAWL_ERROR = "CRAWL_ERROR"
    TIMEOUT_ERROR = "TIMEOUT_ERROR"
    NETWORK_ERROR = "NETWORK_ERROR"


@dataclass
class DetailedMatch:
    """Data structure for detailed match information."""
    criterion: str
    found: bool
    matched_pages: List[str] = field(default_factory=list)
    
    def add_page(self, page_url: str) -> None:
        """Add a page URL where this criterion was found."""
        if page_url not in self.matched_pages:
            self.matched_pages.append(page_url)


@dataclass
class WebsiteScoreV2:
    """Enhanced data structure for website crawl results and scoring with detailed match tracking."""
    domain: str
    total_score: int
    
    # Detailed match information with page URLs
    detailed_matches: Dict[str, DetailedMatch]
    
    # Legacy boolean fields for backward compatibility
    vat_found: bool
    company_name_found: bool
    company_number_found: bool
    postal_code_found: bool
    address_line_1_found: bool
    address_line_2_found: bool
    
    pages_crawled: int
    crawl_status: str
    matched_pages: List[str]
    processing_notes: str
    crawl_timestamp: str
    
    @property
    def is_success(self) -> bool:
        """Check if the crawl was successful."""
        return self.crawl_status in [CrawlStatus.SUCCESS.value, CrawlStatus.PARTIAL_SUCCESS.value]
    
    @property
    def has_matches(self) -> bool:
        """Check if any matches were found."""
        return self.total_score > 0
    
    def get_detailed_score_breakdown(self) -> str:
        """Get detailed score breakdown with page URLs."""
        details = []
        
        criteria_order = [
            'company_number_found',
            'vat_found', 
            'company_name_found',
            'postal_code_found',
            'address_line_1_found',
            'address_line_2_found'
        ]
        
        for criterion in criteria_order:
            if criterion in self.detailed_matches:
                match_detail = self.detailed_matches[criterion]
                if match_detail.found and match_detail.matched_pages:
                    # Show first page URL for brevity
                    page_url = match_detail.matched_pages[0]
                    details.append(f"{criterion.replace('_found', '')}: 1 ({page_url})")
                else:
                    details.append(f"{criterion.replace('_found', '')}: 0")
            else:
                details.append(f"{criterion.replace('_found', '')}: 0")
        
        return "; ".join(details)


@dataclass
class CrawlConfig:
    """Configuration for website crawling."""
    max_pages_per_site: int = 10
    timeout_seconds: int = 30
    max_concurrent_sites: int = 5
    delay_between_requests: float = 1.0


class WebsiteCrawlerV2:
    """
    Enhanced website crawler for verifying company information and ranking websites.
    
    V2 features:
    - Tracks which specific page contains each match
    - Provides detailed breakdown with page URLs
    - Maintains backward compatibility with V1 interface
    
    Usage:
        crawler = WebsiteCrawlerV2()
        ranked_results = crawler.crawl_and_rank_websites(domains, company_data)
    """
    
    def __init__(self, config: Optional[CrawlConfig] = None):
        """
        Initialize website crawler V2.
        
        Args:
            config: Crawl configuration. Uses defaults if None.
        """
        self.config = config or CrawlConfig()
        
        # Configure session
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1'
        })
        
        logger.info(f"Initialized website crawler V2 with max {self.config.max_pages_per_site} pages per site")
    
    def _normalize_text(self, text: str) -> str:
        """
        Normalize text for matching by removing extra whitespace and converting to lowercase.
        
        Args:
            text: Text to normalize
            
        Returns:
            Normalized text
        """
        if not text:
            return ""
        
        # Remove extra whitespace and convert to lowercase
        normalized = re.sub(r'\s+', ' ', text.strip().lower())
        return normalized
    
    def _extract_links_from_homepage(self, domain: str) -> List[str]:
        """
        Visit homepage and extract all internal links.
        
        Args:
            domain: Base domain to crawl
            
        Returns:
            List of URLs found on homepage
        """
        homepage_urls = [f"https://{domain}", f"http://{domain}"]
        all_links = []
        
        for homepage_url in homepage_urls:
            try:
                logger.debug(f"Extracting links from homepage: {homepage_url}")
                response = self.session.get(
                    homepage_url,
                    timeout=self.config.timeout_seconds,
                    allow_redirects=True
                )
                
                if response.status_code == 200:
                    soup = BeautifulSoup(response.text, 'html.parser')
                    
                    # Extract all anchor tags with href attributes
                    for link in soup.find_all('a', href=True):
                        href = link.get('href')
                        if href:
                            # Convert relative URLs to absolute
                            absolute_url = urljoin(homepage_url, href)
                            all_links.append(absolute_url)
                    
                    logger.debug(f"Found {len(all_links)} links on homepage")
                    return all_links
                    
            except requests.RequestException as e:
                logger.debug(f"Error accessing homepage {homepage_url}: {e}")
                continue
        
        return all_links
    
    def _filter_relevant_links(self, domain: str, all_links: List[str]) -> List[str]:
        """
        Filter links to find relevant pages (about, contact, privacy, etc.).
        
        Args:
            domain: Base domain to filter for
            all_links: All links found on homepage
            
        Returns:
            List of filtered, relevant URLs
        """
        relevant_keywords = [
            'about', 'contact', 'privacy', 'terms', 'legal',
            'company', 'information', 'policy', 'team', 'us'
        ]
        
        filtered_links = []
        base_domain = domain.lower()
        
        for url in all_links:
            try:
                parsed_url = urlparse(url)
                url_domain = parsed_url.netloc.lower()
                
                # Remove www. prefix for comparison
                if url_domain.startswith('www.'):
                    url_domain = url_domain[4:]
                
                # Only include links from the same domain
                if url_domain == base_domain:
                    url_path = parsed_url.path.lower()
                    
                    # Check if URL contains relevant keywords
                    for keyword in relevant_keywords:
                        if keyword in url_path:
                            filtered_links.append(url)
                            break
                            
            except Exception as e:
                logger.debug(f"Error parsing URL {url}: {e}")
                continue
        
        # Remove duplicates while preserving order
        unique_links = []
        for link in filtered_links:
            if link not in unique_links:
                unique_links.append(link)
        
        logger.debug(f"Filtered to {len(unique_links)} relevant links")
        return unique_links
    
    def _find_target_pages(self, domain: str) -> List[str]:
        """
        Find target pages by visiting homepage and extracting relevant links.
        
        Args:
            domain: Base domain to crawl
            
        Returns:
            List of URLs to crawl (homepage + relevant sub-pages)
        """
        target_urls = []
        
        # Always include homepage
        homepage_urls = [f"https://{domain}", f"http://{domain}"]
        target_urls.extend(homepage_urls)
        
        # Extract links from homepage
        all_links = self._extract_links_from_homepage(domain)
        
        if all_links:
            # Filter for relevant pages
            relevant_links = self._filter_relevant_links(domain, all_links)
            target_urls.extend(relevant_links)
        
        # Limit to max pages per site
        limited_urls = target_urls[:self.config.max_pages_per_site]
        
        logger.debug(f"Target pages for {domain}: {len(limited_urls)} URLs")
        return limited_urls
    
    def _extract_text_content(self, html_content: str) -> str:
        """
        Extract clean text content from HTML.
        
        Args:
            html_content: HTML content
            
        Returns:
            Clean text content
        """
        try:
            soup = BeautifulSoup(html_content, 'html.parser')
            
            # Remove script and style elements
            for script in soup(["script", "style"]):
                script.decompose()
            
            # Get text content
            text = soup.get_text()
            
            # Clean up whitespace
            lines = (line.strip() for line in text.splitlines())
            chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
            text = ' '.join(chunk for chunk in chunks if chunk)
            
            return text
            
        except Exception as e:
            logger.debug(f"Error extracting text content: {e}")
            return ""
    
    def _check_company_data_matches(self, text_content: str, company_data: Dict[str, Any]) -> Dict[str, bool]:
        """
        Check for company data matches in text content.
        
        Args:
            text_content: Normalized text content from webpage
            company_data: Company data to search for
            
        Returns:
            Dict with match results
        """
        matches = {
            'vat_found': False,
            'company_name_found': False,
            'company_number_found': False,
            'postal_code_found': False,
            'address_line_1_found': False,
            'address_line_2_found': False
        }
        
        normalized_content = self._normalize_text(text_content)
        
        # Check VAT number
        vat_number = company_data.get('vat_number')
        if vat_number:
            # Remove spaces and check for VAT number
            clean_vat = re.sub(r'\s+', '', vat_number.upper())
            if clean_vat in normalized_content.replace(' ', '').upper():
                matches['vat_found'] = True
        
        # Check company name
        company_name = company_data.get('company_name')
        if company_name:
            # Try exact match and partial matches
            normalized_name = self._normalize_text(company_name)
            if normalized_name in normalized_content:
                matches['company_name_found'] = True
            else:
                # Try without common suffixes
                name_without_suffix = re.sub(r'\s+(ltd|limited|plc|inc|corp|corporation|llc)\.?$', '', normalized_name)
                if name_without_suffix and name_without_suffix in normalized_content:
                    matches['company_name_found'] = True
        
        # Check company number
        company_number = company_data.get('company_number')
        if company_number:
            # Search for company number (with and without spaces)
            clean_company_number = re.sub(r'\s+', '', company_number)
            if clean_company_number in normalized_content.replace(' ', ''):
                matches['company_number_found'] = True
        
        # Check postal code
        postal_code = company_data.get('postal_code')
        if postal_code:
            normalized_postal = self._normalize_text(postal_code)
            if normalized_postal in normalized_content:
                matches['postal_code_found'] = True
        
        # Check address line 1
        address_line_1 = company_data.get('address_line_1')
        if address_line_1:
            normalized_addr1 = self._normalize_text(address_line_1)
            if normalized_addr1 in normalized_content:
                matches['address_line_1_found'] = True
        
        # Check address line 2
        address_line_2 = company_data.get('address_line_2')
        if address_line_2:
            normalized_addr2 = self._normalize_text(address_line_2)
            if normalized_addr2 in normalized_content:
                matches['address_line_2_found'] = True
        
        return matches
    
    def _crawl_single_website(self, domain: str, company_data: Dict[str, Any]) -> WebsiteScoreV2:
        """
        Crawl a single website and score it based on company data matches.
        
        Args:
            domain: Domain to crawl
            company_data: Company data to search for
            
        Returns:
            WebsiteScoreV2 object with detailed match tracking
        """
        logger.info(f"Starting crawl for domain: {domain}")
        
        pages_crawled = 0
        matched_pages = []
        
        # Initialize detailed match tracking
        detailed_matches = {
            'vat_found': DetailedMatch('vat_found', False),
            'company_name_found': DetailedMatch('company_name_found', False),
            'company_number_found': DetailedMatch('company_number_found', False),
            'postal_code_found': DetailedMatch('postal_code_found', False),
            'address_line_1_found': DetailedMatch('address_line_1_found', False),
            'address_line_2_found': DetailedMatch('address_line_2_found', False)
        }
        
        target_urls = self._find_target_pages(domain)
        logger.debug(f"Found {len(target_urls)} target URLs for {domain}")
        
        try:
            # Remove duplicates (homepage might appear twice)
            unique_urls = []
            for url in target_urls:
                if url not in unique_urls:
                    unique_urls.append(url)
            
            for url in unique_urls:
                if pages_crawled >= self.config.max_pages_per_site:
                    break
                
                try:
                    logger.debug(f"Crawling URL ({pages_crawled + 1}/{self.config.max_pages_per_site}): {url}")
                    
                    response = self.session.get(
                        url, 
                        timeout=self.config.timeout_seconds,
                        allow_redirects=True
                    )
                    
                    if response.status_code == 200:
                        pages_crawled += 1
                        
                        # Extract and analyze content
                        text_content = self._extract_text_content(response.text)
                        page_matches = self._check_company_data_matches(text_content, company_data)
                        
                        # Track detailed matches with page URLs
                        page_had_matches = False
                        for criterion, found in page_matches.items():
                            if found:
                                page_had_matches = True
                                detailed_matches[criterion].found = True
                                detailed_matches[criterion].add_page(url)
                        
                        if page_had_matches:
                            matched_pages.append(url)
                        
                        logger.debug(f"Page matches: {sum(page_matches.values())}/6 - {url}")
                    
                    # Rate limiting
                    time.sleep(self.config.delay_between_requests)
                    
                except requests.RequestException as e:
                    logger.debug(f"Error crawling {url}: {e}")
                    continue
                except Exception as e:
                    logger.debug(f"Unexpected error crawling {url}: {e}")
                    continue
            
            # Calculate total score
            total_score = sum(1 for match in detailed_matches.values() if match.found)
            
            # Legacy boolean fields for backward compatibility
            legacy_matches = {
                'vat_found': detailed_matches['vat_found'].found,
                'company_name_found': detailed_matches['company_name_found'].found,
                'company_number_found': detailed_matches['company_number_found'].found,
                'postal_code_found': detailed_matches['postal_code_found'].found,
                'address_line_1_found': detailed_matches['address_line_1_found'].found,
                'address_line_2_found': detailed_matches['address_line_2_found'].found
            }
            
            # Determine status
            if total_score > 0:
                status = CrawlStatus.SUCCESS if pages_crawled > 0 else CrawlStatus.PARTIAL_SUCCESS
                notes = f"Found {total_score} matches across {len(matched_pages)} pages"
            else:
                status = CrawlStatus.NO_MATCHES_FOUND
                notes = f"No matches found after crawling {pages_crawled} pages"
            
            logger.info(f"Crawl completed for {domain}: {total_score} matches, {pages_crawled} pages")
            
            return WebsiteScoreV2(
                domain=domain,
                total_score=total_score,
                detailed_matches=detailed_matches,
                vat_found=legacy_matches['vat_found'],
                company_name_found=legacy_matches['company_name_found'],
                company_number_found=legacy_matches['company_number_found'],
                postal_code_found=legacy_matches['postal_code_found'],
                address_line_1_found=legacy_matches['address_line_1_found'],
                address_line_2_found=legacy_matches['address_line_2_found'],
                pages_crawled=pages_crawled,
                crawl_status=status.value,
                matched_pages=matched_pages,
                processing_notes=notes,
                crawl_timestamp=datetime.now().isoformat()
            )
            
        except Exception as e:
            logger.error(f"Critical error crawling {domain}: {e}")
            return WebsiteScoreV2(
                domain=domain,
                total_score=0,
                detailed_matches=detailed_matches,
                vat_found=False,
                company_name_found=False,
                company_number_found=False,
                postal_code_found=False,
                address_line_1_found=False,
                address_line_2_found=False,
                pages_crawled=pages_crawled,
                crawl_status=CrawlStatus.CRAWL_ERROR.value,
                matched_pages=[],
                processing_notes=f"Crawl failed: {str(e)}",
                crawl_timestamp=datetime.now().isoformat()
            )
    
    def crawl_and_rank_websites(self, domains: List[str], company_data: Dict[str, Any], skip_domains: List[str] = None) -> List[WebsiteScoreV2]:
        """
        Crawl multiple websites and return them ranked by score.
        
        Args:
            domains: List of domains to crawl
            company_data: Company data to search for
            skip_domains: List of domains to skip/exclude from crawling
            
        Returns:
            List of WebsiteScoreV2 objects ranked by total_score (highest first)
        """
        if not domains:
            logger.warning("No domains provided for crawling")
            return []
        
        # Filter out domains in skip list
        skip_list = skip_domains or []
        filtered_domains = [domain for domain in domains if domain not in skip_list]
        
        if len(filtered_domains) != len(domains):
            skipped_count = len(domains) - len(filtered_domains)
            logger.info(f"Skipped {skipped_count} domains from skip list: {[d for d in domains if d in skip_list]}")
        
        if not filtered_domains:
            logger.warning("No domains left after filtering skip list")
            return []
        
        logger.info(f"Starting crawl of {len(filtered_domains)} websites for company: {company_data.get('company_name', 'Unknown')}")
        
        results = []
        
        # Use ThreadPoolExecutor for concurrent crawling
        with ThreadPoolExecutor(max_workers=self.config.max_concurrent_sites) as executor:
            # Submit all crawl tasks
            future_to_domain = {
                executor.submit(self._crawl_single_website, domain, company_data): domain 
                for domain in filtered_domains
            }
            
            # Collect results as they complete
            for future in future_to_domain:
                try:
                    result = future.result(timeout=self.config.timeout_seconds * 2)
                    results.append(result)
                except Exception as e:
                    domain = future_to_domain[future]
                    logger.error(f"Failed to crawl {domain}: {e}")
                    # Add error result
                    error_detailed_matches = {
                        'vat_found': DetailedMatch('vat_found', False),
                        'company_name_found': DetailedMatch('company_name_found', False),
                        'company_number_found': DetailedMatch('company_number_found', False),
                        'postal_code_found': DetailedMatch('postal_code_found', False),
                        'address_line_1_found': DetailedMatch('address_line_1_found', False),
                        'address_line_2_found': DetailedMatch('address_line_2_found', False)
                    }
                    results.append(WebsiteScoreV2(
                        domain=domain,
                        total_score=0,
                        detailed_matches=error_detailed_matches,
                        vat_found=False,
                        company_name_found=False,
                        company_number_found=False,
                        postal_code_found=False,
                        address_line_1_found=False,
                        address_line_2_found=False,
                        pages_crawled=0,
                        crawl_status=CrawlStatus.TIMEOUT_ERROR.value,
                        matched_pages=[],
                        processing_notes=f"Crawl timeout or error: {str(e)}",
                        crawl_timestamp=datetime.now().isoformat()
                    ))
        
        # Sort by total_score (highest first), then by pages_crawled
        ranked_results = sorted(results, key=lambda x: (x.total_score, x.pages_crawled), reverse=True)
        
        logger.info(f"Crawling completed. {len([r for r in ranked_results if r.has_matches])} websites with matches")
        
        return ranked_results


# Convenience function for direct usage
def crawl_and_rank_websites(domains: List[str], 
                          company_data: Dict[str, Any],
                          config: Optional[CrawlConfig] = None,
                          skip_domains: List[str] = None) -> List[str]:
    """
    Convenience function to crawl websites and return ranked domain list.
    
    Args:
        domains: List of domains to crawl
        company_data: Company data to search for
        config: Optional crawl configuration
        skip_domains: List of domains to skip/exclude from crawling
        
    Returns:
        List of domains ranked by relevance (highest score first)
    """
    if not domains or not company_data:
        logger.error("Domains and company data are required")
        return []
    
    crawler = WebsiteCrawlerV2(config)
    scored_results = crawler.crawl_and_rank_websites(domains, company_data, skip_domains)
    
    # Return just the domain names in ranked order
    return [result.domain for result in scored_results]


if __name__ == "__main__":
    # Test the crawler V2 with sample data
    test_domains = [
        "example.com",
        "test-company.co.uk"
    ]
    
    test_company_data = {
        "company_number": "08894455",
        "postal_code": "SL3 9AS",
        "vat_number": "GB123456789",
        "company_name": "TIM O'BRIEN ACCOUNTANTS LTD",
        "address_line_1": "Tim O'Brien Accountants The Green",
        "address_line_2": "Datchet",
    }
    
    print(f"Testing Website Crawler V2 for {len(test_domains)} domains:")
    print("=" * 80)
    
    # Configure crawler
    config = CrawlConfig(
        max_pages_per_site=3,  # Reduced for testing
        timeout_seconds=10,
        max_concurrent_sites=2,
        delay_between_requests=0.5
    )
    
    crawler = WebsiteCrawlerV2(config)
    
    print(f"Company to search for: {test_company_data['company_name']}")
    print(f"VAT Number: {test_company_data.get('vat_number', 'N/A')}")
    print(f"Postal Code: {test_company_data['postal_code']}")
    print("\n" + "=" * 80)
    
    try:
        ranked_results = crawler.crawl_and_rank_websites(test_domains, test_company_data)
        
        print("CRAWL RESULTS V2:")
        print("=" * 80)
        
        for i, result in enumerate(ranked_results, 1):
            print(f"\n[{i}] {result.domain} (Score: {result.total_score}/6)")
            print(f"    Status: {result.crawl_status}")
            print(f"    Pages Crawled: {result.pages_crawled}")
            print(f"    Detailed Score Breakdown:")
            print(f"    {result.get_detailed_score_breakdown()}")
            
            if result.matched_pages:
                print(f"    Matched Pages ({len(result.matched_pages)}):")
                for page in result.matched_pages[:3]:
                    print(f"      • {page}")
            print(f"    Notes: {result.processing_notes}")
        
        print(f"\n" + "=" * 80)
        print("RANKED DOMAINS (by relevance):")
        for i, result in enumerate(ranked_results, 1):
            print(f"{i:2d}. {result.domain} (Score: {result.total_score}/6)")
        
    except Exception as e:
        print(f"❌ Error during crawling: {e}")
        import traceback
        traceback.print_exc() 