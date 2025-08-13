"""
Portal app URL configuration.
"""
from django.urls import path

from . import views

app_name = "portal"

urlpatterns = [
    path("", views.CampaignListView.as_view(), name="home"),
    path("campaigns/create/", views.CampaignCreateView.as_view(), name="campaign_create"),
    path("website-human-review/<int:campaign_id>/", views.WebsiteHumanReviewView.as_view(), name="website_human_review"),
    path("serp-settings/", views.SERPSettingsView.as_view(), name="serp_settings"),
    path("serp-settings/delete-domain/", views.delete_domain, name="delete_domain"),
]
