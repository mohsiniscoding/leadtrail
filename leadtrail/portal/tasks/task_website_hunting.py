"""
Website Hunting Task
===================

This task performs website hunting operations by combining SERP search for domain discovery
and website crawling for domain ranking. It processes companies that have completed VAT lookup
(regardless of success/failure) to maximize search potential using all available data.
"""
import logging
from typing import Dict, List, Any, Optional
from django.db import transaction

from config.celery_app import app
from celery_singleton import Singleton
from leadtrail.portal.models import (
    CompanyNumber, 
    WebsiteHuntingResult, 
    SearchKeyword, 
    SERPExcludedDomain, 
    BlacklistDomain
)
from leadtrail.portal.modules.website_hunter_api import WebsiteHunterClient
from leadtrail.portal.modules.website_crawler_v3 import WebsiteCrawlerV3, CrawlConfigV3

logger = logging.getLogger(__name__)

# Configuration
DEFAULT_BATCH_SIZE = 3


def _build_company_data(company_number_obj: CompanyNumber) -> Dict[str, Any]:
    """
    Build company data dict from all available sources for website hunting.
    
    Args:
        company_number_obj: CompanyNumber model instance
        
    Returns:
        Dict containing all available company identifiers
    """
    company_data = {
        'company_number': company_number_obj.company_number,
        'company_name': '',
        'vat_number': ''
    }
    
    # Get company name from Companies House data (if available)
    if hasattr(company_number_obj, 'house_data') and company_number_obj.house_data:
        house_data = company_number_obj.house_data
        if house_data.company_name:
            company_data['company_name'] = house_data.company_name
    
    # Get VAT number from VAT lookup (if available)
    if hasattr(company_number_obj, 'vat_lookup') and company_number_obj.vat_lookup:
        vat_lookup = company_number_obj.vat_lookup
        if vat_lookup.vat_number and vat_lookup.vat_number != "NOT_FOUND":
            company_data['vat_number'] = vat_lookup.vat_number
    
    logger.debug(f"Built company data for {company_number_obj.company_number}: "
                f"name='{company_data['company_name']}', vat='{company_data['vat_number']}'")
    
    return company_data


def _load_configuration_data() -> Dict[str, List[str]]:
    """
    Load search keywords and domain filters from database.
    
    Returns:
        Dict containing search_keywords, serp_excluded_domains, blacklist_domains
    """
    try:
        # Load search keywords
        search_keywords = list(SearchKeyword.objects.values_list('keyword', flat=True))
        
        # Load SERP excluded domains
        serp_excluded_domains = list(SERPExcludedDomain.objects.values_list('domain', flat=True))
        
        # Load blacklist domains
        blacklist_domains = list(BlacklistDomain.objects.values_list('domain', flat=True))
        
        logger.info(f"Loaded configuration: {len(search_keywords)} keywords, "
                   f"{len(serp_excluded_domains)} SERP excluded, {len(blacklist_domains)} blacklisted")
        
        return {
            'search_keywords': search_keywords,
            'serp_excluded_domains': serp_excluded_domains,
            'blacklist_domains': blacklist_domains
        }
        
    except Exception as e:
        logger.error(f"Error loading configuration data: {str(e)}")
        return {
            'search_keywords': [],
            'serp_excluded_domains': [],
            'blacklist_domains': []
        }


def _filter_blacklist_domains(domains: List[str], blacklist_domains: List[str]) -> List[str]:
    """
    Filter out blacklist domains from the SERP results.
    
    Args:
        domains: List of domains from SERP results
        blacklist_domains: List of domains to filter out
        
    Returns:
        Filtered list of domains
    """
    if not blacklist_domains:
        return domains
    
    blacklist_set = set(blacklist_domains)
    filtered_domains = [domain for domain in domains if domain not in blacklist_set]
    
    filtered_count = len(domains) - len(filtered_domains)
    if filtered_count > 0:
        logger.info(f"Filtered out {filtered_count} blacklisted domains from SERP results")
    
    return filtered_domains


def _process_website_hunting(company_number_obj: CompanyNumber, 
                           hunter_client: Optional[WebsiteHunterClient],
                           crawler: WebsiteCrawlerV3,
                           config_data: Dict[str, List[str]]) -> bool:
    """
    Process website hunting for a single company using two-phase workflow.
    
    Args:
        company_number_obj: CompanyNumber model instance
        hunter_client: WebsiteHunterClient instance (can be None if API not configured)
        crawler: WebsiteCrawlerV3 instance
        config_data: Configuration data with keywords and domain filters
        
    Returns:
        bool: True if processing was successful, False otherwise
    """
    try:
        logger.info(f"Processing website hunting for company: {company_number_obj.company_number}")
        
        # Build company data from all available sources
        company_data = _build_company_data(company_number_obj)
        
        # Phase 1: SERP Discovery
        serp_domains = []
        serp_status = "NO_HUNTER_CLIENT"
        serp_notes = ""
        
        if hunter_client:
            try:
                logger.info(f"Phase 1: SERP discovery for {company_number_obj.company_number}")
                
                search_result = hunter_client.find_company_website(
                    company_data,
                    config_data['search_keywords'],
                    config_data['serp_excluded_domains']
                )
                
                serp_status = search_result.search_status
                serp_domains = search_result.websites_found
                serp_notes = search_result.processing_notes
                
                logger.info(f"SERP phase completed: {serp_status}, {len(serp_domains)} domains found")
                
            except Exception as e:
                logger.error(f"SERP discovery failed for {company_number_obj.company_number}: {str(e)}")
                serp_status = "SERP_ERROR"
                serp_notes = f"SERP error: {str(e)}"
        else:
            logger.warning(f"No SERP client available for {company_number_obj.company_number}")
            serp_notes = "SERP client not configured (missing ZenSERP API key)"
        
        # Filter blacklist domains from SERP results
        if serp_domains:
            filtered_domains = _filter_blacklist_domains(serp_domains, config_data['blacklist_domains'])
        else:
            filtered_domains = []
        
        # Phase 2: Website Ranking (only if we have domains)
        ranked_results = []
        crawl_status = "NO_DOMAINS_TO_CRAWL"
        crawl_notes = ""
        
        if filtered_domains:
            try:
                logger.info(f"Phase 2: Website ranking for {company_number_obj.company_number} ({len(filtered_domains)} domains)")
                
                scored_results = crawler.crawl_and_rank_websites(filtered_domains, company_data)
                
                # Convert crawler results to JSON-serializable format
                ranked_results = []
                for result in scored_results:
                    ranked_results.append({
                        'domain': result.domain,
                        'score': result.total_score,
                        'pages_crawled': result.pages_crawled,
                        'status': result.crawl_status,
                        'match_summary': result.get_match_summary()
                    })
                
                if ranked_results:
                    crawl_status = "CRAWL_SUCCESS"
                    crawl_notes = f"Successfully ranked {len(ranked_results)} domains"
                else:
                    crawl_status = "CRAWL_NO_RESULTS"
                    crawl_notes = "Crawler completed but no results returned"
                
                logger.info(f"Crawl phase completed: {crawl_status}, {len(ranked_results)} results")
                
            except Exception as e:
                logger.error(f"Website crawling failed for {company_number_obj.company_number}: {str(e)}")
                crawl_status = "CRAWL_ERROR"
                crawl_notes = f"Crawl error: {str(e)}"
        else:
            crawl_notes = "No domains available for crawling after filtering"
        
        # Determine overall processing notes
        processing_notes = f"SERP: {serp_notes}. Crawl: {crawl_notes}"
        
        # Create WebsiteHuntingResult record
        website_result = WebsiteHuntingResult(
            company_number=company_number_obj,
            domains_found=serp_domains,
            ranked_domains=ranked_results,
            serp_status=serp_status,
            crawl_status=crawl_status,
            processing_notes=processing_notes,
            approved_by_human=False
        )
        
        with transaction.atomic():
            website_result.save()
        
        logger.info(f"Website hunting completed for {company_number_obj.company_number}: "
                   f"SERP({serp_status}), Crawl({crawl_status})")
        return True
        
    except Exception as e:
        logger.error(f"Error processing website hunting for {company_number_obj.company_number}: {str(e)}")
        
        # Create error record in database
        try:
            error_result = WebsiteHuntingResult(
                company_number=company_number_obj,
                domains_found=[],
                ranked_domains=[],
                serp_status="PROCESSING_ERROR",
                crawl_status="PROCESSING_ERROR",
                processing_notes=f"Processing error: {str(e)}",
                approved_by_human=False
            )
            
            with transaction.atomic():
                error_result.save()
                
        except Exception as save_error:
            logger.error(f"Failed to save error record for {company_number_obj.company_number}: {str(save_error)}")
        
        return False


@app.task(base=Singleton, lock_expiry=600, raise_on_duplicate=False)
def run():
    """
    Website hunting background task.
    
    Processes companies that have completed VAT lookup (regardless of success/failure)
    using a two-phase workflow: SERP discovery + website crawling.
    
    Returns:
        str: Summary of processing results
    """
    logger.info("[SINGLETON] Website hunting task started - Lock expiry: 600s")
    
    try:
        # Get companies ready for website hunting (VAT lookup completed, oldest first)
        companies_to_process = CompanyNumber.objects.filter(
            vat_lookup__isnull=False,  # VAT lookup completed
            website_hunting_result__isnull=True  # Website hunting not done yet
        ).select_related('house_data', 'vat_lookup').order_by('created_at')[:DEFAULT_BATCH_SIZE]
        
        if not companies_to_process:
            logger.info("No companies ready for website hunting")
            return "No companies ready for website hunting"
        
        logger.info(f"Processing {len(companies_to_process)} companies for website hunting")
        
        # Load configuration data from database
        config_data = _load_configuration_data()
        
        if not config_data['search_keywords']:
            logger.warning("No search keywords configured - website hunting may be less effective")
        
        # Initialize website hunter client (can be None if no API key)
        hunter_client = None
        try:
            hunter_client = WebsiteHunterClient(query_version=2)  # Use v2 for inurl: searches
            logger.info("Website hunter client initialized successfully")
        except ValueError as e:
            logger.warning(f"Website hunter client not available: {str(e)}")
        
        # Initialize website crawler
        crawler_config = CrawlConfigV3(
            max_target_pages=3,
            max_additional_pages=6,
            timeout_seconds=30,
            max_concurrent_sites=2,
            delay_between_requests=1.0
        )
        crawler = WebsiteCrawlerV3(crawler_config)
        logger.info("Website crawler initialized successfully")
        
        # Process each company
        successful_count = 0
        failed_count = 0
        
        for company in companies_to_process:
            try:
                success = _process_website_hunting(
                    company, 
                    hunter_client, 
                    crawler, 
                    config_data
                )
                
                if success:
                    successful_count += 1
                else:
                    failed_count += 1
                    
            except Exception as e:
                logger.error(f"Error processing company {company.company_number}: {str(e)}")
                failed_count += 1
        
        # Return summary
        summary = f"Website hunting completed: {successful_count} successful, {failed_count} failed out of {len(companies_to_process)} companies"
        logger.info(summary)
        return summary
        
    except Exception as e:
        error_msg = f"Website hunting task failed: {str(e)}"
        logger.error(error_msg)
        return error_msg
