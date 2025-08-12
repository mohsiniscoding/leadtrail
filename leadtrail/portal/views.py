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

from .models import Campaign, CompanyNumber, SERPExcludedDomain, BlacklistDomain, ZenSERPQuota, SearchKeyword


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
