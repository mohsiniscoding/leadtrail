"""
Portal app models.
"""
from django.db import models
from django.utils.translation import gettext_lazy as _
from django.core.validators import RegexValidator
from collections import Counter
from typing import List, Tuple, Optional, Dict, Any

from .modules.companies_house_api_search import CompanySearchStatus
from .modules.vat_lookup import VATSearchStatus

# Convert enum to choices for Django model
COMPANY_SEARCH_STATUS_CHOICES = [(status.value, status.value) for status in CompanySearchStatus]
VAT_SEARCH_STATUS_CHOICES = [(status.value, status.value) for status in VATSearchStatus]

# Domain validator
domain_validator = RegexValidator(
    regex=r'^([a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?\.)+[a-zA-Z]{2,}$',
    message=_("Enter a valid domain name (e.g., example.com)"),
    code='invalid_domain'
)


class Campaign(models.Model):
    """
    Campaign model for managing marketing campaigns.
    """
    name = models.CharField(
        _("Name"),
        max_length=255,
        help_text=_("The name of the campaign")
    )
    created_at = models.DateTimeField(
        _("Created at"),
        auto_now_add=True,
        help_text=_("When the campaign was created")
    )
    updated_at = models.DateTimeField(
        _("Updated at"),
        auto_now=True,
        help_text=_("When the campaign was last updated")
    )

    class Meta:
        verbose_name = _("Campaign")
        verbose_name_plural = _("Campaigns")
        ordering = ["-created_at"]

    def __str__(self) -> str:
        """String representation of the campaign."""
        return self.name

    @property
    def house_data_progress(self):
        """Calculate progress percentage of Companies House data lookup."""
        total = self.company_numbers.count()
        if total == 0:
            return 0
        completed = self.company_numbers.filter(house_data__isnull=False).count()
        return round((completed / total) * 100)

    @property
    def house_data_stats(self):
        """Get Companies House lookup statistics for display."""
        total = self.company_numbers.count()
        completed = self.company_numbers.filter(house_data__isnull=False).count()
        
        if completed == 0:
            success_rate = 0
        else:
            successful = self.company_numbers.filter(
                house_data__isnull=False,
                house_data__status='SUCCESS'
            ).count()
            success_rate = round((successful / completed) * 100)
        
        return {
            'total_companies': total,
            'completed_lookups': completed,
            'successful_lookups': self.company_numbers.filter(
                house_data__isnull=False,
                house_data__status='SUCCESS'
            ).count(),
            'success_rate': success_rate,
            'progress_percentage': self.house_data_progress
        }

    @property
    def vat_lookup_progress(self):
        """Calculate progress percentage of VAT lookup."""
        total = self.company_numbers.count()
        if total == 0:
            return 0
        completed = self.company_numbers.filter(vat_lookup__isnull=False).count()
        return round((completed / total) * 100)

    @property
    def vat_lookup_stats(self):
        """Get VAT lookup statistics for display."""
        total = self.company_numbers.count()
        completed = self.company_numbers.filter(vat_lookup__isnull=False).count()
        
        if completed == 0:
            success_rate = 0
        else:
            successful = self.company_numbers.filter(
                vat_lookup__isnull=False,
                vat_lookup__status='SUCCESS'
            ).count()
            success_rate = round((successful / completed) * 100)
        
        return {
            'total_companies': total,
            'completed_lookups': completed,
            'successful_lookups': self.company_numbers.filter(
                vat_lookup__isnull=False,
                vat_lookup__status='SUCCESS'
            ).count(),
            'success_rate': success_rate,
            'progress_percentage': self.vat_lookup_progress
        }

    @property
    def website_hunting_progress(self):
        """Calculate progress percentage of Website Hunting."""
        total = self.company_numbers.count()
        if total == 0:
            return 0
        completed = self.company_numbers.filter(website_hunting_result__isnull=False).count()
        return round((completed / total) * 100)

    @property
    def website_hunting_stats(self):
        """Get Website Hunting statistics with score breakdown for display."""
        
        total = self.company_numbers.count()
        completed = self.company_numbers.filter(website_hunting_result__isnull=False).count()
        
        # Count approved domains (human-approved)
        approved_domains = self.company_numbers.filter(
            website_hunting_result__approved_domain__isnull=False,
            website_hunting_result__approved_by_human=True
        ).count()
        
        # Initialize score counters
        no_score_count = 0  # No websites found or all websites have 0 score
        score_2_count = 0   # Companies with 2 score websites
        score_1_5_count = 0 # Companies with 1.5 score websites  
        score_1_count = 0   # Companies with 1 score websites
        score_0_75_count = 0 # Companies with 0.75 score websites
        
        # Process each company's website hunting results
        for company in self.company_numbers.filter(website_hunting_result__isnull=False).select_related('website_hunting_result'):
            hunting_result = company.website_hunting_result
            ranked_domains = hunting_result.ranked_domains or []
            
            if not ranked_domains:
                no_score_count += 1
                continue
            
            # Get the highest score from all ranked domains
            max_score = 0
            for domain_result in ranked_domains:
                if isinstance(domain_result, dict) and 'score' in domain_result:
                    try:
                        score = float(domain_result['score'])
                        max_score = max(max_score, score)
                    except (ValueError, TypeError):
                        continue
            
            # Categorize based on highest score found
            if max_score == 0:
                no_score_count += 1
            elif max_score >= 2.0:
                score_2_count += 1
            elif max_score >= 1.5:
                score_1_5_count += 1
            elif max_score >= 1.0:
                score_1_count += 1
            elif max_score >= 0.75:
                score_0_75_count += 1
            else:
                no_score_count += 1
        
        # Calculate percentages and non-zero total
        non_zero_count = score_2_count + score_1_5_count + score_1_count + score_0_75_count
        
        if completed > 0:
            no_score_pct = round((no_score_count / completed) * 100)
            score_2_pct = round((score_2_count / completed) * 100)
            score_1_5_pct = round((score_1_5_count / completed) * 100)
            score_1_pct = round((score_1_count / completed) * 100)
            score_0_75_pct = round((score_0_75_count / completed) * 100)
            non_zero_pct = round((non_zero_count / completed) * 100)
        else:
            no_score_pct = score_2_pct = score_1_5_pct = score_1_pct = score_0_75_pct = non_zero_pct = 0
        
        return {
            'total_companies': total,
            'completed_lookups': completed,
            'approved_domains': approved_domains,
            'progress_percentage': self.website_hunting_progress,
            'score_breakdown': {
                'no_score': {'count': no_score_count, 'percentage': no_score_pct},
                'non_zero': {'count': non_zero_count, 'percentage': non_zero_pct},
                'score_2': {'count': score_2_count, 'percentage': score_2_pct},
                'score_1_5': {'count': score_1_5_count, 'percentage': score_1_5_pct},
                'score_1': {'count': score_1_count, 'percentage': score_1_pct},
                'score_0_75': {'count': score_0_75_count, 'percentage': score_0_75_pct},
            }
        }

    @property
    def website_contact_lookup_progress(self):
        """Calculate progress percentage of Website Contact Lookup for approved domains."""
        # Count companies with approved domains (human-approved)
        approved_domains = self.company_numbers.filter(
            website_hunting_result__approved_domain__isnull=False,
            website_hunting_result__approved_by_human=True
        ).count()
        
        if approved_domains == 0:
            return 0
        
        # Count companies with contact lookup completed
        completed = self.company_numbers.filter(
            website_hunting_result__approved_domain__isnull=False,
            website_hunting_result__approved_by_human=True,
            website_contact_lookup__isnull=False
        ).count()
        
        return round((completed / approved_domains) * 100)

    @property
    def website_contact_lookup_stats(self):
        """Get website contact lookup statistics with contact type breakdown for display."""
        approved_domains = self.company_numbers.filter(
            website_hunting_result__approved_domain__isnull=False,
            website_hunting_result__approved_by_human=True
        ).count()
        
        completed = self.company_numbers.filter(
            website_hunting_result__approved_domain__isnull=False,
            website_hunting_result__approved_by_human=True,
            website_contact_lookup__isnull=False
        ).count()
        
        # Initialize contact type counters
        email_found_count = 0
        phone_found_count = 0
        linkedin_found_count = 0
        
        # Process each company's contact lookup results
        for company in self.company_numbers.filter(
            website_hunting_result__approved_domain__isnull=False,
            website_hunting_result__approved_by_human=True,
            website_contact_lookup__isnull=False
        ).select_related('website_contact_lookup'):
            
            contact_lookup = company.website_contact_lookup
            
            # Check for email addresses
            if contact_lookup.email_addresses and len(contact_lookup.email_addresses) > 0:
                email_found_count += 1
            
            # Check for phone numbers
            if contact_lookup.phone_numbers and len(contact_lookup.phone_numbers) > 0:
                phone_found_count += 1
            
            # Check for LinkedIn in social media links
            if contact_lookup.social_media_links:
                linkedin_links = contact_lookup.social_media_links.get('linkedin', [])
                if isinstance(linkedin_links, list) and len(linkedin_links) > 0:
                    linkedin_found_count += 1
                elif isinstance(linkedin_links, str) and linkedin_links.strip():
                    linkedin_found_count += 1
        
        # Calculate percentages
        if completed > 0:
            email_found_pct = round((email_found_count / completed) * 100)
            phone_found_pct = round((phone_found_count / completed) * 100)
            linkedin_found_pct = round((linkedin_found_count / completed) * 100)
        else:
            email_found_pct = phone_found_pct = linkedin_found_pct = 0
        
        return {
            'approved_domains': approved_domains,
            'completed_lookups': completed,
            'progress_percentage': self.website_contact_lookup_progress,
            'contact_breakdown': {
                'email_found': {'count': email_found_count, 'percentage': email_found_pct},
                'phone_found': {'count': phone_found_count, 'percentage': phone_found_pct},
                'linkedin_found': {'count': linkedin_found_count, 'percentage': linkedin_found_pct},
            }
        }

    @property
    def linkedin_lookup_progress(self):
        """Calculate progress percentage of LinkedIn Lookup."""
        total = self.company_numbers.count()
        if total == 0:
            return 0
        
        completed = self.company_numbers.filter(linkedin_lookup__isnull=False).count()
        return round((completed / total) * 100)

    @property
    def linkedin_lookup_stats(self):
        """Get LinkedIn lookup statistics with profile type breakdown for display."""
        total = self.company_numbers.count()
        completed = self.company_numbers.filter(linkedin_lookup__isnull=False).count()
        
        # Initialize profile type counters
        employee_found_count = 0
        company_found_count = 0
        overall_success_count = 0
        
        # Process each company's LinkedIn lookup results
        for company in self.company_numbers.filter(linkedin_lookup__isnull=False).select_related('linkedin_lookup'):
            linkedin_lookup = company.linkedin_lookup
            
            has_employee = False
            has_company = False
            
            # Check for employee profiles
            if linkedin_lookup.employee_urls and len(linkedin_lookup.employee_urls) > 0:
                employee_found_count += 1
                has_employee = True
            
            # Check for company profiles
            if linkedin_lookup.company_urls and len(linkedin_lookup.company_urls) > 0:
                company_found_count += 1
                has_company = True
            
            # Count overall success (either employee or company profiles found)
            if has_employee or has_company:
                overall_success_count += 1
        
        # Calculate percentages
        if completed > 0:
            employee_found_pct = round((employee_found_count / completed) * 100)
            company_found_pct = round((company_found_count / completed) * 100)
            overall_success_pct = round((overall_success_count / completed) * 100)
        else:
            employee_found_pct = company_found_pct = overall_success_pct = 0
        
        return {
            'total_companies': total,
            'completed_lookups': completed,
            'progress_percentage': self.linkedin_lookup_progress,
            'profile_breakdown': {
                'employee_found': {'count': employee_found_count, 'percentage': employee_found_pct},
                'company_found': {'count': company_found_count, 'percentage': company_found_pct},
                'overall_success': {'count': overall_success_count, 'percentage': overall_success_pct},
            }
        }

    @property
    def linkedin_employee_review_progress(self):
        """Calculate progress percentage of LinkedIn Employee Review."""
        # Companies eligible for review: have linkedin lookup
        eligible_companies = self.company_numbers.filter(
            linkedin_lookup__isnull=False
        ).count()
        
        if eligible_companies == 0:
            return 0
        
        # Companies that have been reviewed
        reviewed_companies = self.company_numbers.filter(
            linkedin_employee_review__isnull=False
        ).count()
        
        return round((reviewed_companies / eligible_companies) * 100)

    @property
    def linkedin_employee_review_stats(self):
        """Get LinkedIn employee review statistics with breakdown for display."""
        # Count eligible companies (have both contact extraction and linkedin lookup)
        eligible_companies = self.company_numbers.filter(
            website_contact_lookup__isnull=False,
            linkedin_lookup__isnull=False
        ).count()
        
        # Count reviewed companies
        reviewed_companies = self.company_numbers.filter(
            linkedin_employee_review__isnull=False
        ).count()
        
        # Initialize URL counters
        total_approved = 0
        companies_with_approvals = 0
        
        # Process each reviewed company's data
        for company in self.company_numbers.filter(
            linkedin_employee_review__isnull=False
        ).select_related('linkedin_employee_review'):
            
            employee_review = company.linkedin_employee_review
            total_approved += employee_review.total_approved
            
            if employee_review.has_approved_employees:
                companies_with_approvals += 1
        
        # Calculate percentages
        if reviewed_companies > 0:
            approval_rate = round((companies_with_approvals / reviewed_companies) * 100)
        else:
            approval_rate = 0
        
        return {
            'eligible_companies': eligible_companies,
            'reviewed_companies': reviewed_companies,
            'total_approved': total_approved,
            'companies_with_approvals': companies_with_approvals,
            'approval_rate': approval_rate,
            'progress_percentage': self.linkedin_employee_review_progress
        }
    
    @property
    def companies_with_approved_employees(self):
        """
        Count companies that have approved employee URLs from any source
        (either through website contact extraction or LinkedIn discovery).
        """
        return self.company_numbers.filter(
            linkedin_employee_review__isnull=False
        ).count()

    @property
    def snov_lookup_progress(self):
        """Calculate progress percentage of Snov.io Email Extraction."""
        # Companies eligible for Snov lookup: have approved LinkedIn employee profiles
        eligible_companies = self.company_numbers.filter(
            linkedin_employee_review__isnull=False
        )
        
        # Filter companies that have approved employee URLs (done in Python since JSONField filtering can be tricky)
        eligible_count = 0
        for company in eligible_companies:
            if company.linkedin_employee_review.approved_employee_urls:
                eligible_count += 1
        
        if eligible_count == 0:
            return 0
        
        # Companies that have had Snov lookup completed
        completed_companies = self.company_numbers.filter(
            snov_lookup__isnull=False
        ).count()
        
        return round((completed_companies / eligible_count) * 100)

    @property
    def snov_lookup_stats(self):
        """Get Snov.io lookup statistics with breakdown for display."""
        # Companies eligible for Snov lookup: have approved LinkedIn employee profiles
        eligible_companies = self.company_numbers.filter(
            linkedin_employee_review__isnull=False
        )
        
        # Filter companies that have approved employee URLs (done in Python since JSONField filtering can be tricky)
        total_eligible = 0
        for company in eligible_companies:
            if company.linkedin_employee_review.approved_employee_urls:
                total_eligible += 1
        
        # Companies with completed Snov lookups
        completed_lookups = self.company_numbers.filter(
            snov_lookup__isnull=False
        ).select_related('snov_lookup')
        
        # Calculate statistics
        total_completed = completed_lookups.count()
        
        # Email extraction statistics
        successful_extractions = 0
        total_emails_found = 0
        total_profiles_processed = 0
        
        for company in completed_lookups:
            snov_lookup = company.snov_lookup
            if snov_lookup.has_emails:
                successful_extractions += 1
            total_emails_found += snov_lookup.total_emails_found
            total_profiles_processed += snov_lookup.profiles_processed_count
        
        # Calculate percentages
        success_rate = round((successful_extractions / total_completed * 100)) if total_completed > 0 else 0
        
        # Email breakdown
        emails_found_count = sum(1 for company in completed_lookups if company.snov_lookup.has_emails)
        emails_found_percentage = round((emails_found_count / total_completed * 100)) if total_completed > 0 else 0
        
        # Processing status breakdown
        success_count = sum(1 for company in completed_lookups if company.snov_lookup.is_success)
        success_percentage = round((success_count / total_completed * 100)) if total_completed > 0 else 0
        
        return {
            'total_eligible': total_eligible,
            'completed_lookups': total_completed,
            'success_rate': success_rate,
            'total_emails_found': total_emails_found,
            'total_profiles_processed': total_profiles_processed,
            'progress_percentage': self.snov_lookup_progress,
            'email_breakdown': {
                'emails_found': {
                    'count': emails_found_count,
                    'percentage': emails_found_percentage
                },
                'success_status': {
                    'count': success_count,
                    'percentage': success_percentage
                }
            }
        }

    @property
    def hunter_lookup_progress(self):
        """Calculate progress percentage of Hunter.io Domain Search."""
        # Companies eligible for Hunter lookup: have approved domains
        approved_domains_count = self.company_numbers.filter(
            website_hunting_result__approved_domain__isnull=False,
            website_hunting_result__approved_by_human=True
        ).count()
        
        if approved_domains_count == 0:
            return 0
        
        # Companies that have had Hunter lookup completed
        completed_companies = self.company_numbers.filter(
            hunter_lookup__isnull=False
        ).count()
        
        return round((completed_companies / approved_domains_count) * 100)

    @property
    def hunter_lookup_stats(self):
        """Get Hunter.io lookup statistics with breakdown for display."""
        # Companies with approved domains (eligible for Hunter lookup)
        approved_domains_count = self.company_numbers.filter(
            website_hunting_result__approved_domain__isnull=False,
            website_hunting_result__approved_by_human=True
        ).count()
        
        # Companies with completed Hunter lookups
        completed_lookups = self.company_numbers.filter(
            hunter_lookup__isnull=False
        ).select_related('hunter_lookup')
        
        # Calculate statistics
        total_completed = completed_lookups.count()
        
        # Email extraction statistics
        successful_extractions = 0
        total_emails_found = 0
        
        for company in completed_lookups:
            hunter_lookup = company.hunter_lookup
            if hunter_lookup.has_emails:
                successful_extractions += 1
            total_emails_found += hunter_lookup.total_emails_found
        
        # Calculate percentages
        success_rate = round((successful_extractions / total_completed * 100)) if total_completed > 0 else 0
        
        # Email breakdown
        emails_found_count = sum(1 for company in completed_lookups if company.hunter_lookup.has_emails)
        emails_found_percentage = round((emails_found_count / total_completed * 100)) if total_completed > 0 else 0
        
        # Processing status breakdown
        success_count = sum(1 for company in completed_lookups if company.hunter_lookup.is_success)
        success_percentage = round((success_count / total_completed * 100)) if total_completed > 0 else 0
        
        return {
            'approved_domains': approved_domains_count,
            'completed_lookups': total_completed,
            'success_rate': success_rate,
            'total_emails_found': total_emails_found,
            'progress_percentage': self.hunter_lookup_progress,
            'email_breakdown': {
                'emails_found': {
                    'count': emails_found_count,
                    'percentage': emails_found_percentage
                },
                'success_status': {
                    'count': success_count,
                    'percentage': success_percentage
                }
            }
        }


class CompanyNumber(models.Model):
    """
    Company number associated with a campaign.
    """
    company_number = models.CharField(
        _("Company Number"),
        max_length=20,
        help_text=_("The company registration number")
    )
    campaign = models.ForeignKey(
        Campaign,
        on_delete=models.CASCADE,
        related_name="company_numbers",
        help_text=_("The campaign this company number belongs to")
    )
    created_at = models.DateTimeField(
        _("Created at"),
        auto_now_add=True,
        help_text=_("When the company number was added")
    )

    class Meta:
        verbose_name = _("Company Number")
        verbose_name_plural = _("Company Numbers")
        ordering = ["company_number"]

    def __str__(self) -> str:
        """String representation of the company number."""
        return f"{self.company_number} ({self.campaign.name})"


class CompanyHouseData(models.Model):
    """
    Detailed information about a company retrieved from Companies House API.
    """
    company_number = models.OneToOneField(
        CompanyNumber,
        on_delete=models.CASCADE,
        related_name="house_data",
        help_text=_("The company number this detail belongs to")
    )
    company_name = models.CharField(
        _("Company Name"),
        max_length=255,
        null=True,
        blank=True
    )
    company_status = models.CharField(
        _("Company Status"),
        max_length=100,
        null=True,
        blank=True
    )
    company_type = models.CharField(
        _("Company Type"),
        max_length=100,
        null=True,
        blank=True
    )
    incorporation_date = models.CharField(
        _("Incorporation Date"),
        max_length=20,
        null=True,
        blank=True
    )
    jurisdiction = models.CharField(
        _("Jurisdiction"),
        max_length=100,
        null=True,
        blank=True
    )
    registered_office_address = models.TextField(
        _("Registered Office Address"),
        null=True,
        blank=True
    )
    address_line_1 = models.CharField(
        _("Address Line 1"),
        max_length=255,
        null=True,
        blank=True
    )
    address_line_2 = models.CharField(
        _("Address Line 2"),
        max_length=255,
        null=True,
        blank=True
    )
    locality = models.CharField(
        _("Locality"),
        max_length=255,
        null=True,
        blank=True
    )
    region = models.CharField(
        _("Region"),
        max_length=255,
        null=True,
        blank=True
    )
    postal_code = models.CharField(
        _("Postal Code"),
        max_length=20,
        null=True,
        blank=True
    )
    country = models.CharField(
        _("Country"),
        max_length=100,
        null=True,
        blank=True
    )
    registered_office_is_in_dispute = models.CharField(
        _("Registered Office Is In Dispute"),
        max_length=200,
        null=True,
        blank=True
    )
    undeliverable_registered_office_address = models.CharField(
        _("Undeliverable Registered Office Address"),
        max_length=200,
        null=True,
        blank=True
    )
    sic_codes = models.TextField(
        _("SIC Codes"),
        null=True,
        blank=True
    )
    can_file = models.CharField(
        _("Can File"),
        max_length=200,
        null=True,
        blank=True
    )
    has_been_liquidated = models.CharField(
        _("Has Been Liquidated"),
        max_length=200,
        null=True,
        blank=True
    )
    has_charges = models.CharField(
        _("Has Charges"),
        max_length=200,
        null=True,
        blank=True
    )
    has_insolvency_history = models.CharField(
        _("Has Insolvency History"),
        max_length=200,
        null=True,
        blank=True
    )
    previous_company_names = models.TextField(
        _("Previous Company Names"),
        null=True,
        blank=True
    )
    last_accounts_date = models.CharField(
        _("Last Accounts Date"),
        max_length=20,
        null=True,
        blank=True
    )
    last_accounts_period_start = models.CharField(
        _("Last Accounts Period Start"),
        max_length=20,
        null=True,
        blank=True
    )
    last_accounts_period_end = models.CharField(
        _("Last Accounts Period End"),
        max_length=20,
        null=True,
        blank=True
    )
    last_accounts_type = models.CharField(
        _("Last Accounts Type"),
        max_length=100,
        null=True,
        blank=True
    )
    next_accounts_due = models.CharField(
        _("Next Accounts Due"),
        max_length=20,
        null=True,
        blank=True
    )
    next_accounts_period_end = models.CharField(
        _("Next Accounts Period End"),
        max_length=20,
        null=True,
        blank=True
    )
    accounts_overdue = models.CharField(
        _("Accounts Overdue"),
        max_length=200,
        null=True,
        blank=True
    )
    accounting_reference_date = models.CharField(
        _("Accounting Reference Date"),
        max_length=20,
        null=True,
        blank=True
    )
    confirmation_statement_date = models.CharField(
        _("Confirmation Statement Date"),
        max_length=20,
        null=True,
        blank=True
    )
    confirmation_statement_next_due = models.CharField(
        _("Confirmation Statement Next Due"),
        max_length=20,
        null=True,
        blank=True
    )
    confirmation_statement_overdue = models.CharField(
        _("Confirmation Statement Overdue"),
        max_length=200,
        null=True,
        blank=True
    )
    officers_total_count = models.CharField(
        _("Officers Total Count"),
        max_length=200,
        null=True,
        blank=True
    )
    officers_active_count = models.CharField(
        _("Officers Active Count"),
        max_length=200,
        null=True,
        blank=True
    )
    officers_resigned_count = models.CharField(
        _("Officers Resigned Count"),
        max_length=200,
        null=True,
        blank=True
    )
    officers_inactive_count = models.CharField(
        _("Officers Inactive Count"),
        max_length=200,
        null=True,
        blank=True
    )
    key_officers = models.TextField(
        _("Key Officers"),
        null=True,
        blank=True
    )
    last_full_members_list_date = models.CharField(
        _("Last Full Members List Date"),
        max_length=20,
        null=True,
        blank=True
    )
    created_at = models.DateTimeField(
        _("Created at"),
        auto_now_add=True
    )
    error_message = models.TextField(
        _("Error Message"),
        null=True,
        blank=True
    )
    status = models.CharField(
        _("Status"),
        max_length=30,
        choices=COMPANY_SEARCH_STATUS_CHOICES,
        default=CompanySearchStatus.SUCCESS.value
    )

    class Meta:
        verbose_name = _("Company House Data")
        verbose_name_plural = _("Company House Data")
        ordering = ["-created_at"]

    def __str__(self) -> str:
        """String representation of the company house data."""
        name = self.company_name or "Unknown"
        return f"{name} ({self.company_number.company_number})"


class VATLookup(models.Model):
    """
    VAT Lookup data retrieved from VAT lookup service.
    """
    company_number = models.OneToOneField(
        CompanyNumber,
        on_delete=models.CASCADE,
        related_name="vat_lookup",
        help_text=_("The company number this VAT data belongs to")
    )
    vat_number = models.CharField(
        _("VAT Number"),
        max_length=20,
        null=True,
        blank=True
    )
    company_name = models.CharField(
        _("Company Name"),
        max_length=255,
        null=True,
        blank=True
    )
    search_terms = models.TextField(
        _("Search Terms"),
        null=True,
        blank=True,
        help_text=_("Search terms that were tried")
    )
    status = models.CharField(
        _("Status"),
        max_length=30,
        choices=VAT_SEARCH_STATUS_CHOICES,
        default=VATSearchStatus.SUCCESS.value
    )
    processing_notes = models.TextField(
        _("Processing Notes"),
        null=True,
        blank=True
    )
    proxy_used = models.CharField(
        _("Proxy Used"),
        max_length=100,
        null=True,
        blank=True
    )
    created_at = models.DateTimeField(
        _("Created at"),
        auto_now_add=True
    )

    class Meta:
        verbose_name = _("VAT Lookup")
        verbose_name_plural = _("VAT Lookups")
        ordering = ["-created_at"]

    def __str__(self) -> str:
        """String representation of the VAT lookup."""
        if self.vat_number:
            return f"{self.vat_number} ({self.company_number.company_number})"
        return f"No VAT - {self.company_number.company_number}"


class SERPExcludedDomain(models.Model):
    """
    Domains to exclude from SERP results.
    These domains will be added to SERP query as "-site:domain1 -site:domain2" etc.
    """
    domain = models.CharField(
        _("Domain"),
        max_length=255,
        unique=True,
        validators=[domain_validator],
        help_text=_("Domain to exclude from SERP results (e.g., example.com)")
    )
    created_at = models.DateTimeField(
        _("Created at"),
        auto_now_add=True
    )

    class Meta:
        verbose_name = _("SERP Excluded Domain")
        verbose_name_plural = _("SERP Excluded Domains")
        ordering = ["domain"]

    def __str__(self) -> str:
        """String representation of the SERP excluded domain."""
        return self.domain


class BlacklistDomain(models.Model):
    """
    Domains to blacklist from website crawling.
    These domains will be filtered out before crawling.
    """
    domain = models.CharField(
        _("Domain"),
        max_length=255,
        unique=True,
        validators=[domain_validator],
        help_text=_("Domain to blacklist from website crawling (e.g., example.com)")
    )
    created_at = models.DateTimeField(
        _("Created at"),
        auto_now_add=True
    )

    class Meta:
        verbose_name = _("Blacklist Domain")
        verbose_name_plural = _("Blacklist Domains")
        ordering = ["domain"]

    def __str__(self) -> str:
        """String representation of the blacklist domain."""
        return self.domain


class ZenSERPQuota(models.Model):
    """
    Tracks the available ZenSERP API quota.
    """
    available_credits = models.PositiveIntegerField(
        _("Available Credits"),
        default=0,
        help_text=_("Number of available ZenSERP API credits")
    )
    last_updated = models.DateTimeField(
        _("Last Updated"),
        auto_now=True,
        help_text=_("When the quota was last updated")
    )

    class Meta:
        verbose_name = _("ZenSERP Quota")
        verbose_name_plural = _("ZenSERP Quota")

    def __str__(self) -> str:
        """String representation of the ZenSERP quota."""
        return f"ZenSERP Credits: {self.available_credits}"
    
    @classmethod
    def get_current_quota(cls):
        """
        Get the current ZenSERP quota.
        If no record exists, create one with 0 credits.
        """
        quota, created = cls.objects.get_or_create(
            pk=1,
            defaults={'available_credits': 0}
        )
        return quota


class SnovQuota(models.Model):
    """
    Tracks the available Snov.io API quota/balance.
    """
    available_credits = models.DecimalField(
        _("Available Credits"),
        max_digits=12,
        decimal_places=2,
        default=0.00,
        help_text=_("Number of available Snov.io API credits")
    )
    last_updated = models.DateTimeField(
        _("Last Updated"),
        auto_now=True,
        help_text=_("When the quota was last updated")
    )

    class Meta:
        verbose_name = _("Snov Quota")
        verbose_name_plural = _("Snov Quota")

    def __str__(self) -> str:
        """String representation of the Snov quota."""
        return f"Snov Credits: {self.available_credits}"
    
    @classmethod
    def get_current_quota(cls):
        """
        Get the current Snov quota.
        If no record exists, create one with 0 credits.
        """
        quota, created = cls.objects.get_or_create(
            pk=1,
            defaults={'available_credits': 0.00}
        )
        return quota


class HunterQuota(models.Model):
    """
    Tracks the available Hunter.io API quota/balance.
    """
    available_credits = models.DecimalField(
        _("Available Credits"),
        max_digits=12,
        decimal_places=2,
        default=0.00,
        help_text=_("Number of available Hunter.io API credits (available - used)")
    )
    last_updated = models.DateTimeField(
        _("Last Updated"),
        auto_now=True,
        help_text=_("When the quota was last updated")
    )

    class Meta:
        verbose_name = _("Hunter Quota")
        verbose_name_plural = _("Hunter Quota")

    def __str__(self) -> str:
        """String representation of the Hunter quota."""
        return f"Hunter Credits: {self.available_credits}"
    
    @classmethod
    def get_current_quota(cls):
        """
        Get the current Hunter quota.
        If no record exists, create one with 0 credits.
        """
        quota, created = cls.objects.get_or_create(
            pk=1,
            defaults={'available_credits': 0.00}
        )
        return quota


class SearchKeyword(models.Model):
    """
    Keywords used for SERP searches when looking for company websites.
    These keywords help identify relevant pages on company websites.
    """
    keyword = models.CharField(
        _("Search Keyword"),
        max_length=255,
        unique=True,
        help_text=_("Keyword to search for on company websites (e.g., 'privacy policy')")
    )
    created_at = models.DateTimeField(
        _("Created at"),
        auto_now_add=True
    )

    class Meta:
        verbose_name = _("Search Keyword")
        verbose_name_plural = _("Search Keywords")
        ordering = ["keyword"]

    def __str__(self) -> str:
        """String representation of the search keyword."""
        return self.keyword


class WebsiteHuntingResult(models.Model):
    """
    Results from website hunting process including SERP discovery and crawler ranking.
    Stores both the domains found via SERP and their rankings from the crawler.
    """
    company_number = models.OneToOneField(
        CompanyNumber,
        on_delete=models.CASCADE,
        related_name="website_hunting_result",
        help_text=_("The company number this website hunting result belongs to")
    )
    domains_found = models.JSONField(
        _("Domains Found"),
        default=list,
        help_text=_("List of domains found via SERP search")
    )
    ranked_domains = models.JSONField(
        _("Ranked Domains"),
        default=list,
        help_text=_("List of domains ranked by crawler with scores")
    )
    serp_status = models.CharField(
        _("SERP Status"),
        max_length=50,
        help_text=_("Status of SERP search phase")
    )
    crawl_status = models.CharField(
        _("Crawl Status"),
        max_length=50,
        help_text=_("Status of website crawling phase")
    )
    processing_notes = models.TextField(
        _("Processing Notes"),
        help_text=_("Notes about the website hunting process")
    )
    approved_domain = models.CharField(
        _("Approved Domain"),
        max_length=255,
        null=True,
        blank=True,
        help_text=_("The domain approved by human review")
    )
    approved_by_human = models.BooleanField(
        _("Approved by Human"),
        default=False,
        help_text=_("Whether the results have been approved by human review")
    )
    created_at = models.DateTimeField(
        _("Created at"),
        auto_now_add=True
    )

    class Meta:
        verbose_name = _("Website Hunting Result")
        verbose_name_plural = _("Website Hunting Results")
        ordering = ["-created_at"]

    def __str__(self) -> str:
        """String representation of the website hunting result."""
        domain_count = len(self.domains_found) if self.domains_found else 0
        return f"Website hunting for {self.company_number.company_number} ({domain_count} domains found)"

    @classmethod
    def get_domain_suggestions(cls, limit: int = 20) -> List[Tuple[str, int]]:
        """
        Get most frequently found domains that are not already blacklisted.
        
        Returns:
            List of tuples: [(domain, frequency), ...]
        """
        from django.db import connection
        
        # Get already blacklisted domains
        blacklisted_domains = set(BlacklistDomain.objects.values_list('domain', flat=True))
        
        # Get all domains from WebsiteHuntingResult records
        domain_counter: Counter[str] = Counter()
        
        # Use PostgreSQL-compatible raw SQL for better performance with JSON field
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT domains_found 
                FROM portal_websitehuntingresult 
                WHERE domains_found IS NOT NULL 
                AND domains_found != '[]'
            """)
            
            for row in cursor.fetchall():
                domains_json = row[0]
                # Parse JSON string to Python list if needed
                if isinstance(domains_json, str):
                    import json
                    try:
                        domains_list = json.loads(domains_json)
                    except json.JSONDecodeError:
                        continue
                elif isinstance(domains_json, list):
                    domains_list = domains_json
                else:
                    continue
                    
                if domains_list:
                    for domain in domains_list:
                        if domain and isinstance(domain, str):
                            # Skip already blacklisted domains
                            if domain not in blacklisted_domains:
                                domain_counter[domain] += 1
        
        # Return top domains with their frequencies
        return domain_counter.most_common(limit)


class WebsiteContactLookup(models.Model):
    """
    Website contact information lookup results.
    Stores contact information extracted from approved domains.
    """
    company_number = models.OneToOneField(
        CompanyNumber,
        on_delete=models.CASCADE,
        related_name="website_contact_lookup",
        help_text=_("The company number this contact lookup belongs to")
    )
    domain_searched = models.CharField(
        _("Domain Searched"),
        max_length=255,
        help_text=_("The domain that was searched for contact information")
    )
    phone_numbers = models.JSONField(
        _("Phone Numbers"),
        default=list,
        help_text=_("List of phone numbers found on the website")
    )
    email_addresses = models.JSONField(
        _("Email Addresses"),
        default=list,
        help_text=_("List of email addresses found on the website")
    )
    social_media_links = models.JSONField(
        _("Social Media Links"),
        default=dict,
        help_text=_("Social media links found (Facebook, Instagram, LinkedIn)")
    )
    status = models.CharField(
        _("Status"),
        max_length=50,
        help_text=_("Status of the contact extraction process")
    )
    processing_notes = models.TextField(
        _("Processing Notes"),
        help_text=_("Notes about the contact extraction process")
    )
    pages_crawled = models.PositiveIntegerField(
        _("Pages Crawled"),
        default=0,
        help_text=_("Number of pages crawled during extraction")
    )
    created_at = models.DateTimeField(
        _("Created at"),
        auto_now_add=True
    )

    class Meta:
        verbose_name = _("Website Contact Lookup")
        verbose_name_plural = _("Website Contact Lookups")
        ordering = ["-created_at"]

    def __str__(self) -> str:
        """String representation of the website contact lookup."""
        contact_count = len(self.phone_numbers) + len(self.email_addresses) + sum(
            len(links) for links in self.social_media_links.values() if isinstance(links, list)
        )
        return f"Contact lookup for {self.company_number.company_number} ({contact_count} contacts found)"

    @property
    def total_contacts_found(self) -> int:
        """Get total number of contact items found."""
        total = len(self.phone_numbers) + len(self.email_addresses)
        for links in self.social_media_links.values():
            if isinstance(links, list):
                total += len(links)
        return total

    @property
    def has_contact_info(self) -> bool:
        """Check if any contact information was found."""
        return self.total_contacts_found > 0


class LinkedinLookup(models.Model):
    """
    LinkedIn lookup results for company and employee profiles.
    Stores LinkedIn URLs found via SERP API searches.
    """
    company_number = models.OneToOneField(
        CompanyNumber,
        on_delete=models.CASCADE,
        related_name="linkedin_lookup",
        help_text=_("The company number this LinkedIn lookup belongs to")
    )
    company_urls = models.JSONField(
        _("Company URLs"),
        default=list,
        help_text=_("List of LinkedIn company profile URLs found")
    )
    employee_urls = models.JSONField(
        _("Employee URLs"),
        default=list,
        help_text=_("List of LinkedIn employee profile URLs found")
    )
    search_query = models.TextField(
        _("Search Query"),
        help_text=_("The query used for LinkedIn search")
    )
    search_status = models.CharField(
        _("Search Status"),
        max_length=50,
        help_text=_("Status of the LinkedIn search process")
    )
    processing_notes = models.TextField(
        _("Processing Notes"),
        help_text=_("Notes about the LinkedIn search process")
    )
    total_results_found = models.PositiveIntegerField(
        _("Total Results Found"),
        default=0,
        help_text=_("Total number of LinkedIn profiles found")
    )
    approved_domain_used = models.CharField(
        _("Approved Domain Used"),
        max_length=255,
        null=True,
        blank=True,
        help_text=_("The approved domain that was used for enhanced search")
    )
    created_at = models.DateTimeField(
        _("Created at"),
        auto_now_add=True
    )

    class Meta:
        verbose_name = _("LinkedIn Lookup")
        verbose_name_plural = _("LinkedIn Lookups")
        ordering = ["-created_at"]

    def __str__(self) -> str:
        """String representation of the LinkedIn lookup."""
        return f"LinkedIn lookup for {self.company_number.company_number} ({self.total_linkedin_profiles} profiles found)"

    @property
    def total_linkedin_profiles(self) -> int:
        """Get total number of LinkedIn profiles found."""
        return len(self.company_urls) + len(self.employee_urls)

    @property
    def has_linkedin_profiles(self) -> bool:
        """Check if any LinkedIn profiles were found."""
        return self.total_linkedin_profiles > 0

    @property
    def best_company_profile(self) -> Optional[Dict[str, Any]]:
        """Get the highest-scoring company profile."""
        if not self.company_urls:
            return None
        return max(self.company_urls, key=lambda x: x.get('score', 0))

    @property
    def is_success(self) -> bool:
        """Check if the LinkedIn search was successful."""
        return self.search_status in ['SUCCESS', 'PARTIAL_SUCCESS']


class LinkedinEmployeeReview(models.Model):
    """
    LinkedIn employee review results for approved employee profiles.
    Consolidates LinkedIn employee URLs from both website contact extraction and LinkedIn profile discovery.
    """
    company_number = models.OneToOneField(
        CompanyNumber,
        on_delete=models.CASCADE,
        related_name="linkedin_employee_review",
        help_text=_("The company number this LinkedIn employee review belongs to")
    )
    approved_employee_urls = models.JSONField(
        _("Approved Employee URLs"),
        default=list,
        help_text=_("List of approved LinkedIn employee profile URLs with metadata")
    )
    reviewed_at = models.DateTimeField(
        _("Reviewed At"),
        auto_now_add=True,
        help_text=_("When the review was completed")
    )

    class Meta:
        verbose_name = _("LinkedIn Employee Review")
        verbose_name_plural = _("LinkedIn Employee Reviews")
        ordering = ["-reviewed_at"]

    def __str__(self) -> str:
        """String representation of the LinkedIn employee review."""
        return f"Employee review for {self.company_number.company_number} ({len(self.approved_employee_urls)} approved)"

    @property
    def total_approved(self) -> int:
        """Get total number of approved employee URLs."""
        return len(self.approved_employee_urls)

    @property
    def has_approved_employees(self) -> bool:
        """Check if any employee URLs were approved."""
        return self.total_approved > 0

    @property
    def is_completed(self) -> bool:
        """Check if the review process is completed."""
        return True  # If the record exists, it means review was completed


class SnovLookup(models.Model):
    """
    Snov.io email extraction lookup results.
    Stores email information extracted from approved LinkedIn employee profiles.
    """
    company_number = models.OneToOneField(
        CompanyNumber,
        on_delete=models.CASCADE,
        related_name="snov_lookup",
        help_text=_("The company number this Snov lookup belongs to")
    )
    linkedin_profiles_processed = models.JSONField(
        _("LinkedIn Profiles Processed"),
        default=list,
        help_text=_("List of LinkedIn profile URLs that were processed through Snov.io")
    )
    emails_found = models.JSONField(
        _("Emails Found"),
        default=list,
        help_text=_("List of email addresses found with their status and associated profiles")
    )
    processing_status = models.CharField(
        _("Processing Status"),
        max_length=50,
        choices=[
            ('SUCCESS', _('Success')),
            ('PARTIAL_SUCCESS', _('Partial Success')),
            ('NO_EMAILS_FOUND', _('No Emails Found')),
            ('API_ERROR', _('API Error')),
            ('PROCESSING_ERROR', _('Processing Error')),
        ],
        default='SUCCESS',
        help_text=_("Overall status of the Snov.io processing")
    )
    processing_notes = models.TextField(
        _("Processing Notes"),
        blank=True,
        help_text=_("Additional notes about the processing, including any errors or warnings")
    )
    profiles_processed_count = models.PositiveIntegerField(
        _("Profiles Processed Count"),
        default=0,
        help_text=_("Number of LinkedIn profiles successfully processed")
    )
    total_emails_found = models.PositiveIntegerField(
        _("Total Emails Found"),
        default=0,
        help_text=_("Total number of email addresses found across all profiles")
    )
    processed_at = models.DateTimeField(
        _("Processed At"),
        auto_now_add=True,
        help_text=_("When the Snov.io processing was completed")
    )
    updated_at = models.DateTimeField(
        _("Updated At"),
        auto_now=True,
        help_text=_("When the record was last updated")
    )

    class Meta:
        verbose_name = _("Snov Lookup")
        verbose_name_plural = _("Snov Lookups")
        ordering = ["-processed_at"]

    def __str__(self) -> str:
        """String representation of the Snov lookup."""
        return f"Snov lookup for {self.company_number.company_number} ({self.total_emails_found} emails found)"

    @property
    def has_emails(self) -> bool:
        """Check if any emails were found."""
        return self.total_emails_found > 0

    @property
    def is_success(self) -> bool:
        """Check if the Snov processing was successful."""
        return self.processing_status in ['SUCCESS', 'PARTIAL_SUCCESS']


class HunterLookup(models.Model):
    """
    Hunter.io domain search lookup results.
    Stores email information extracted from approved domains using Hunter.io API.
    """
    company_number = models.OneToOneField(
        CompanyNumber,
        on_delete=models.CASCADE,
        related_name="hunter_lookup",
        help_text=_("The company number this Hunter lookup belongs to")
    )
    domain_searched = models.CharField(
        _("Domain Searched"),
        max_length=255,
        help_text=_("The approved domain that was searched")
    )
    emails_found = models.JSONField(
        _("Emails Found"),
        default=list,
        help_text=_("List of email addresses found with their details")
    )
    processing_status = models.CharField(
        _("Processing Status"),
        max_length=50,
        choices=[
            ('SUCCESS', _('Success')),
            ('NO_EMAILS_FOUND', _('No Emails Found')),
            ('API_ERROR', _('API Error')),
            ('PROCESSING_ERROR', _('Processing Error')),
        ],
        default='SUCCESS',
        help_text=_("Overall status of the Hunter.io processing")
    )
    processing_notes = models.TextField(
        _("Processing Notes"),
        blank=True,
        help_text=_("Additional notes about the processing, including any errors or warnings")
    )
    total_emails_found = models.PositiveIntegerField(
        _("Total Emails Found"),
        default=0,
        help_text=_("Total number of email addresses found for this domain")
    )
    processed_at = models.DateTimeField(
        _("Processed At"),
        auto_now_add=True,
        help_text=_("When the Hunter.io processing was completed")
    )
    updated_at = models.DateTimeField(
        _("Updated At"),
        auto_now=True,
        help_text=_("When the record was last updated")
    )

    class Meta:
        verbose_name = _("Hunter Lookup")
        verbose_name_plural = _("Hunter Lookups")
        ordering = ["-processed_at"]

    def __str__(self) -> str:
        """String representation of the Hunter lookup."""
        return f"Hunter lookup for {self.company_number.company_number} - {self.domain_searched} ({self.total_emails_found} emails found)"

    @property
    def has_emails(self) -> bool:
        """Check if any emails were found."""
        return self.total_emails_found > 0

    @property
    def is_success(self) -> bool:
        """Check if the Hunter processing was successful."""
        return self.processing_status == 'SUCCESS'
