"""
Portal app views.
"""
import re
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import HttpResponseRedirect, JsonResponse
from django.urls import reverse
from django.utils.decorators import method_decorator
from django.utils import timezone
from django.views.generic import ListView, TemplateView
from django.views.decorators.http import require_POST

from .models import Campaign, CompanyNumber, SERPExcludedDomain, BlacklistDomain, ZenSERPQuota, SnovQuota, HunterQuota, SearchKeyword, WebsiteHuntingResult, LinkedinEmployeeReview
from leadtrail.exports.companies_house_lookup import generate_companies_house_csv
from leadtrail.exports.vat_lookup import generate_vat_lookup_csv
from leadtrail.exports.contact_extraction import generate_contact_extraction_csv
from leadtrail.exports.linkedin_finder import generate_linkedin_finder_csv
from leadtrail.exports.snov_lookup import generate_snov_lookup_csv
from leadtrail.exports.hunter_lookup import generate_hunter_lookup_csv
from leadtrail.exports.full_export import generate_full_export_excel


@method_decorator(login_required, name='dispatch')
class CampaignListView(ListView):
    """
    View to list all campaigns.
    """
    model = Campaign
    template_name = "portal/campaigns.html"
    context_object_name = "campaigns"
    paginate_by = 20
    
    def get_context_data(self, **kwargs):
        from datetime import timedelta

        context = super().get_context_data(**kwargs)

        # Check if quotas need refreshing (older than 2 minutes)
        now = timezone.now()
        refresh_threshold = timedelta(minutes=2)

        # Add ZenSERP quota to context
        zenserp_quota = ZenSERPQuota.get_current_quota()
        if now - zenserp_quota.last_updated > refresh_threshold:
            try:
                from leadtrail.portal.modules.website_hunter_api import WebsiteHunterClient
                client = WebsiteHunterClient()
                quota_data = client.check_api_quota()
                if quota_data:
                    zenserp_quota.available_credits = quota_data.get('remaining_requests', 0)
                    zenserp_quota.save()
            except Exception:
                pass  # Use existing quota data if refresh fails
        context['zenserp_quota'] = zenserp_quota

        # Add Snov quota to context
        snov_quota = SnovQuota.get_current_quota()
        if now - snov_quota.last_updated > refresh_threshold:
            try:
                from leadtrail.portal.utils.snov_client import SnovClient
                from decimal import Decimal
                client = SnovClient()
                balance_data = client.check_api_quota()
                if balance_data:
                    available_credits = balance_data.get('balance', '0.00')
                    try:
                        snov_quota.available_credits = Decimal(str(available_credits))
                        snov_quota.save()
                    except (TypeError, ValueError):
                        pass
            except Exception:
                pass  # Use existing quota data if refresh fails
        context['snov_quota'] = snov_quota

        # Add Hunter quota to context
        hunter_quota = HunterQuota.get_current_quota()
        if now - hunter_quota.last_updated > refresh_threshold:
            try:
                from leadtrail.portal.utils.hunter_client import HunterClient
                from decimal import Decimal
                client = HunterClient()
                balance_data = client.check_api_quota()
                if balance_data:
                    available_credits = balance_data.get('available_credits', 0.0)
                    try:
                        hunter_quota.available_credits = Decimal(str(available_credits))
                        hunter_quota.save()
                    except (TypeError, ValueError):
                        pass
            except Exception:
                pass  # Use existing quota data if refresh fails
        context['hunter_quota'] = hunter_quota

        return context


@method_decorator(login_required, name='dispatch')
class CampaignCreateView(TemplateView):
    """
    View to create a new campaign.
    """
    template_name = "portal/campaign_create.html"
    
    def get_context_data(self, **kwargs):
        """Add context data to the template."""
        context = super().get_context_data(**kwargs)
        # context['has_existing_campaign'] = Campaign.objects.exists() ## TODO: uncomment
        context['has_existing_campaign'] = False ## TODO: remove
        return context
    
    def post(self, request, *args, **kwargs):
        """Handle POST requests: create a campaign."""
        # Get form data
        name = request.POST.get('name', '')
        company_numbers_text = request.POST.get('company_numbers', '')
        
        # Sanitize company numbers (only digits)
        company_numbers = []
        for number in company_numbers_text.split('\n'):
            number = number.strip()
            if number and number.isdigit():
                company_numbers.append(number)
        
        # Remove duplicates
        unique_company_numbers = list(set(company_numbers))
        
        if not name:
            messages.error(request, "Campaign name is required.")
            return self.render_to_response(self.get_context_data())
        
        if not unique_company_numbers:
            messages.error(request, "At least one valid company number is required.")
            return self.render_to_response(self.get_context_data())
        
        ## TODO: uncomment
        # Check if a campaign already exists
        # if Campaign.objects.exists():
        #     messages.error(request, "You can have 1 campaign running at a time, this is to save resources and database calls on Heroku")
        #     return self.render_to_response(self.get_context_data())
            
        # Create campaign
        campaign = Campaign.objects.create(name=name)
        
        # Create company numbers
        for number in unique_company_numbers:
            CompanyNumber.objects.create(
                company_number=number,
                campaign=campaign
            )
        
        messages.success(
            request, 
            f"Campaign '{name}' created with {len(unique_company_numbers)} company numbers."
        )
        return HttpResponseRedirect(reverse('portal:home'))


@method_decorator(login_required, name='dispatch')
class HowToView(TemplateView):
    """
    View for How-To guide page.
    """
    template_name = "portal/how_to.html"


@method_decorator(login_required, name='dispatch')
class SERPSettingsView(TemplateView):
    """
    View for SERP settings management.
    """
    template_name = "portal/serp_settings.html"
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['serp_excluded_domains'] = SERPExcludedDomain.objects.all()
        context['blacklist_domains'] = BlacklistDomain.objects.all()
        context['search_keywords'] = SearchKeyword.objects.all()
        context['zenserp_quota'] = ZenSERPQuota.get_current_quota()
        
        # Add domain suggestions
        try:
            from django.core.cache import cache
            cache_key = 'domain_suggestions'
            suggestions = cache.get(cache_key)
            
            if suggestions is None:
                suggestions = WebsiteHuntingResult.get_domain_suggestions(limit=20)
                cache.set(cache_key, suggestions, 600)  # Cache for 10 minutes
            
            context['domain_suggestions'] = suggestions
        except Exception as e:
            context['domain_suggestions'] = []
            
        return context
    
    def post(self, request, *args, **kwargs):
        """Handle POST requests: add domains or search keywords."""
        form_type = request.POST.get('form_type')
        
        if form_type == 'keyword':
            return self._handle_keyword_form(request)
        else:
            return self._handle_domain_form(request)
    
    def _handle_keyword_form(self, request):
        """Handle search keyword form submission."""
        keyword = request.POST.get('keyword', '').strip()
        
        if not keyword:
            messages.error(request, "Search keyword cannot be empty.")
            return HttpResponseRedirect(reverse('portal:serp_settings'))
        
        # Validate keyword (should not be too long and should be reasonable)
        if len(keyword) > 255:
            messages.error(request, "Search keyword is too long (maximum 255 characters).")
            return HttpResponseRedirect(reverse('portal:serp_settings'))
        
        try:
            SearchKeyword.objects.create(keyword=keyword)
            messages.success(request, f"Search keyword '{keyword}' added successfully.")
        except Exception as e:
            if "UNIQUE constraint failed" in str(e) or "duplicate key" in str(e):
                messages.error(request, f"Search keyword '{keyword}' already exists.")
            else:
                messages.error(request, f"Error adding search keyword: {str(e)}")
        
        return HttpResponseRedirect(reverse('portal:serp_settings'))
    
    def _handle_domain_form(self, request):
        """Handle domain form submission."""
        domain_type = request.POST.get('domain_type')
        domain = request.POST.get('domain', '').strip().lower()
        
        if not domain:
            messages.error(request, "Domain cannot be empty.")
            return HttpResponseRedirect(reverse('portal:serp_settings'))
        
        ## valid domain example.com
        regex = r'^([a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?\.)+[a-zA-Z]{2,}$'
        if not re.match(regex, domain):
            messages.error(request, f"Invalid domain format ({domain}). Valid format: example.com")
            return HttpResponseRedirect(reverse('portal:serp_settings'))

        try:
            if domain_type == 'serp':
                SERPExcludedDomain.objects.create(domain=domain)
                messages.success(request, f"Domain '{domain}' added to SERP excluded domains.")
            elif domain_type == 'blacklist':
                BlacklistDomain.objects.create(domain=domain)
                messages.success(request, f"Domain '{domain}' added to blacklist domains.")
        except Exception as e:
            messages.error(request, f"Error adding domain: {str(e)}")
        
        return HttpResponseRedirect(reverse('portal:serp_settings'))


@require_POST
@login_required
def delete_domain(request):
    """Delete a domain or search keyword."""
    item_id = request.POST.get('domain_id')  # keeping same name for backward compatibility
    item_type = request.POST.get('domain_type')  # keeping same name for backward compatibility
    
    try:
        if item_type == 'serp':
            domain = SERPExcludedDomain.objects.get(id=item_id)
            domain_name = domain.domain
            domain.delete()
            messages.success(request, f"Domain '{domain_name}' removed from SERP excluded domains.")
        elif item_type == 'blacklist':
            domain = BlacklistDomain.objects.get(id=item_id)
            domain_name = domain.domain
            domain.delete()
            messages.success(request, f"Domain '{domain_name}' removed from blacklist domains.")
        elif item_type == 'keyword':
            keyword = SearchKeyword.objects.get(id=item_id)
            keyword_text = keyword.keyword
            
            # Check if at least 1 keyword will remain
            remaining_count = SearchKeyword.objects.exclude(id=item_id).count()
            if remaining_count == 0:
                messages.error(request, "Cannot delete the last search keyword. At least one keyword must remain.")
                return HttpResponseRedirect(reverse('portal:serp_settings'))
            
            keyword.delete()
            messages.success(request, f"Search keyword '{keyword_text}' removed successfully.")
        return HttpResponseRedirect(reverse('portal:serp_settings'))
    except Exception as e:
        messages.error(request, f"Error removing item: {str(e)}")
        return HttpResponseRedirect(reverse('portal:serp_settings'))


@method_decorator(login_required, name='dispatch')
class WebsiteHumanReviewView(ListView):
    """
    View for human review of website hunting results.
    """
    model = CompanyNumber
    template_name = "portal/website_human_review.html"
    context_object_name = "companies"
    paginate_by = 10
    
    def get_queryset(self):
        """Get companies for the specified campaign, ordered by creation date."""
        campaign_id = self.kwargs.get('campaign_id')
        queryset = CompanyNumber.objects.filter(
            campaign_id=campaign_id
        ).select_related(
            'house_data', 'vat_lookup', 'website_hunting_result'
        )
        
        # Apply non-zero score filter if requested
        non_zero_filter = self.request.GET.get('non_zero_score')
        if non_zero_filter == 'true':
            # Get all companies and filter in Python for simplicity
            all_companies = list(queryset)
            filtered_companies = []
            
            for company in all_companies:
                try:
                    if (company.website_hunting_result and 
                        company.website_hunting_result.ranked_domains):
                        # Check if any domain has a score > 0
                        has_non_zero_score = any(
                            domain.get('score', 0) > 0 
                            for domain in company.website_hunting_result.ranked_domains
                        )
                        if has_non_zero_score:
                            filtered_companies.append(company.id)
                except CompanyNumber.website_hunting_result.RelatedObjectDoesNotExist:
                    # Company has no website hunting result, skip it
                    continue
            
            # Filter queryset by the company IDs that have non-zero scores
            queryset = queryset.filter(id__in=filtered_companies)
        
        # Apply unapproved filter if requested
        unapproved_filter = self.request.GET.get('unapproved_only')
        if unapproved_filter == 'true':
            # Show only companies that haven't been approved yet
            # This includes companies with no website_hunting_result or approved_by_human=False
            from django.db import models
            queryset = queryset.filter(
                models.Q(website_hunting_result__isnull=True) |
                models.Q(website_hunting_result__approved_by_human=False)
            )
        
        return queryset.order_by('created_at')
    
    def get_paginate_by(self, queryset):
        """Allow dynamic pagination based on URL parameter."""
        per_page = self.request.GET.get('per_page', self.paginate_by)
        try:
            per_page = int(per_page)
            if per_page in [10, 25, 50]:
                return per_page
        except (ValueError, TypeError):
            pass
        return self.paginate_by
    
    def get_context_data(self, **kwargs):
        """Add campaign and pagination context."""
        context = super().get_context_data(**kwargs)
        campaign_id = self.kwargs.get('campaign_id')
        campaign = Campaign.objects.get(id=campaign_id)
        
        context['campaign'] = campaign
        context['per_page_options'] = [10, 25, 50]
        context['current_per_page'] = self.get_paginate_by(None)
        context['non_zero_filter'] = self.request.GET.get('non_zero_score', 'false')
        context['unapproved_filter'] = self.request.GET.get('unapproved_only', 'false')
        
        # Add blacklisted domains for UI indication
        blacklisted_domains = set(BlacklistDomain.objects.values_list('domain', flat=True))
        context['blacklisted_domains'] = blacklisted_domains
        
        return context
    
    def post(self, request, *args, **kwargs):
        """Handle approval and blacklist actions."""
        action = request.POST.get('action')
        company_id = request.POST.get('company_id')
        domain = request.POST.get('domain')
        
        try:
            company = CompanyNumber.objects.get(id=company_id)
            
            if action == 'approve':
                # Approve domain
                hunting_result = company.website_hunting_result
                hunting_result.approved_domain = domain
                hunting_result.approved_by_human = True
                hunting_result.save()
                
                messages.success(request, f"Domain '{domain}' approved for company {company.company_number}")
                
            elif action == 'blacklist':
                # Add domain to blacklist
                BlacklistDomain.objects.get_or_create(domain=domain)
                messages.success(request, f"Domain '{domain}' added to blacklist")
                
            else:
                messages.error(request, "Invalid action")
                
        except CompanyNumber.DoesNotExist:
            messages.error(request, "Company not found")
        except Exception as e:
            messages.error(request, f"Error processing request: {str(e)}")
        
        # Redirect back to the same page with current pagination and filters
        campaign_id = self.kwargs.get('campaign_id')
        page = request.GET.get('page', 1)
        per_page = request.GET.get('per_page', 10)
        non_zero_score = request.GET.get('non_zero_score', 'false')
        
        redirect_url = reverse('portal:website_human_review', kwargs={'campaign_id': campaign_id})
        return HttpResponseRedirect(f"{redirect_url}?page={page}&per_page={per_page}&non_zero_score={non_zero_score}")


@method_decorator(login_required, name='dispatch')
class LinkedinEmployeeReviewView(ListView):
    """
    View for human review of LinkedIn employee URLs from both Website Contact Extraction 
    and LinkedIn Profile Discovery sources.
    """
    model = CompanyNumber
    template_name = "portal/linkedin_employee_review.html"
    context_object_name = "companies"
    paginate_by = 10
    
    def get_queryset(self):
        """Get companies for the specified campaign that have LinkedIn lookup data."""
        campaign_id = self.kwargs.get('campaign_id')
        queryset = CompanyNumber.objects.filter(
            campaign_id=campaign_id,
            linkedin_lookup__isnull=False  # Has LinkedIn profile discovery (required)
        ).select_related(
            'house_data', 'vat_lookup', 'website_hunting_result', 
            'website_contact_lookup', 'linkedin_lookup', 'linkedin_employee_review'
        )
        
        # Apply show_unapproved filter if requested
        show_unapproved_filter = self.request.GET.get('show_unapproved')
        if show_unapproved_filter == 'true':
            # Only show companies that don't have LinkedinEmployeeReview records yet
            queryset = queryset.filter(linkedin_employee_review__isnull=True)
        
        # Apply non-zero filter if requested
        non_zero_filter = self.request.GET.get('non_zero_employees')
        if non_zero_filter == 'true':
            # Get all companies and filter in Python for simplicity
            all_companies = list(queryset)
            filtered_companies = []
            
            for company in all_companies:
                linkedin_data = self._extract_linkedin_employees(company)
                if linkedin_data['total_count'] > 0:
                    filtered_companies.append(company.id)
            
            # Filter queryset by the company IDs that have LinkedIn employees
            queryset = queryset.filter(id__in=filtered_companies)
        
        return queryset.order_by('created_at')
    
    def get_context_data(self, **kwargs):
        """Add campaign and LinkedIn employee data context."""
        context = super().get_context_data(**kwargs)
        campaign_id = self.kwargs.get('campaign_id')
        campaign = Campaign.objects.get(id=campaign_id)
        
        context['campaign'] = campaign
        context['non_zero_filter'] = self.request.GET.get('non_zero_employees', 'false')
        context['show_unapproved_filter'] = self.request.GET.get('show_unapproved', 'false')
        
        # Process LinkedIn employee URLs for each company
        processed_companies = []
        for company in context['companies']:
            company_data = {
                'company': company,
                'linkedin_employees': self._extract_linkedin_employees(company)
            }
            processed_companies.append(company_data)
        
        context['processed_companies'] = processed_companies
        return context
    
    def _extract_linkedin_employees(self, company):
        """
        Extract LinkedIn employee URLs from LinkedIn Profile Discovery (required) and 
        Website Contact Extraction (optional, only if available).
        
        Args:
            company: CompanyNumber instance with linkedin_lookup (required) and 
                    website_contact_lookup (optional)
        
        Returns:
            dict: Contains 'website_crawling', 'linkedin_discovery', 'total_count', and 'approved_urls'
        """
        linkedin_employees = {
            'website_crawling': [],
            'linkedin_discovery': [],
            'total_count': 0,
            'approved_urls': set()  # Track which URLs are already approved
        }
        
        # Get previously approved URLs if they exist
        try:
            if hasattr(company, 'linkedin_employee_review') and company.linkedin_employee_review:
                approved_records = company.linkedin_employee_review.approved_employee_urls
                if approved_records:
                    for record in approved_records:
                        if isinstance(record, dict) and 'url' in record:
                            linkedin_employees['approved_urls'].add(record['url'])
        except Exception:
            pass
        
        # Extract from Website Contact Extraction (social_media_links.linkedin)
        try:
            if (hasattr(company, 'website_contact_lookup') and 
                company.website_contact_lookup and 
                company.website_contact_lookup.social_media_links):
                
                social_links = company.website_contact_lookup.social_media_links
                if isinstance(social_links, dict) and 'linkedin' in social_links:
                    linkedin_urls = social_links['linkedin']
                    if isinstance(linkedin_urls, list):
                        # Filter for employee/people profiles (not company pages)
                        employee_urls = [
                            url for url in linkedin_urls 
                            if '/in/' in url  # Employee profiles contain '/in/'
                        ]
                        linkedin_employees['website_crawling'] = employee_urls
        except (AttributeError, TypeError):
            pass
        
        # Extract from LinkedIn Profile Discovery (employee_urls)
        try:
            if (hasattr(company, 'linkedin_lookup') and 
                company.linkedin_lookup and 
                company.linkedin_lookup.employee_urls):
                
                employee_urls = company.linkedin_lookup.employee_urls
                if isinstance(employee_urls, list):
                    # Extract just the URLs from the employee_urls objects
                    discovery_urls = [
                        emp_obj.get('url', '') for emp_obj in employee_urls 
                        if isinstance(emp_obj, dict) and emp_obj.get('url')
                    ]
                    linkedin_employees['linkedin_discovery'] = discovery_urls
        except (AttributeError, TypeError):
            pass
        
        # Calculate total count
        linkedin_employees['total_count'] = (
            len(linkedin_employees['website_crawling']) + 
            len(linkedin_employees['linkedin_discovery'])
        )
        
        return linkedin_employees
    
    def post(self, request, *args, **kwargs):
        """Handle LinkedIn employee URL approvals."""
        try:
            company_id = request.POST.get('company_id')
            approved_urls = request.POST.getlist('approved_urls')  # Get list of selected URLs
            
            if not company_id:
                messages.error(request, 'Company ID is required')
                return self._redirect_with_pagination(request)
            
            try:
                company = CompanyNumber.objects.get(id=company_id)
            except CompanyNumber.DoesNotExist:
                messages.error(request, 'Company not found')
                return self._redirect_with_pagination(request)
            
            # Get or create LinkedinEmployeeReview record
            linkedin_review, created = LinkedinEmployeeReview.objects.get_or_create(
                company_number=company,
                defaults={
                    'approved_employee_urls': []
                }
            )
            
            # Extract LinkedIn employee data to determine sources
            linkedin_data = self._extract_linkedin_employees(company)
            
            # Build source breakdown for approved URLs
            source_breakdown = {
                'website_crawling': [],
                'linkedin_discovery': []
            }
            
            approved_urls_with_source = []
            
            for url in approved_urls:
                url_data = {'url': url, 'approved_at': timezone.now().isoformat()}
                
                # Determine source of each approved URL
                if url in linkedin_data['website_crawling']:
                    url_data['source'] = 'website_crawling'
                    source_breakdown['website_crawling'].append(url)
                elif url in linkedin_data['linkedin_discovery']:
                    url_data['source'] = 'linkedin_discovery'
                    source_breakdown['linkedin_discovery'].append(url)
                else:
                    url_data['source'] = 'unknown'
                
                approved_urls_with_source.append(url_data)
            
            # Handle the review record based on whether URLs are approved
            if approved_urls:
                # Update the review record with approved URLs
                linkedin_review.approved_employee_urls = approved_urls_with_source
                linkedin_review.save()
                
                messages.success(
                    request, 
                    f"✓ {len(approved_urls)} LinkedIn profile(s) approved for Company #{company.company_number}"
                )
            else:
                # Delete the review record if no URLs are selected
                linkedin_review.delete()
                messages.info(
                    request, 
                    f"No LinkedIn profiles selected for Company #{company.company_number}. Review record removed."
                )
                
        except Exception as e:
            messages.error(request, f"Error saving LinkedIn approvals: {str(e)}")
        
        return self._redirect_with_pagination(request)
    
    def _redirect_with_pagination(self, request):
        """Redirect back to the same page preserving pagination and filters."""
        campaign_id = self.kwargs.get('campaign_id')
        page = request.GET.get('page', 1)
        non_zero_employees = request.GET.get('non_zero_employees', 'false')
        show_unapproved = request.GET.get('show_unapproved', 'false')
        
        redirect_url = reverse('portal:linkedin_employee_review', kwargs={'campaign_id': campaign_id})
        params = f"?page={page}&non_zero_employees={non_zero_employees}&show_unapproved={show_unapproved}"
        
        return HttpResponseRedirect(f"{redirect_url}{params}")


@require_POST
@login_required
def delete_campaign(request, campaign_id):
    """Delete a campaign and all its associated company numbers."""
    try:
        campaign = Campaign.objects.get(id=campaign_id)
        campaign_name = campaign.name
        company_count = campaign.company_numbers.count()
        
        # Delete the campaign (cascade will handle related objects)
        campaign.delete()
        
        messages.success(
            request, 
            f"Campaign '{campaign_name}' and its {company_count} company numbers have been deleted successfully."
        )
        
    except Campaign.DoesNotExist:
        messages.error(request, "Campaign not found.")
    except Exception as e:
        messages.error(request, f"Error deleting campaign: {str(e)}")
    
    return HttpResponseRedirect(reverse('portal:home'))


@login_required
def get_domain_suggestions(request):
    """Get domain suggestions for blacklisting."""
    try:
        from django.core.cache import cache
        
        # Try to get suggestions from cache first
        cache_key = 'domain_suggestions'
        suggestions = cache.get(cache_key)
        
        if suggestions is None:
            # Get suggestions from database
            suggestions = WebsiteHuntingResult.get_domain_suggestions(limit=20)
            # Cache for 10 minutes
            cache.set(cache_key, suggestions, 600)
        
        # Format for JSON response
        suggestion_list = [
            {'domain': domain, 'frequency': frequency}
            for domain, frequency in suggestions
        ]
        
        return JsonResponse({
            'suggestions': suggestion_list,
            'total_count': len(suggestion_list)
        })
        
    except Exception as e:
        return JsonResponse({
            'error': f"Error fetching domain suggestions: {str(e)}"
        }, status=500)


@require_POST
@login_required
def add_suggested_domain(request):
    """Add a suggested domain to blacklist."""
    try:
        domain = request.POST.get('domain', '').strip().lower()
        
        if not domain:
            return JsonResponse({
                'error': 'Domain cannot be empty'
            }, status=400)
        
        # Validate domain format
        regex = r'^([a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?\.)+[a-zA-Z]{2,}$'
        if not re.match(regex, domain):
            return JsonResponse({
                'error': f'Invalid domain format: {domain}'
            }, status=400)
        
        # Add to blacklist
        blacklist_domain, created = BlacklistDomain.objects.get_or_create(domain=domain)
        
        if created:
            # Clear domain suggestions cache to refresh the list
            from django.core.cache import cache
            cache.delete('domain_suggestions')
            
            return JsonResponse({
                'success': True,
                'message': f"Domain '{domain}' added to blacklist successfully"
            })
        else:
            return JsonResponse({
                'error': f"Domain '{domain}' is already in blacklist"
            }, status=400)
            
    except Exception as e:
        return JsonResponse({
            'error': f"Error adding domain to blacklist: {str(e)}"
        }, status=500)




@require_POST
@login_required
def website_review_action(request):
    """Handle AJAX approval and blacklist actions for website review."""
    try:
        action = request.POST.get('action')
        company_id = request.POST.get('company_id')
        domain = request.POST.get('domain')
        
        if not all([action, company_id, domain]):
            return JsonResponse({
                'error': 'Missing required parameters'
            }, status=400)
        
        try:
            company = CompanyNumber.objects.get(id=company_id)
        except CompanyNumber.DoesNotExist:
            return JsonResponse({
                'error': 'Company not found'
            }, status=404)
        
        if action == 'approve':
            # Approve domain
            hunting_result = company.website_hunting_result
            hunting_result.approved_domain = domain
            hunting_result.approved_by_human = True
            hunting_result.save()
            
            return JsonResponse({
                'success': True,
                'action': 'approve',
                'message': f"Domain '{domain}' approved for company {company.company_number}",
                'approved_domain': domain
            })
            
        elif action == 'blacklist':
            # Add domain to blacklist
            BlacklistDomain.objects.get_or_create(domain=domain)
            return JsonResponse({
                'success': True,
                'action': 'blacklist',
                'message': f"Domain '{domain}' added to blacklist"
            })
            
        elif action == 'remove_approval':
            # Remove approval from domain
            hunting_result = company.website_hunting_result
            hunting_result.approved_domain = None
            hunting_result.approved_by_human = False
            hunting_result.save()
            
            return JsonResponse({
                'success': True,
                'action': 'remove_approval',
                'message': f"Approval removed for domain '{domain}' from company {company.company_number}"
            })
            
        else:
            return JsonResponse({
                'error': 'Invalid action'
            }, status=400)
            
    except Exception as e:
        return JsonResponse({
            'error': f"Error processing request: {str(e)}"
        }, status=500)


@login_required
def export_companies_house_csv(request, campaign_id):
    """Export Companies House lookup data as CSV."""
    try:
        campaign = Campaign.objects.get(id=campaign_id)
        return generate_companies_house_csv(campaign)
    except Campaign.DoesNotExist:
        messages.error(request, "Campaign not found.")
        return HttpResponseRedirect(reverse('portal:home'))


@login_required
def export_vat_lookup_csv(request, campaign_id):
    """Export VAT lookup data as CSV."""
    try:
        campaign = Campaign.objects.get(id=campaign_id)
        return generate_vat_lookup_csv(campaign)
    except Campaign.DoesNotExist:
        messages.error(request, "Campaign not found.")
        return HttpResponseRedirect(reverse('portal:home'))




@login_required
def export_contact_extraction_csv(request, campaign_id):
    """Export Contact Extraction data as CSV."""
    try:
        campaign = Campaign.objects.get(id=campaign_id)
        return generate_contact_extraction_csv(campaign)
    except Campaign.DoesNotExist:
        messages.error(request, "Campaign not found.")
        return HttpResponseRedirect(reverse('portal:home'))


@login_required
def export_linkedin_finder_csv(request, campaign_id):
    """Export LinkedIn Finder data as CSV."""
    try:
        campaign = Campaign.objects.get(id=campaign_id)
        return generate_linkedin_finder_csv(campaign)
    except Campaign.DoesNotExist:
        messages.error(request, "Campaign not found.")
        return HttpResponseRedirect(reverse('portal:home'))


@login_required
def export_snov_lookup_csv(request, campaign_id):
    """Export Snov.io lookup data as CSV."""
    try:
        campaign = Campaign.objects.get(id=campaign_id)
        return generate_snov_lookup_csv(campaign)
    except Campaign.DoesNotExist:
        messages.error(request, "Campaign not found.")
        return HttpResponseRedirect(reverse('portal:home'))


@login_required
def export_hunter_lookup_csv(request, campaign_id):
    """Export Hunter.io lookup data as CSV."""
    try:
        campaign = Campaign.objects.get(id=campaign_id)
        return generate_hunter_lookup_csv(campaign)
    except Campaign.DoesNotExist:
        messages.error(request, "Campaign not found.")
        return HttpResponseRedirect(reverse('portal:home'))


@login_required
def export_full_excel(request, campaign_id):
    """Export comprehensive campaign data as Excel file."""
    try:
        campaign = Campaign.objects.get(id=campaign_id)
        return generate_full_export_excel(campaign)
    except Campaign.DoesNotExist:
        messages.error(request, "Campaign not found.")
        return HttpResponseRedirect(reverse('portal:home'))


@login_required
@require_POST
def refresh_zenserp_quota(request):
    """Refresh the ZenSERP quota by checking the ZenSERP API directly."""
    import logging
    from leadtrail.portal.modules.website_hunter_api import WebsiteHunterClient
    
    logger = logging.getLogger(__name__)
    
    try:
        logger.info("Checking ZenSERP API quota...")
        
        # Create WebsiteHunterClient instance (it will load API key from .env)
        client = WebsiteHunterClient()
        
        # Check API quota
        quota_data = client.check_api_quota()
        
        if not quota_data:
            logger.error("Failed to retrieve ZenSERP API quota")
            return JsonResponse({
                'success': False,
                'error': "Failed to retrieve ZenSERP API quota"
            }, status=500)
        
        # Extract available credits
        available_credits = quota_data.get('remaining_requests', 0)
        
        # Update or create quota record
        quota = ZenSERPQuota.get_current_quota()
        quota.available_credits = available_credits
        quota.save()
        
        logger.info(f"ZenSERP API quota updated: {available_credits} credits available")
        result_message = f"ZenSERP API quota updated: {available_credits} credits available"
        
        return JsonResponse({
            'success': True,
            'available_credits': quota.available_credits,
            'message': result_message
        })
        
    except Exception as e:
        logger.error(f"Error checking ZenSERP API quota: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': f"Error checking ZenSERP API quota: {str(e)}"
        }, status=500)


@login_required
@require_POST
def refresh_snov_quota(request):
    """Refresh the Snov quota by checking the Snov API directly."""
    import logging
    from leadtrail.portal.utils.snov_client import SnovClient
    
    logger = logging.getLogger(__name__)
    
    try:
        logger.info("Checking Snov API balance...")
        
        # Create Snov client instance (it will load API key from .env)
        client = SnovClient()
        
        # Check API balance
        balance_data = client.check_api_quota()
        
        if not balance_data:
            logger.error("Failed to retrieve Snov API balance")
            return JsonResponse({
                'success': False,
                'error': "Failed to retrieve Snov API balance"
            }, status=500)
        
        # Extract available credits (balance is returned as string like "25000.00")
        available_credits = balance_data.get('balance', '0.00')
        
        try:
            from decimal import Decimal
            available_credits_decimal = Decimal(str(available_credits))
        except (TypeError, ValueError):
            logger.warning(f"Could not convert balance to Decimal: {available_credits}")
            available_credits_decimal = Decimal('0.00')
        
        # Update or create quota record
        quota = SnovQuota.get_current_quota()
        quota.available_credits = available_credits_decimal
        quota.save()
        
        logger.info(f"Snov API balance updated: {available_credits} credits available")
        result_message = f"Snov API balance updated: {available_credits} credits available"
        
        return JsonResponse({
            'success': True,
            'available_credits': str(quota.available_credits),
            'message': result_message
        })
        
    except Exception as e:
        logger.error(f"Error checking Snov API balance: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': f"Error checking Snov API balance: {str(e)}"
        }, status=500)


@login_required
@require_POST
def refresh_hunter_quota(request):
    """Refresh the Hunter quota by checking the Hunter.io API directly."""
    import logging
    from leadtrail.portal.utils.hunter_client import HunterClient
    
    logger = logging.getLogger(__name__)
    
    try:
        logger.info("Checking Hunter.io API balance...")
        
        # Create Hunter client instance (it will load API key from .env)
        client = HunterClient()
        
        # Check API balance
        balance_data = client.check_api_quota()
        
        if not balance_data:
            logger.error("Failed to retrieve Hunter.io API balance")
            return JsonResponse({
                'success': False,
                'error': "Failed to retrieve Hunter.io API balance"
            }, status=500)
        
        # Extract available credits (already calculated as available - used)
        available_credits = balance_data.get('available_credits', 0.0)
        
        try:
            from decimal import Decimal
            available_credits_decimal = Decimal(str(available_credits))
        except (TypeError, ValueError):
            logger.warning(f"Could not convert balance to Decimal: {available_credits}")
            available_credits_decimal = Decimal('0.00')
        
        # Update or create quota record
        quota = HunterQuota.get_current_quota()
        quota.available_credits = available_credits_decimal
        quota.save()
        
        logger.info(f"Hunter.io API balance updated: {available_credits} credits available")
        result_message = f"Hunter.io API balance updated: {available_credits} credits available"
        
        return JsonResponse({
            'success': True,
            'available_credits': str(quota.available_credits),
            'message': result_message
        })
        
    except Exception as e:
        logger.error(f"Error checking Hunter.io API balance: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': f"Error checking Hunter.io API balance: {str(e)}"
        }, status=500)
