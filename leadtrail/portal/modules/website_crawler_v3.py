#!/usr/bin/env python3

"""
Website Crawler Module V3 - Precision-Focused
==============================================

Precision-focused website crawler that uses exact matching for only high-value identifiers.

Philosophy:
- OLD: Fuzzy matching with 6 data points (0-6 scoring)
- NEW: Exact matching with 2 high-value identifiers (company number + VAT) with weighted scoring
- Goal: Find the ONE correct website per company with high precision

Features:
- Two-phase search strategy: target pages first, then additional pages
- Weighted scoring system: target pages (+1.0), non-target pages (+0.75)
- Maximum score: 2.0 (both identifiers found on target pages)
- Exact matching only for company number and VAT number
- Concurrent crawling for performance
- Robust error handling and timeouts
"""

import logging
import re
import time
from datetime import datetime
from typing import Optional, Dict, Any, List, Tuple
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


class PageType(Enum):
    """Enumeration for page types with different scoring weights."""
    TARGET = "TARGET"          # +1.0 scoring weight
    NON_TARGET = "NON_TARGET"  # +0.75 scoring weight


@dataclass
class PrecisionMatch:
    """Data structure for precision match tracking with page type and URL."""
    identifier: str
    found: bool
    page_type: Optional[PageType] = None
    page_url: Optional[str] = None
    score_weight: float = 0.0
    
    def set_match(self, page_type: PageType, page_url: str) -> None:
        """Set match details and calculate score weight."""
        self.found = True
        self.page_type = page_type
        self.page_url = page_url
        self.score_weight = 1.0 if page_type == PageType.TARGET else 0.75


@dataclass
class WebsiteScoreV3:
    """Precision-focused data structure for website crawl results."""
    domain: str
    total_score: float
    company_number_match: PrecisionMatch
    vat_number_match: PrecisionMatch
    pages_crawled: int
    target_pages_crawled: int
    non_target_pages_crawled: int
    crawl_status: str
    processing_notes: str
    crawl_timestamp: str
    max_possible_score: float = 2.0
    search_phases_completed: List[str] = field(default_factory=list)
    
    @property
    def is_success(self) -> bool:
        """Check if the crawl was successful."""
        return self.crawl_status in [CrawlStatus.SUCCESS.value, CrawlStatus.PARTIAL_SUCCESS.value]
    
    @property
    def has_matches(self) -> bool:
        """Check if any matches were found."""
        return self.total_score > 0
    
    @property
    def precision_score(self) -> float:
        """Calculate precision score as percentage of maximum possible."""
        return (self.total_score / self.max_possible_score) * 100 if self.max_possible_score > 0 else 0
    
    def get_match_summary(self) -> str:
        """Get concise match summary."""
        matches = []
        
        if self.company_number_match.found:
            page_type = "T" if self.company_number_match.page_type == PageType.TARGET else "NT"
            matches.append(f"CompanyNum({page_type}:{self.company_number_match.score_weight})")
        
        if self.vat_number_match.found:
            page_type = "T" if self.vat_number_match.page_type == PageType.TARGET else "NT"
            matches.append(f"VAT({page_type}:{self.vat_number_match.score_weight})")
        
        return "; ".join(matches) if matches else "No matches"


@dataclass 
class CrawlConfigV3:
    """Configuration for precision-focused website crawling."""
    max_target_pages: int = 6  # Target pages to search first
    max_additional_pages: int = 10  # Additional pages if no target matches
    timeout_seconds: int = 30
    max_concurrent_sites: int = 5
    delay_between_requests: float = 1.0
    
    # Target page keywords for higher scoring
    target_page_keywords: List[str] = field(default_factory=lambda: [
        'about', 'contact', 'privacy', 'terms', 'legal', 'disclaimer', 
        'cookie', 'policy', 'company', 'information'
    ])


class WebsiteCrawlerV3:
    """
    Precision-focused website crawler that searches for exact matches of high-value identifiers.
    
    Key Features:
    - Two-phase search: target pages first (+1.0), then additional pages (+0.75)  
    - Exact matching for company number and VAT number only
    - Maximum score: 2.0 (both identifiers found on target pages)
    - Goal: Find ONE correct website per company with high precision
    
    Usage:
        crawler = WebsiteCrawlerV3()
        results = crawler.crawl_and_rank_websites(domains, company_data)
    """
    
    def __init__(self, config: Optional[CrawlConfigV3] = None):
        """
        Initialize precision-focused website crawler.
        
        Args:
            config: Crawl configuration. Uses defaults if None.
        """
        self.config = config or CrawlConfigV3()
        
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
        
        logger.info(f"Initialized precision crawler V3 - Target pages: {self.config.max_target_pages}, Additional: {self.config.max_additional_pages}")
    
    def _normalize_text(self, text: str) -> str:
        """
        Normalize text for exact matching.
        
        Args:
            text: Text to normalize
            
        Returns:
            Normalized text in uppercase with spaces removed
        """
        if not text:
            return ""
        
        # For exact matching, remove all whitespace and convert to uppercase
        normalized = re.sub(r'\s+', '', text.strip().upper())
        return normalized
    
    def _extract_all_links(self, domain: str) -> List[str]:
        """
        Extract all internal links from homepage.
        
        Args:
            domain: Base domain to crawl
            
        Returns:
            List of all internal URLs found
        """
        homepage_urls = [f"https://{domain}", f"http://{domain}"]
        all_links = []
        
        for homepage_url in homepage_urls:
            try:
                logger.debug(f"Extracting all links from: {homepage_url}")
                response = self.session.get(
                    homepage_url,
                    timeout=self.config.timeout_seconds,
                    allow_redirects=True
                )
                
                if response.status_code == 200:
                    soup = BeautifulSoup(response.text, 'html.parser')
                    
                    # Include homepage itself
                    all_links.append(homepage_url)
                    
                    # Extract all anchor tags
                    for link in soup.find_all('a', href=True):
                        href = link.get('href')
                        if href:
                            absolute_url = urljoin(homepage_url, href)
                            
                            # Only include same-domain links
                            parsed_url = urlparse(absolute_url)
                            url_domain = parsed_url.netloc.lower().replace('www.', '')
                            base_domain = domain.lower()
                            
                            if url_domain == base_domain:
                                all_links.append(absolute_url)
                    
                    logger.debug(f"Found {len(all_links)} total links")
                    return list(set(all_links))  # Remove duplicates
                    
            except requests.RequestException as e:
                logger.debug(f"Error accessing homepage {homepage_url}: {e}")
                continue
        
        return all_links
    
    def _categorize_pages(self, all_links: List[str]) -> Tuple[List[str], List[str]]:
        """
        Categorize pages into target and non-target based on URL patterns.
        
        Args:
            all_links: All links found on website
            
        Returns:
            Tuple of (target_pages, non_target_pages)
        """
        target_pages = []
        non_target_pages = []
        
        for url in all_links:
            try:
                parsed_url = urlparse(url)
                url_path = parsed_url.path.lower()
                
                # Check if URL contains target keywords
                is_target = any(keyword in url_path for keyword in self.config.target_page_keywords)
                
                if is_target:
                    target_pages.append(url)
                else:
                    non_target_pages.append(url)
                    
            except Exception as e:
                logger.debug(f"Error categorizing URL {url}: {e}")
                non_target_pages.append(url)  # Default to non-target
        
        logger.debug(f"Categorized pages: {len(target_pages)} target, {len(non_target_pages)} non-target")
        return target_pages, non_target_pages
    
    def _extract_text_content(self, html_content: str) -> str:
        """
        Extract clean text content from HTML for exact matching.
        
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
            
            # For exact matching, keep text as-is for normalization later
            return text
            
        except Exception as e:
            logger.debug(f"Error extracting text content: {e}")
            return ""
    
    def _check_exact_matches(self, text_content: str, company_data: Dict[str, Any]) -> Dict[str, bool]:
        """
        Check for exact matches of high-value identifiers only.
        
        Args:
            text_content: Text content from webpage
            company_data: Company data containing identifiers
            
        Returns:
            Dict with exact match results for company number and VAT
        """
        matches = {
            'company_number_found': False,
            'vat_number_found': False
        }
        
        # Normalize content for exact matching
        normalized_content = self._normalize_text(text_content)
        
        # Check company number (exact match only)
        company_number = company_data.get('company_number')
        if company_number:
            normalized_company_number = self._normalize_text(company_number)
            if normalized_company_number and normalized_company_number in normalized_content:
                matches['company_number_found'] = True
                logger.debug(f"Found exact company number match: {company_number}")
        
        # Check VAT number (exact match with GB prefix variants)
        vat_number = company_data.get('vat_number')
        if vat_number:
            normalized_vat_full = self._normalize_text(vat_number)
            
            # Extract numeric part (remove GB prefix if present)
            vat_numeric = re.sub(r'^GB', '', normalized_vat_full)
            
            # Check both full VAT (with GB) and numeric part (without GB)
            if normalized_vat_full and normalized_vat_full in normalized_content:
                matches['vat_number_found'] = True
                logger.debug(f"Found exact VAT number match (full): {vat_number}")
            elif vat_numeric and vat_numeric != normalized_vat_full and vat_numeric in normalized_content:
                matches['vat_number_found'] = True
                logger.debug(f"Found exact VAT number match (numeric): {vat_numeric} from {vat_number}")
        
        return matches
    
    def _crawl_pages_phase(self, pages: List[str], page_type: PageType, 
                          company_data: Dict[str, Any], max_pages: int) -> Tuple[PrecisionMatch, PrecisionMatch, int]:
        """
        Crawl pages in a specific phase and return matches.
        
        Args:
            pages: List of page URLs to crawl
            page_type: Type of pages being crawled (TARGET or NON_TARGET)
            company_data: Company data to search for
            max_pages: Maximum pages to crawl in this phase
            
        Returns:
            Tuple of (company_number_match, vat_number_match, pages_crawled)
        """
        company_number_match = PrecisionMatch('company_number', False)
        vat_number_match = PrecisionMatch('vat_number', False)
        pages_crawled = 0
        
        # Limit pages for this phase
        phase_pages = pages[:max_pages]
        
        for url in phase_pages:
            if pages_crawled >= max_pages:
                break
            
            # Skip if we already found both matches
            if company_number_match.found and vat_number_match.found:
                logger.debug(f"Both matches found, stopping phase early")
                break
            
            try:
                logger.debug(f"Crawling {page_type.value} page ({pages_crawled + 1}/{max_pages}): {url}")
                
                response = self.session.get(
                    url,
                    timeout=self.config.timeout_seconds,
                    allow_redirects=True
                )
                
                if response.status_code == 200:
                    pages_crawled += 1
                    
                    # Extract and check content
                    text_content = self._extract_text_content(response.text)
                    page_matches = self._check_exact_matches(text_content, company_data)
                    
                    # Update matches if found
                    if page_matches['company_number_found'] and not company_number_match.found:
                        company_number_match.set_match(page_type, url)
                        logger.info(f"Company number found on {page_type.value} page: {url}")
                    
                    if page_matches['vat_number_found'] and not vat_number_match.found:
                        vat_number_match.set_match(page_type, url)
                        logger.info(f"VAT number found on {page_type.value} page: {url}")
                
                # Rate limiting
                time.sleep(self.config.delay_between_requests)
                
            except requests.RequestException as e:
                logger.debug(f"Error crawling {url}: {e}")
                continue
            except Exception as e:
                logger.debug(f"Unexpected error crawling {url}: {e}")
                continue
        
        return company_number_match, vat_number_match, pages_crawled
    
    def _crawl_single_website(self, domain: str, company_data: Dict[str, Any]) -> WebsiteScoreV3:
        """
        Crawl a single website using precision-focused two-phase strategy.
        
        Args:
            domain: Domain to crawl
            company_data: Company data containing identifiers to search for
            
        Returns:
            WebsiteScoreV3 object with precision scoring
        """
        logger.info(f"Starting precision crawl for domain: {domain}")
        
        # Initialize match tracking
        company_number_match = PrecisionMatch('company_number', False)
        vat_number_match = PrecisionMatch('vat_number', False)
        total_pages_crawled = 0
        target_pages_crawled = 0
        non_target_pages_crawled = 0
        phases_completed = []
        
        try:
            # Extract all links from website
            all_links = self._extract_all_links(domain)
            if not all_links:
                logger.warning(f"No links found for domain: {domain}")
                return self._create_error_result(domain, "No links found on website")
            
            # Categorize pages
            target_pages, non_target_pages = self._categorize_pages(all_links)
            
            # PHASE 1: Search target pages first (+1.0 scoring)
            logger.info(f"Phase 1: Searching {len(target_pages)} target pages for {domain}")
            if target_pages:
                phase1_company, phase1_vat, target_crawled = self._crawl_pages_phase(
                    target_pages, PageType.TARGET, company_data, self.config.max_target_pages
                )
                
                # Update matches from Phase 1
                if phase1_company.found:
                    company_number_match = phase1_company
                if phase1_vat.found:
                    vat_number_match = phase1_vat
                
                target_pages_crawled = target_crawled
                total_pages_crawled += target_crawled
                phases_completed.append("Phase 1: Target pages")
            
            # PHASE 2: Search additional pages only if no matches found in Phase 1 (+0.75 scoring)
            if not (company_number_match.found and vat_number_match.found) and non_target_pages:
                logger.info(f"Phase 2: Searching {len(non_target_pages)} additional pages for {domain}")
                
                phase2_company, phase2_vat, non_target_crawled = self._crawl_pages_phase(
                    non_target_pages, PageType.NON_TARGET, company_data, self.config.max_additional_pages
                )
                
                # Update matches from Phase 2 (only if not found in Phase 1)
                if phase2_company.found and not company_number_match.found:
                    company_number_match = phase2_company
                if phase2_vat.found and not vat_number_match.found:
                    vat_number_match = phase2_vat
                
                non_target_pages_crawled = non_target_crawled
                total_pages_crawled += non_target_crawled
                phases_completed.append("Phase 2: Additional pages")
            
            # Calculate total score
            total_score = 0.0
            if company_number_match.found:
                total_score += company_number_match.score_weight
            if vat_number_match.found:
                total_score += vat_number_match.score_weight
            
            # Determine status and notes
            if total_score > 0:
                status = CrawlStatus.SUCCESS
                notes = f"Found {total_score:.2f}/2.0 precision score. "
                notes += f"Company number: {'✓' if company_number_match.found else '✗'}, "
                notes += f"VAT: {'✓' if vat_number_match.found else '✗'}"
            else:
                status = CrawlStatus.NO_MATCHES_FOUND
                notes = f"No exact matches found after crawling {total_pages_crawled} pages"
            
            logger.info(f"Precision crawl completed for {domain}: {total_score:.2f}/2.0 score, {total_pages_crawled} pages")
            
            return WebsiteScoreV3(
                domain=domain,
                total_score=total_score,
                company_number_match=company_number_match,
                vat_number_match=vat_number_match,
                pages_crawled=total_pages_crawled,
                target_pages_crawled=target_pages_crawled,
                non_target_pages_crawled=non_target_pages_crawled,
                crawl_status=status.value,
                processing_notes=notes,
                crawl_timestamp=datetime.now().isoformat(),
                search_phases_completed=phases_completed
            )
            
        except Exception as e:
            logger.error(f"Critical error in precision crawl for {domain}: {e}")
            return self._create_error_result(domain, f"Crawl failed: {str(e)}")
    
    def _create_error_result(self, domain: str, error_message: str) -> WebsiteScoreV3:
        """
        Create error result for failed crawls.
        
        Args:
            domain: Domain that failed
            error_message: Error description
            
        Returns:
            WebsiteScoreV3 object with error status
        """
        return WebsiteScoreV3(
            domain=domain,
            total_score=0.0,
            company_number_match=PrecisionMatch('company_number', False),
            vat_number_match=PrecisionMatch('vat_number', False),
            pages_crawled=0,
            target_pages_crawled=0,
            non_target_pages_crawled=0,
            crawl_status=CrawlStatus.CRAWL_ERROR.value,
            processing_notes=error_message,
            crawl_timestamp=datetime.now().isoformat(),
            search_phases_completed=[]
        )
    
    def crawl_and_rank_websites(self, domains: List[str], company_data: Dict[str, Any], 
                               skip_domains: List[str] = None) -> List[WebsiteScoreV3]:
        """
        Crawl multiple websites using precision-focused approach and return ranked results.
        
        Args:
            domains: List of domains to crawl
            company_data: Company data containing identifiers to search for
            skip_domains: List of domains to skip/exclude from crawling
            
        Returns:
            List of WebsiteScoreV3 objects ranked by precision score (highest first)
        """
        if not domains:
            logger.warning("No domains provided for precision crawling")
            return []
        
        # Validate required identifiers
        company_number = company_data.get('company_number')
        vat_number = company_data.get('vat_number')
        
        if not company_number and not vat_number:
            logger.error("At least one of company_number or vat_number is required for precision crawling")
            return []
        
        # Filter skip domains
        skip_list = skip_domains or []
        filtered_domains = [domain for domain in domains if domain not in skip_list]
        
        if len(filtered_domains) != len(domains):
            skipped_count = len(domains) - len(filtered_domains)
            logger.info(f"Skipped {skipped_count} domains from skip list")
        
        if not filtered_domains:
            logger.warning("No domains left after filtering skip list")
            return []
        
        logger.info(f"Starting precision crawl of {len(filtered_domains)} websites")
        logger.info(f"Searching for - Company Number: {company_number or 'N/A'}, VAT: {vat_number or 'N/A'}")
        
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
                    result = future.result(timeout=self.config.timeout_seconds * 3)
                    results.append(result)
                except Exception as e:
                    domain = future_to_domain[future]
                    logger.error(f"Failed to crawl {domain}: {e}")
                    results.append(self._create_error_result(domain, f"Timeout or error: {str(e)}"))
        
        # Sort by precision score (highest first), then by total pages crawled
        ranked_results = sorted(results, key=lambda x: (x.total_score, x.pages_crawled), reverse=True)
        
        # Log summary
        matches_found = len([r for r in ranked_results if r.has_matches])
        perfect_matches = len([r for r in ranked_results if r.total_score == 2.0])
        
        logger.info(f"Precision crawling completed. {matches_found}/{len(ranked_results)} websites with matches, {perfect_matches} perfect matches")
        
        return ranked_results


def crawl_and_rank_websites_v3(domains: List[str], 
                              company_data: Dict[str, Any],
                              config: Optional[CrawlConfigV3] = None,
                              skip_domains: List[str] = None) -> List[str]:
    """
    Convenience function for precision crawling that returns ranked domain list.
    
    Args:
        domains: List of domains to crawl
        company_data: Company data containing identifiers
        config: Optional crawl configuration
        skip_domains: List of domains to skip
        
    Returns:
        List of domains ranked by precision score (highest first)
    """
    if not domains or not company_data:
        logger.error("Domains and company data are required")
        return []
    
    crawler = WebsiteCrawlerV3(config)
    scored_results = crawler.crawl_and_rank_websites(domains, company_data, skip_domains)
    
    return [result.domain for result in scored_results]


if __name__ == "__main__":
    test_domains = [
        "example.com",
        "test-company.co.uk",
        "sample-business.com"
    ]
    
    test_company_data = {
        "company_number": "12345678",
        "vat_number": "GB123456789",  # Will match both "GB123456789" and "123456789" on websites
        "company_name": "TEST COMPANY LTD"  # Not used in V3, but kept for compatibility
    }
    
    print(f"Testing Precision Website Crawler V3 for {len(test_domains)} domains:")
    print("=" * 80)
    
    config = CrawlConfigV3(
        max_target_pages=4,
        max_additional_pages=6, 
        timeout_seconds=15,
        max_concurrent_sites=2,
        delay_between_requests=0.5
    )
    
    crawler = WebsiteCrawlerV3(config)
    
    print(f"Precision Search Mode: Exact matching only")
    print(f"Company Number: {test_company_data.get('company_number', 'N/A')}")
    print(f"VAT Number: {test_company_data.get('vat_number', 'N/A')} (matches both with/without GB prefix)")
    print(f"Target page score: +1.0, Additional page score: +0.75")
    print(f"Maximum possible score: 2.0")
    print("\n" + "=" * 80)
    
    try:
        ranked_results = crawler.crawl_and_rank_websites(test_domains, test_company_data)
        
        print("PRECISION CRAWL RESULTS:")
        print("=" * 80)
        
        for i, result in enumerate(ranked_results, 1):
            print(f"\n[{i}] {result.domain} (Score: {result.total_score:.2f}/2.0, Precision: {result.precision_score:.1f}%)")
            print(f"    Status: {result.crawl_status}")
            print(f"    Pages: {result.pages_crawled} total ({result.target_pages_crawled} target, {result.non_target_pages_crawled} additional)")
            print(f"    Phases: {', '.join(result.search_phases_completed) if result.search_phases_completed else 'None'}")
            print(f"    Matches: {result.get_match_summary()}")
            
            if result.company_number_match.found:
                print(f"      • Company Number: {result.company_number_match.page_url}")
            if result.vat_number_match.found:
                print(f"      • VAT Number: {result.vat_number_match.page_url}")
            
            print(f"    Notes: {result.processing_notes}")
        
        print(f"\n" + "=" * 80)
        print("FINAL PRECISION RANKING:")
        for i, result in enumerate(ranked_results, 1):
            precision_label = ""
            if result.total_score == 2.0:
                precision_label = " [PERFECT MATCH]"
            elif result.total_score >= 1.5:
                precision_label = " [HIGH PRECISION]"
            elif result.total_score >= 0.75:
                precision_label = " [MEDIUM PRECISION]"
            
            print(f"{i:2d}. {result.domain} (Score: {result.total_score:.2f}/2.0){precision_label}")
        
    except Exception as e:
        print(f"❌ Error during precision crawling: {e}")
        import traceback
        traceback.print_exc()