#!/usr/bin/env python3

"""
Contact Extractor Module
========================

This module provides intelligent contact information extraction from business websites,
with specialized focus on UK companies. It crawls relevant pages (about us, contact us, 
privacy policy, etc.) and extracts:
- UK phone numbers (landlines, mobiles, freephone, service numbers)
- Email addresses  
- Social media links (Facebook, Instagram, LinkedIn)

Features:
- Intelligent page discovery (contact, about, privacy pages)
- UK-specific phone number extraction with comprehensive validation
- Advanced pattern matching with false positive filtering
- Social media profile detection
- Configurable crawling parameters
- Comprehensive result structure
- Robust error handling and timeouts

Phone Number Support:
- UK landlines (01xxx, 020, 03xx)
- UK mobiles (07xxx)
- UK freephone (0800, 0808)
- UK service numbers (0845, 0870, 0871, etc.)
- International format for UK numbers (+44)
- Various formatting styles (spaces, brackets, dashes)
"""

import logging
import re
import time
from datetime import datetime
from typing import Optional, Dict, Any, List, Set
from enum import Enum
from dataclasses import dataclass, field
from urllib.parse import urljoin, urlparse
import requests
from bs4 import BeautifulSoup

# Load environment variables
from dotenv import load_dotenv
load_dotenv()

# Set up logging
logger = logging.getLogger(__name__)


class ContactExtractionStatus(Enum):
    """Enumeration for contact extraction status codes."""
    SUCCESS = "SUCCESS"
    PARTIAL_SUCCESS = "PARTIAL_SUCCESS"
    NO_CONTACT_INFO_FOUND = "NO_CONTACT_INFO_FOUND"
    CRAWL_ERROR = "CRAWL_ERROR"
    TIMEOUT_ERROR = "TIMEOUT_ERROR"
    NETWORK_ERROR = "NETWORK_ERROR"


@dataclass
class ContactInformation:
    """Data structure for extracted contact information from UK businesses."""
    domain: str
    phone_numbers: List[str] = field(default_factory=list)
    email_addresses: List[str] = field(default_factory=list)
    facebook_links: List[str] = field(default_factory=list)
    instagram_links: List[str] = field(default_factory=list)
    linkedin_links: List[str] = field(default_factory=list)
    pages_crawled: int = 0
    pages_with_contact_info: List[str] = field(default_factory=list)
    extraction_status: str = ContactExtractionStatus.SUCCESS.value
    processing_notes: str = ""
    extraction_timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    
    @property
    def is_success(self) -> bool:
        """Check if the extraction was successful."""
        return self.extraction_status in [
            ContactExtractionStatus.SUCCESS.value, 
            ContactExtractionStatus.PARTIAL_SUCCESS.value
        ]
    
    @property
    def has_contact_info(self) -> bool:
        """Check if any contact information was found."""
        return (len(self.phone_numbers) > 0 or 
                len(self.email_addresses) > 0 or 
                len(self.facebook_links) > 0 or 
                len(self.instagram_links) > 0 or 
                len(self.linkedin_links) > 0)
    
    @property
    def total_contact_items(self) -> int:
        """Get total count of contact information items found."""
        return (len(self.phone_numbers) + 
                len(self.email_addresses) + 
                len(self.facebook_links) + 
                len(self.instagram_links) + 
                len(self.linkedin_links))


@dataclass
class ContactCrawlConfig:
    """Configuration for contact information crawling."""
    max_pages_per_site: int = 15
    timeout_seconds: int = 30
    delay_between_requests: float = 1.0
    max_phone_numbers: int = 10
    max_email_addresses: int = 10
    max_social_links_per_platform: int = 5


class ContactExtractor:
    """
    UK-focused website contact information extractor.
    
    Crawls relevant pages of a website to extract contact information including
    UK phone numbers, email addresses, and social media links. Optimized for
    British businesses with comprehensive UK phone number validation.
    
    Usage:
        extractor = ContactExtractor()
        contact_info = extractor.extract_contact_info("ukcompany.co.uk")
    """
    
    def __init__(self, config: Optional[ContactCrawlConfig] = None):
        """
        Initialize contact extractor.
        
        Args:
            config: Crawl configuration. Uses defaults if None.
        """
        self.config = config or ContactCrawlConfig()
        
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
        
        # Regex patterns for contact information
        self._setup_regex_patterns()
        
        logger.info(f"Initialized contact extractor with max {self.config.max_pages_per_site} pages per site")
    
    def _setup_regex_patterns(self) -> None:
        """Setup regex patterns for extracting contact information."""
        
        # UK-focused phone number patterns - optimized for British businesses
        self.phone_patterns = [
            # UK landline numbers with area codes: 0121 496 0000, 020 7946 0000, 01234 567890
            re.compile(r'\b0(?:1[1-9]\d{1,2}|2[0-9]|3[0-9])\s?\d{3,4}\s?\d{3,4}\b', re.IGNORECASE),
            
            # UK mobile numbers: 07123 456789, 07123456789, +44 7123 456789
            re.compile(r'\b(?:\+44\s?7|07)[0-9]{3}\s?\d{3}\s?\d{3}\b', re.IGNORECASE),
            
            # UK freephone numbers: 0800 123 4567, 0808 123 4567
            re.compile(r'\b0(?:800|808)\s?\d{3}\s?\d{4}\b', re.IGNORECASE),
            
            # UK local rate and national rate: 0845 123 4567, 0870 123 4567, 0871 123 4567
            re.compile(r'\b0(?:845|870|871|872|873)\s?\d{3}\s?\d{4}\b', re.IGNORECASE),
            
            # UK premium rate: 09xx xxx xxxx
            re.compile(r'\b09[0-9]{2}\s?\d{3}\s?\d{4}\b', re.IGNORECASE),
            
            # International format for UK numbers: +44 20 7946 0000, +44 121 496 0000
            re.compile(r'\+44\s?(?:1[1-9]\d{1,2}|2[0-9]|3[0-9]|7[0-9]{3})\s?\d{3,4}\s?\d{3,4}\b', re.IGNORECASE),
            
            # UK numbers with brackets: (020) 7946 0000, (0121) 496 0000
            re.compile(r'\(0(?:1[1-9]\d{1,2}|2[0-9]|3[0-9])\)\s?\d{3,4}\s?\d{3,4}\b', re.IGNORECASE),
            
            # UK numbers with dashes: 020-7946-0000, 0121-496-0000
            re.compile(r'\b0(?:1[1-9]\d{1,2}|2[0-9]|3[0-9])-\d{3,4}-\d{3,4}\b', re.IGNORECASE)
        ]
        
        # Email pattern (unchanged)
        self.email_pattern = re.compile(
            r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
        )
        
        # Social media patterns (unchanged)
        self.social_patterns = {
            'facebook': re.compile(r'(?:https?://)?(?:www\.)?facebook\.com/[A-Za-z0-9._-]+', re.IGNORECASE),
            'instagram': re.compile(r'(?:https?://)?(?:www\.)?instagram\.com/[A-Za-z0-9._-]+', re.IGNORECASE),
            'linkedin': re.compile(r'(?:https?://)?(?:www\.)?linkedin\.com/(?:in|company)/[A-Za-z0-9._-]+', re.IGNORECASE)
        }
    
    def _normalize_text(self, text: str) -> str:
        """
        Normalize text for processing.
        
        Args:
            text: Text to normalize
            
        Returns:
            Normalized text
        """
        if not text:
            return ""
        
        # Remove extra whitespace and convert to lowercase for some operations
        normalized = re.sub(r'\s+', ' ', text.strip())
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
    
    def _filter_contact_relevant_links(self, domain: str, all_links: List[str]) -> List[str]:
        """
        Filter links to find contact-relevant pages.
        
        Args:
            domain: Base domain to filter for
            all_links: All links found on homepage
            
        Returns:
            List of filtered, contact-relevant URLs
        """
        contact_keywords = [
            'contact', 'about', 'team', 'staff', 'office', 'location',
            'phone', 'email', 'reach', 'touch', 'connect', 'support',
            'help', 'customer', 'service', 'info', 'information'
        ]
        
        # Also include privacy/legal pages as they often contain contact info
        legal_keywords = [
            'privacy', 'terms', 'legal', 'policy', 'cookies',
            'disclaimer', 'imprint', 'impressum'
        ]
        
        all_keywords = contact_keywords + legal_keywords
        
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
                    url_full = url.lower()
                    
                    # Check if URL contains relevant keywords
                    for keyword in all_keywords:
                        if keyword in url_path or keyword in url_full:
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
        
        logger.debug(f"Filtered to {len(unique_links)} contact-relevant links")
        return unique_links
    
    def _find_contact_pages(self, domain: str) -> List[str]:
        """
        Find contact-relevant pages by visiting homepage and extracting relevant links.
        
        Args:
            domain: Base domain to crawl
            
        Returns:
            List of URLs to crawl for contact information
        """
        target_urls = []
        
        # Always include homepage
        homepage_urls = [f"https://{domain}", f"http://{domain}"]
        target_urls.extend(homepage_urls)
        
        # Extract links from homepage
        all_links = self._extract_links_from_homepage(domain)
        
        if all_links:
            # Filter for contact-relevant pages
            contact_links = self._filter_contact_relevant_links(domain, all_links)
            target_urls.extend(contact_links)
        
        # Limit to max pages per site
        limited_urls = target_urls[:self.config.max_pages_per_site]
        
        logger.debug(f"Target contact pages for {domain}: {len(limited_urls)} URLs")
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
    
    def _extract_phone_numbers(self, text: str, html: str) -> List[str]:
        """
        Extract UK phone numbers from text and HTML content.
        
        Args:
            text: Plain text content
            html: HTML content
            
        Returns:
            List of unique UK phone numbers found
        """
        phone_numbers = set()
        
        # Search in both text and HTML
        content_sources = [text, html]
        
        for content in content_sources:
            if not content:
                continue
                
            for pattern in self.phone_patterns:
                matches = pattern.findall(content)
                for match in matches:
                    # Clean up the phone number
                    clean_phone = re.sub(r'[^\d+\s()-]', '', match.strip())
                    
                    # UK-specific validation
                    digits_only = re.sub(r'[^\d]', '', clean_phone)
                    
                    # Skip if too short or too long for UK numbers
                    if len(digits_only) < 10 or len(digits_only) > 13:
                        continue
                    
                    # Skip obvious UK false positives and test numbers
                    uk_test_numbers = [
                        '01234567890',  # Common test format
                        '02079460000',  # London example number
                        '01214960000',  # Birmingham example number
                        '07700900000',  # Mobile example range
                        '08001111111',  # Freephone test
                        '09999999999'   # Invalid premium rate
                    ]
                    
                    if any(test_num in digits_only for test_num in uk_test_numbers):
                        continue
                    
                    # Validate UK number format
                    if not self._is_valid_uk_number(digits_only):
                        continue
                    
                    # Skip numbers that are too repetitive (except valid cases like 0800 1111)
                    unique_digits = len(set(digits_only))
                    if unique_digits < 3 and len(digits_only) > 8:
                        continue
                    
                    if clean_phone:
                        phone_numbers.add(clean_phone)
        
        # Limit results
        return list(phone_numbers)[:self.config.max_phone_numbers]
    
    def _is_valid_uk_number(self, digits_only: str) -> bool:
        """
        Validate if a number matches UK phone number format.
        
        Args:
            digits_only: Phone number with only digits
            
        Returns:
            True if valid UK number format
        """
        # Remove +44 country code if present and replace with 0
        if digits_only.startswith('44'):
            digits_only = '0' + digits_only[2:]
        
        # Must be 10 or 11 digits for UK numbers
        if len(digits_only) not in [10, 11]:
            return False
        
        # Must start with 0
        if not digits_only.startswith('0'):
            return False
        
        # Validate specific UK number ranges
        if len(digits_only) == 11:
            # Mobile numbers: 07xxx xxxxxx
            if digits_only.startswith('07'):
                return True
            
            # Some landline areas with 11 digits (geographic numbers)
            if digits_only.startswith('01'):
                return True
        
        if len(digits_only) == 10:
            # London: 020 xxxx xxxx (actually 11 digits, but some may appear as 10)
            if digits_only.startswith('02'):
                return True
            
            # Major cities: 0121, 0131, 0141, 0151, 0161, 0191 (actually 11 digits)
            major_cities = ['012', '013', '014', '015', '016', '019']
            if any(digits_only.startswith(city) for city in major_cities):
                return True
        
        # Check for 11-digit numbers with specific prefixes
        if len(digits_only) == 11:
            # London: 020x xxx xxxx
            if digits_only.startswith('020'):
                return True
            
            # Major cities: 0121 xxx xxxx, 0131 xxx xxxx, etc.
            major_cities_11 = ['0121', '0131', '0141', '0151', '0161', '0191']
            if any(digits_only.startswith(city) for city in major_cities_11):
                return True
            
            # Other landlines: 01xxx xxxxxx
            if digits_only.startswith('01'):
                return True
            
            # Freephone: 0800 xxx xxxx, 0808 xxx xxxx
            if digits_only.startswith('0800') or digits_only.startswith('0808'):
                return True
            
            # Local/National rate: 0845 xxx xxxx, 0870 xxx xxxx, etc.
            service_numbers = ['0845', '0870', '0871', '0872', '0873']
            if any(digits_only.startswith(service) for service in service_numbers):
                return True
            
            # Premium rate: 09xx xxx xxxx
            if digits_only.startswith('09'):
                return True
        
        # Check for 10-digit numbers (less common but valid)
        if len(digits_only) == 10:
            # Some freephone or service numbers might be 10 digits
            if digits_only.startswith('0800') or digits_only.startswith('0808'):
                return True
            
            # Some service numbers might be 10 digits  
            service_numbers_10 = ['0845', '0870', '0871', '0872', '0873']
            if any(digits_only.startswith(service) for service in service_numbers_10):
                return True
        
        return False
    
    def _extract_email_addresses(self, text: str, html: str) -> List[str]:
        """
        Extract email addresses from text and HTML content.
        
        Args:
            text: Plain text content
            html: HTML content
            
        Returns:
            List of unique email addresses found
        """
        email_addresses = set()
        
        # Search in both text and HTML
        content_sources = [text, html]
        
        for content in content_sources:
            if not content:
                continue
                
            matches = self.email_pattern.findall(content)
            for match in matches:
                # Filter out common false positives
                email = match.lower().strip()
                if not any(exclude in email for exclude in [
                    'example.com', 'test.com', 'dummy.com', 'placeholder',
                    'yourname@', 'name@domain', '@example', 'noreply@'
                ]):
                    email_addresses.add(email)
        
        # Limit results
        return list(email_addresses)[:self.config.max_email_addresses]
    
    def _extract_social_media_links(self, text: str, html: str) -> Dict[str, List[str]]:
        """
        Extract social media links from text and HTML content.
        
        Args:
            text: Plain text content
            html: HTML content
            
        Returns:
            Dict with lists of social media links by platform
        """
        social_links = {
            'facebook': set(),
            'instagram': set(),
            'linkedin': set()
        }
        
        # Search in both text and HTML
        content_sources = [text, html]
        
        for content in content_sources:
            if not content:
                continue
                
            for platform, pattern in self.social_patterns.items():
                matches = pattern.findall(content)
                for match in matches:
                    # Clean up the URL
                    url = match.strip()
                    if not url.startswith('http'):
                        url = 'https://' + url
                    
                    # Filter out generic/invalid profiles
                    if not any(exclude in url.lower() for exclude in [
                        '/sharer/', '/share?', '/login', '/signup', '/home',
                        'facebook.com/pages', 'facebook.com/pg'
                    ]):
                        social_links[platform].add(url)
        
        # Convert to lists and limit results
        result = {}
        for platform, links in social_links.items():
            result[platform] = list(links)[:self.config.max_social_links_per_platform]
        
        return result
    
    def extract_contact_info(self, domain: str) -> ContactInformation:
        """
        Extract contact information from a website.
        
        Args:
            domain: Domain to extract contact information from
            
        Returns:
            ContactInformation object with extracted data
        """
        logger.info(f"Starting contact extraction for domain: {domain}")
        
        # Initialize result object
        contact_info = ContactInformation(domain=domain)
        
        # Find contact-relevant pages
        target_urls = self._find_contact_pages(domain)
        logger.debug(f"Found {len(target_urls)} target URLs for {domain}")
        
        try:
            # Remove duplicates
            unique_urls = []
            for url in target_urls:
                if url not in unique_urls:
                    unique_urls.append(url)
            
            pages_crawled = 0
            pages_with_info = []
            
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
                        
                        # Extract content
                        html_content = response.text
                        text_content = self._extract_text_content(html_content)
                        
                        # Track if this page had any contact info
                        page_had_info = False
                        
                        # Extract phone numbers
                        phones = self._extract_phone_numbers(text_content, html_content)
                        if phones:
                            contact_info.phone_numbers.extend(phones)
                            page_had_info = True
                        
                        # Extract email addresses
                        emails = self._extract_email_addresses(text_content, html_content)
                        if emails:
                            contact_info.email_addresses.extend(emails)
                            page_had_info = True
                        
                        # Extract social media links
                        social_links = self._extract_social_media_links(text_content, html_content)
                        for platform, links in social_links.items():
                            if links:
                                if platform == 'facebook':
                                    contact_info.facebook_links.extend(links)
                                elif platform == 'instagram':
                                    contact_info.instagram_links.extend(links)
                                elif platform == 'linkedin':
                                    contact_info.linkedin_links.extend(links)
                                page_had_info = True
                        
                        if page_had_info:
                            pages_with_info.append(url)
                        
                        logger.debug(f"Page processed: {len(phones)} phones, {len(emails)} emails, {sum(len(l) for l in social_links.values())} social links")
                    
                    # Rate limiting
                    time.sleep(self.config.delay_between_requests)
                    
                except requests.RequestException as e:
                    logger.debug(f"Error crawling {url}: {e}")
                    continue
                except Exception as e:
                    logger.debug(f"Unexpected error crawling {url}: {e}")
                    continue
            
            # Deduplicate results
            contact_info.phone_numbers = list(set(contact_info.phone_numbers))
            contact_info.email_addresses = list(set(contact_info.email_addresses))
            contact_info.facebook_links = list(set(contact_info.facebook_links))
            contact_info.instagram_links = list(set(contact_info.instagram_links))
            contact_info.linkedin_links = list(set(contact_info.linkedin_links))
            
            # Update metadata
            contact_info.pages_crawled = pages_crawled
            contact_info.pages_with_contact_info = pages_with_info
            
            # Determine status and notes
            if contact_info.has_contact_info:
                contact_info.extraction_status = ContactExtractionStatus.SUCCESS.value
                contact_info.processing_notes = f"Successfully extracted {contact_info.total_contact_items} contact items from {len(pages_with_info)} pages"
            else:
                contact_info.extraction_status = ContactExtractionStatus.NO_CONTACT_INFO_FOUND.value
                contact_info.processing_notes = f"No contact information found after crawling {pages_crawled} pages"
            
            logger.info(f"Contact extraction completed for {domain}: {contact_info.total_contact_items} items found")
            
            return contact_info
            
        except Exception as e:
            logger.error(f"Critical error during contact extraction for {domain}: {e}")
            contact_info.extraction_status = ContactExtractionStatus.CRAWL_ERROR.value
            contact_info.processing_notes = f"Contact extraction failed: {str(e)}"
            return contact_info


# Convenience function for direct usage
def extract_contact_info(domain: str, config: Optional[ContactCrawlConfig] = None) -> ContactInformation:
    """
    Convenience function to extract contact information from a UK business website.
    
    Args:
        domain: Domain to extract contact information from
        config: Optional crawl configuration
        
    Returns:
        ContactInformation object with extracted UK phone numbers, emails, and social media
    """
    if not domain or not isinstance(domain, str):
        logger.error("Domain must be a non-empty string")
        return ContactInformation(
            domain=domain or "",
            extraction_status=ContactExtractionStatus.CRAWL_ERROR.value,
            processing_notes="Invalid domain provided"
        )
    
    extractor = ContactExtractor(config)
    return extractor.extract_contact_info(domain)


if __name__ == "__main__":
    import csv
    import os
    from pathlib import Path
    
    # Read websites from best_found_websites.csv
    csv_path = Path(__file__).parent.parent / "best_found_websites.csv"
    test_domains = []
    company_info = {}
    
    if csv_path.exists():
        print(f"📁 Reading websites from: {csv_path}")
        try:
            with open(csv_path, 'r', encoding='utf-8') as file:
                reader = csv.DictReader(file)
                for row in reader:
                    website_url = row.get('website_url', '').strip()
                    if website_url:
                        test_domains.append(website_url)
                        # Store company info for reference
                        company_info[website_url] = {
                            'company_name': row.get('company_name', ''),
                            'company_number': row.get('company_number', ''),
                            'vat_number': row.get('vat_number', ''),
                            'precision_score': row.get('precision_score', '')
                        }
            print(f"✅ Loaded {len(test_domains)} websites from CSV")
        except Exception as e:
            print(f"❌ Error reading CSV file: {e}")
            # Fallback to hardcoded domains
            test_domains = [
                "tpaccounts.co.uk",
                "timtayloraccountants.co.uk", 
                "timothyhignett.com"
            ]
            print(f"🔄 Using fallback domains: {len(test_domains)} websites")
    else:
        print(f"⚠️  CSV file not found at {csv_path}")
        # Fallback to hardcoded domains
        test_domains = [
            "tpaccounts.co.uk",
            "timtayloraccountants.co.uk",
            "timothyhignett.com"
        ]
        print(f"🔄 Using fallback domains: {len(test_domains)} websites")
    
    print(f"🔍 Testing UK-focused Contact Extractor for {len(test_domains)} domains:")
    print("=" * 80)
    
    # Configure extractor for UK business testing
    config = ContactCrawlConfig(
        max_pages_per_site=8,     # Reasonable number for testing
        timeout_seconds=20,
        delay_between_requests=1.0  # Respectful crawling
    )
    
    extractor = ContactExtractor(config)
    
    results = []
    
    for i, domain in enumerate(test_domains, 1):
        print(f"\n[{i}/{len(test_domains)}] Processing: {domain}")
        
        # Show company info if available
        if domain in company_info:
            info = company_info[domain]
            print(f"🏢 Company: {info['company_name']}")
            print(f"🔢 Company Number: {info['company_number']}")
            print(f"🧾 VAT Number: {info['vat_number'] or 'N/A'}")
            print(f"🎯 Precision Score: {info['precision_score']}")
        
        print("-" * 40)
        
        try:
            contact_info = extractor.extract_contact_info(domain)
            results.append(contact_info)
            
            # Print results for this domain
            print(f"✅ Status: {contact_info.extraction_status}")
            print(f"📄 Pages Crawled: {contact_info.pages_crawled}")
            print(f"📞 UK Phone Numbers ({len(contact_info.phone_numbers)}):")
            for phone in contact_info.phone_numbers[:5]:  # Show first 5
                print(f"   • {phone}")
            if len(contact_info.phone_numbers) > 5:
                print(f"   ... and {len(contact_info.phone_numbers) - 5} more")
            
            print(f"📧 Email Addresses ({len(contact_info.email_addresses)}):")
            for email in contact_info.email_addresses[:5]:  # Show first 5
                print(f"   • {email}")
            if len(contact_info.email_addresses) > 5:
                print(f"   ... and {len(contact_info.email_addresses) - 5} more")
            
            print(f"📱 Facebook Links ({len(contact_info.facebook_links)}):")
            for fb in contact_info.facebook_links:
                print(f"   • {fb}")
            
            print(f"📸 Instagram Links ({len(contact_info.instagram_links)}):")
            for ig in contact_info.instagram_links:
                print(f"   • {ig}")
            
            print(f"💼 LinkedIn Links ({len(contact_info.linkedin_links)}):")
            for li in contact_info.linkedin_links:
                print(f"   • {li}")
            
            print(f"📊 Total Contact Items: {contact_info.total_contact_items}")
            print(f"📝 Notes: {contact_info.processing_notes}")
            
        except Exception as e:
            print(f"❌ Error processing {domain}: {e}")
            results.append(ContactInformation(
                domain=domain,
                extraction_status=ContactExtractionStatus.CRAWL_ERROR.value,
                processing_notes=f"Test failed: {str(e)}"
            ))
    
    # Summary
    print("\n" + "=" * 80)
    print("UK-FOCUSED CONTACT EXTRACTION SUMMARY")
    print("=" * 80)
    
    successful_extractions = [r for r in results if r.is_success]
    total_contact_items = sum(r.total_contact_items for r in results)
    total_uk_phones = sum(len(r.phone_numbers) for r in results)
    
    print(f"📊 Total UK Companies Processed: {len(results)}")
    print(f"✅ Successful Extractions: {len(successful_extractions)}")
    print(f"📞 Total UK Phone Numbers Found: {total_uk_phones}")
    print(f"📧 Total Contact Items Found: {total_contact_items}")
    print(f"📈 Success Rate: {len(successful_extractions)/len(results)*100:.1f}%")
    
    if successful_extractions:
        print(f"\n🏆 BEST UK EXTRACTIONS:")
        # Sort by total contact items found
        sorted_results = sorted(results, key=lambda x: x.total_contact_items, reverse=True)
        for result in sorted_results[:3]:  # Show top 3
            if result.total_contact_items > 0:
                uk_phones = len(result.phone_numbers)
                print(f"   • {result.domain}: {result.total_contact_items} items ({uk_phones} UK phone numbers)")
    
    # Save results to CSV
    output_csv = Path(__file__).parent.parent / "contact_extraction_results.csv"
    try:
        with open(output_csv, 'w', newline='', encoding='utf-8') as file:
            fieldnames = [
                'domain', 'company_name', 'company_number', 'vat_number', 'precision_score',
                'extraction_status', 'pages_crawled', 'total_contact_items',
                'phone_numbers', 'email_addresses', 'facebook_links', 
                'instagram_links', 'linkedin_links', 'processing_notes', 'extraction_timestamp'
            ]
            
            writer = csv.DictWriter(file, fieldnames=fieldnames)
            writer.writeheader()
            
            for result in results:
                # Get company info if available
                company_data = company_info.get(result.domain, {})
                
                writer.writerow({
                    'domain': result.domain,
                    'company_name': company_data.get('company_name', ''),
                    'company_number': company_data.get('company_number', ''),
                    'vat_number': company_data.get('vat_number', ''),
                    'precision_score': company_data.get('precision_score', ''),
                    'extraction_status': result.extraction_status,
                    'pages_crawled': result.pages_crawled,
                    'total_contact_items': result.total_contact_items,
                    'phone_numbers': '; '.join(result.phone_numbers),
                    'email_addresses': '; '.join(result.email_addresses),
                    'facebook_links': '; '.join(result.facebook_links),
                    'instagram_links': '; '.join(result.instagram_links),
                    'linkedin_links': '; '.join(result.linkedin_links),
                    'processing_notes': result.processing_notes,
                    'extraction_timestamp': result.extraction_timestamp
                })
        
        print(f"\n💾 Results saved to: {output_csv}")
        
    except Exception as e:
        print(f"\n❌ Error saving results to CSV: {e}")
    
    print(f"\n✅ UK-focused contact extraction testing completed!") 