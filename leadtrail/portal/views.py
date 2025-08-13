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

from .models import Campaign, CompanyNumber, SERPExcludedDomain, BlacklistDomain, ZenSERPQuota, SearchKeyword, WebsiteHuntingResult


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
        return CompanyNumber.objects.filter(
            campaign_id=campaign_id
        ).select_related(
            'house_data', 'vat_lookup', 'website_hunting_result'
        ).order_by('created_at')
    
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
        
        # Redirect back to the same page with current pagination
        campaign_id = self.kwargs.get('campaign_id')
        page = request.GET.get('page', 1)
        per_page = request.GET.get('per_page', 10)
        
        redirect_url = reverse('portal:website_human_review', kwargs={'campaign_id': campaign_id})
        return HttpResponseRedirect(f"{redirect_url}?page={page}&per_page={per_page}")
