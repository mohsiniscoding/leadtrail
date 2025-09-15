"""
Hunter.io API Client
===================

Simple client for interacting with the Hunter.io API to check available credits.

API Documentation: https://hunter.io/api/docs#account
"""

from dotenv import load_dotenv
import requests
import json
import logging
import os
from typing import Dict, Optional
from decimal import Decimal

load_dotenv()

logger = logging.getLogger(__name__)


class HunterAuthenticationError(Exception):
    """Raised when API authentication fails."""
    pass


class HunterAPIError(Exception):
    """Raised when API returns an error."""
    pass


class HunterClient:
    """
    Simple Hunter.io API client for checking account balance.
    
    Uses API key authentication for accessing account information.
    """
    
    BASE_URL = "https://api.hunter.io/v2"
    
    def __init__(self):
        """Initialize the Hunter client with API credentials."""
        self.api_key = os.getenv('HUNTER_API_KEY')
        logger.info(f"Hunter API key: {self.api_key[:5]}...")
        
        if not self.api_key:
            raise HunterAuthenticationError(
                "Hunter API key not found. Please set HUNTER_API_KEY "
                "in your environment variables or Django settings."
            )
    
    def get_account_info(self) -> Dict:
        """
        Get account information including credits usage.
        
        Returns:
            Dict: Account information with the following structure:
            {
                "data": {
                    "first_name": "John",
                    "last_name": "Doe", 
                    "email": "john@example.com",
                    "plan_name": "Free",
                    "plan_level": 0,
                    "reset_date": "2025-09-12",
                    "team_id": 123456,
                    "calls": {
                        "used": 20,
                        "available": 75
                    },
                    "requests": {
                        "searches": {
                            "used": 20,
                            "available": 25
                        },
                        "verifications": {
                            "used": 20,
                            "available": 50
                        },
                        "credits": {
                            "used": 2.0,
                            "available": 50.0
                        }
                    }
                }
            }
            
        Raises:
            HunterAuthenticationError: If authentication fails
            HunterAPIError: If API returns an error
        """
        try:
            # Make request with API key parameter
            params = {
                'api_key': self.api_key
            }
            
            response = requests.get(f'{self.BASE_URL}/account', params=params)
            response.raise_for_status()
            
            # Parse JSON response
            data = response.json()
            
            # Validate response structure
            if 'data' not in data:
                error_msg = data.get('errors', [{}])[0].get('details', 'Unknown API error')
                logger.error(f"Hunter API returned error: {error_msg}")
                raise HunterAPIError(f"API error: {error_msg}")
            
            logger.info("Successfully retrieved Hunter account information")
            return data
            
        except requests.RequestException as e:
            logger.error(f"Hunter API request failed: {e}")
            raise HunterAPIError(f"API request failed: {e}")
        except (json.JSONDecodeError, KeyError) as e:
            logger.error(f"Failed to parse Hunter API response: {e}")
            raise HunterAPIError(f"Invalid API response: {e}")
        except Exception as e:
            logger.error(f"Unexpected error checking Hunter account: {e}")
            raise HunterAPIError(f"Unexpected error: {e}")
    
    def check_api_quota(self) -> Optional[Dict]:
        """
        Check API quota/credits. Alias for get_account_info() for consistency with other clients.
        
        Returns:
            Optional[Dict]: Credits information with available_credits calculated, or None if error occurred
            Example:
            {
                "available_credits": 48.0,  # calculated as available - used
                "total_available": 50.0,
                "total_used": 2.0,
                "plan_name": "Free",
                "reset_date": "2025-09-12"
            }
        """
        try:
            account_data = self.get_account_info()
            
            # Extract credits information
            requests_data = account_data.get('data', {}).get('requests', {})
            credits_data = requests_data.get('credits', {})
            
            if not credits_data:
                logger.warning("No credits data found in Hunter API response")
                return None
            
            # Calculate available credits (available - used)
            total_available = Decimal(str(credits_data.get('available', 0)))
            total_used = Decimal(str(credits_data.get('used', 0)))
            available_credits = total_available - total_used
            
            # Extract additional account info
            account_info = account_data.get('data', {})
            
            result = {
                'available_credits': float(available_credits),
                'total_available': float(total_available),
                'total_used': float(total_used),
                'plan_name': account_info.get('plan_name', 'Unknown'),
                'reset_date': account_info.get('reset_date', 'Unknown')
            }
            
            logger.info(f"Successfully calculated Hunter credits: {available_credits} available")
            return result
            
        except Exception as e:
            logger.error(f"Failed to check Hunter API quota: {e}")
            return None

    def domain_search(self, domain: str) -> Dict:
        """
        Search for email addresses on a domain using Hunter.io domain search API.
        
        Args:
            domain: The domain to search for emails (e.g., 'stripe.com')
        
        Returns:
            Dict: Simple result with emails and status
            {
                "emails": [
                    {
                        "email": "john@example.com",
                        "first_name": "John",
                        "last_name": "Doe",
                        "position": "Software Engineer",
                        "confidence": 95
                    }
                ],
                "status": "SUCCESS" | "NO_EMAILS_FOUND" | "API_ERROR"
            }
        
        Raises:
            HunterAuthenticationError: If authentication fails
            HunterAPIError: If API returns an error
        """
        try:
            # Make request with API key parameter
            params = {
                'domain': domain,
                'api_key': self.api_key
            }
            
            response = requests.get(f'{self.BASE_URL}/domain-search', params=params)
            response.raise_for_status()
            
            # Parse JSON response
            data = response.json()
            
            # Check for API errors
            if 'errors' in data:
                error_msg = data.get('errors', [{}])[0].get('details', 'Unknown API error')
                logger.error(f"Hunter API returned error for domain {domain}: {error_msg}")
                return {
                    "emails": [],
                    "status": "API_ERROR"
                }
            
            # Extract emails from response
            emails_found = []
            domain_data = data.get('data', {})
            raw_emails = domain_data.get('emails', [])
            
            for email_data in raw_emails:
                if isinstance(email_data, dict) and email_data.get('value'):
                    email_obj = {
                        "email": email_data.get('value', ''),
                        "first_name": email_data.get('first_name', ''),
                        "last_name": email_data.get('last_name', ''),
                        "position": email_data.get('position', ''),
                        "confidence": email_data.get('confidence', 0)
                    }
                    emails_found.append(email_obj)
            
            # Determine status
            if emails_found:
                status = "SUCCESS"
                logger.info(f"Successfully found {len(emails_found)} emails for domain {domain}")
            else:
                status = "NO_EMAILS_FOUND"
                logger.info(f"No emails found for domain {domain}")
            
            return {
                "emails": emails_found,
                "status": status
            }
            
        except requests.RequestException as e:
            logger.error(f"Hunter API request failed for domain {domain}: {e}")
            return {
                "emails": [],
                "status": "API_ERROR"
            }
        except (json.JSONDecodeError, KeyError) as e:
            logger.error(f"Failed to parse Hunter API response for domain {domain}: {e}")
            return {
                "emails": [],
                "status": "API_ERROR"
            }
        except Exception as e:
            logger.error(f"Unexpected error during Hunter domain search for {domain}: {e}")
            return {
                "emails": [],
                "status": "API_ERROR"
            }