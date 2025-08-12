"""
Portal app models.
"""
from django.db import models
from django.utils.translation import gettext_lazy as _
from django.core.validators import RegexValidator

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
    def vat_lookup_progress(self):
        """Calculate progress percentage of VAT lookup."""
        total = self.company_numbers.count()
        if total == 0:
            return 0
        completed = self.company_numbers.filter(vat_lookup__isnull=False).count()
        return round((completed / total) * 100)


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
