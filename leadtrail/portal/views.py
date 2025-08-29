"""
Portal app views.
"""
import re
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import HttpResponseRedirect, JsonResponse
from django.urls import reverse
from django.utils.decorators import method_decorator
from django.views.generic import ListView, TemplateView
from django.views.decorators.http import require_POST

from .models import Campaign, CompanyNumber, SERPExcludedDomain, BlacklistDomain, ZenSERPQuota, SearchKeyword, WebsiteHuntingResult, WebsiteContactLookup, LinkedinLookup
from leadtrail.exports.companies_house_lookup import generate_companies_house_csv
from leadtrail.exports.vat_lookup import generate_vat_lookup_csv
from leadtrail.exports.website_hunting import generate_website_hunting_csv
from leadtrail.exports.contact_extraction import generate_contact_extraction_csv
from leadtrail.exports.linkedin_finder import generate_linkedin_finder_csv


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
        context = super().get_context_data(**kwargs)
        # Add ZenSERP quota to context
        context['zenserp_quota'] = ZenSERPQuota.get_current_quota()
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
        context['has_existing_campaign'] = Campaign.objects.exists()
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
        
        # Check if a campaign already exists
        if Campaign.objects.exists():
            messages.error(request, "You can have 1 campaign running at a time, this is to save resources and database calls on Heroku")
            return self.render_to_response(self.get_context_data())
            
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
                if (company.website_hunting_result and 
                    company.website_hunting_result.ranked_domains):
                    # Check if any domain has a score > 0
                    has_non_zero_score = any(
                        domain.get('score', 0) > 0 
                        for domain in company.website_hunting_result.ranked_domains
                    )
                    if has_non_zero_score:
                        filtered_companies.append(company.id)
            
            # Filter queryset by the company IDs that have non-zero scores
            queryset = queryset.filter(id__in=filtered_companies)
        
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
def toggle_linkedin_lookup(request):
    """Toggle LinkedIn lookup for a campaign."""
    try:
        campaign_id = request.POST.get('campaign_id')
        
        if not campaign_id:
            return JsonResponse({
                'error': 'Campaign ID is required'
            }, status=400)
        
        try:
            campaign = Campaign.objects.get(id=campaign_id)
        except Campaign.DoesNotExist:
            return JsonResponse({
                'error': 'Campaign not found'
            }, status=404)
        
        # Toggle LinkedIn lookup status
        campaign.linkedin_lookup_enabled = not campaign.linkedin_lookup_enabled
        campaign.save()
        
        # Return updated status and progress
        linkedin_stats = campaign.linkedin_lookup_stats
        
        return JsonResponse({
            'success': True,
            'linkedin_lookup_enabled': campaign.linkedin_lookup_enabled,
            'progress_percentage': linkedin_stats['progress_percentage'],
            'completed_lookups': linkedin_stats['completed_lookups'],
            'total_companies': linkedin_stats['total_companies'],
            'message': f"LinkedIn lookup {'enabled' if campaign.linkedin_lookup_enabled else 'disabled'} for campaign '{campaign.name}'"
        })
        
    except Exception as e:
        return JsonResponse({
            'error': f"Error toggling LinkedIn lookup: {str(e)}"
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
def export_website_hunting_csv(request, campaign_id):
    """Export Website Hunting data as CSV."""
    try:
        campaign = Campaign.objects.get(id=campaign_id)
        return generate_website_hunting_csv(campaign)
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
