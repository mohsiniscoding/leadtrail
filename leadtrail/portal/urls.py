"""
Portal app URL configuration.
"""
from django.urls import path

from . import views

app_name = "portal"

urlpatterns = [
    path("", views.CampaignListView.as_view(), name="home"),
    path("campaigns/create/", views.CampaignCreateView.as_view(), name="campaign_create"),
    path("how-to/", views.HowToView.as_view(), name="how_to"),
    path("campaigns/delete/<int:campaign_id>/", views.delete_campaign, name="campaign_delete"),
    path("website-human-review/<int:campaign_id>/", views.WebsiteHumanReviewView.as_view(), name="website_human_review"),
    path("serp-settings/", views.SERPSettingsView.as_view(), name="serp_settings"),
    path("serp-settings/delete-domain/", views.delete_domain, name="delete_domain"),
    path("serp-settings/domain-suggestions/", views.get_domain_suggestions, name="get_domain_suggestions"),
    path("serp-settings/add-suggested-domain/", views.add_suggested_domain, name="add_suggested_domain"),
    path("campaigns/toggle-linkedin-lookup/", views.toggle_linkedin_lookup, name="toggle_linkedin_lookup"),
    path("website-review-action/", views.website_review_action, name="website_review_action"),
    path("export/companies-house/<int:campaign_id>/", views.export_companies_house_csv, name="export_companies_house_csv"),
    path("export/vat-lookup/<int:campaign_id>/", views.export_vat_lookup_csv, name="export_vat_lookup_csv"),
    path("export/website-hunting/<int:campaign_id>/", views.export_website_hunting_csv, name="export_website_hunting_csv"),
    path("export/contact-extraction/<int:campaign_id>/", views.export_contact_extraction_csv, name="export_contact_extraction_csv"),
    path("export/linkedin-finder/<int:campaign_id>/", views.export_linkedin_finder_csv, name="export_linkedin_finder_csv"),
]
