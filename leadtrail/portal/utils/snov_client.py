"""
Snov.io API Client
==================

Simple client for interacting with the Snov.io API to check available credits.

API Documentation: https://snov.io/api
"""

from dotenv import load_dotenv
import requests
import json
import logging
import os
from dataclasses import dataclass
from typing import Dict, List, Optional

load_dotenv()

logger = logging.getLogger(__name__)


@dataclass
class SnovResult:
    """
    Result from Snov LinkedIn profile processing.
    
    Attributes:
        profile_url: LinkedIn URL that was processed
        position: Current job position/title
        emails: List of email strings with status format: ["email@company.com (valid)", ...]
        status: Processing status - SUCCESS, API_ERROR, or NOT_FOUND
    """
    profile_url: str
    position: str
    emails: List[str]
    status: str  # SUCCESS, API_ERROR, NOT_FOUND
    message: str


class SnovAuthenticationError(Exception):
    """Raised when API authentication fails."""
    pass


class SnovAPIError(Exception):
    """Raised when API returns an error."""
    pass


class SnovClient:
    """
    Simple Snov.io API client for checking account balance.
    
    Uses OAuth2 client credentials flow without caching.
    """
    
    BASE_URL = "https://api.snov.io/v1"
    
    def __init__(self):
        """Initialize the Snov client with API credentials."""
        self.client_id = os.getenv('SNOV_API_USER')
        self.client_secret =  os.getenv('SNOV_API_KEY')
        
        if not self.client_id or not self.client_secret:
            raise SnovAuthenticationError(
                "Snov API credentials not found. Please set SNOV_API_USER and SNOV_API_KEY "
                "in your environment variables or Django settings."
            )
    
    def get_access_token(self) -> str:
        """
        Get OAuth2 access token for API authentication.
        
        Returns:
            str: The access token
            
        Raises:
            SnovAuthenticationError: If authentication fails
        """
        params = {
            'grant_type': 'client_credentials',
            'client_id': self.client_id,
            'client_secret': self.client_secret
        }
        
        try:
            response = requests.post(f'{self.BASE_URL}/oauth/access_token', data=params)
            response.raise_for_status()
            
            # Handle potential encoding issues as per your example
            response_text = response.text.encode('ascii', 'ignore')
            auth_data = json.loads(response_text)
            
            access_token = auth_data.get('access_token')
            if not access_token:
                raise SnovAuthenticationError("No access token in authentication response")
            
            return access_token
            
        except requests.RequestException as e:
            logger.error(f"Failed to authenticate with Snov API: {e}")
            raise SnovAuthenticationError(f"Authentication request failed: {e}")
        except (json.JSONDecodeError, KeyError) as e:
            logger.error(f"Failed to parse Snov authentication response: {e}")
            raise SnovAuthenticationError(f"Invalid authentication response: {e}")
    
    def get_balance(self) -> Dict:
        """
        Check user balance/credits available.
        
        Uses Bearer token authentication as per your working example.
        
        Returns:
            Dict: Balance information with the following structure:
            {
                "success": true,
                "data": {
                    "balance": "1000.00",
                    "teamwork": false,
                    "unique_recipients_used": 0,
                    "limit_resets_in": 27,
                    "expires_in": 27
                }
            }
            
        Raises:
            SnovAuthenticationError: If authentication fails
            SnovAPIError: If API returns an error
        """
        try:
            # Get access token (fresh each time)
            token = self.get_access_token()
            
            # Make request with Bearer token (as per your example)
            headers = {
                'authorization': f'Bearer {token}'
            }
            
            response = requests.get(f'{self.BASE_URL}/get-balance', headers=headers)
            response.raise_for_status()
            
            # Handle potential encoding issues as per your example
            response_text = response.text.encode('ascii', 'ignore')
            data = json.loads(response_text)
            
            # Validate response structure
            if not data.get('success'):
                error_msg = data.get('error', 'Unknown API error')
                logger.error(f"Snov API returned error: {error_msg}")
                raise SnovAPIError(f"API error: {error_msg}")
            
            balance = data.get('data', {}).get('balance')
            if balance is None:
                logger.warning("No balance found in Snov API response")
                raise SnovAPIError("Invalid balance response from API")
            
            logger.info(f"Successfully retrieved Snov balance: {balance} credits")
            return data
            
        except (SnovAuthenticationError, SnovAPIError):
            # Re-raise these exceptions as-is
            raise
        except requests.RequestException as e:
            logger.error(f"Snov API request failed: {e}")
            raise SnovAPIError(f"API request failed: {e}")
        except (json.JSONDecodeError, KeyError) as e:
            logger.error(f"Failed to parse Snov API response: {e}")
            raise SnovAPIError(f"Invalid API response: {e}")
        except Exception as e:
            logger.error(f"Unexpected error checking Snov balance: {e}")
            raise SnovAPIError(f"Unexpected error: {e}")
    
    def check_api_quota(self) -> Optional[Dict]:
        """
        Check API quota/balance. Alias for get_balance() for consistency with other clients.
        
        Returns:
            Optional[Dict]: Balance information, or None if error occurred
        """
        try:
            response = self.get_balance()
            # Return just the data part for easier consumption
            return response.get('data')
        except Exception as e:
            logger.error(f"Failed to check Snov API quota: {e}")
            return None
    
    def add_url_for_search(self, linkedin_url: str) -> bool:
        """
        Add LinkedIn URL to Snov queue for processing.
        
        Args:
            linkedin_url: LinkedIn profile URL to process
            
        Returns:
            bool: True if URL was successfully queued, False otherwise
            
        Raises:
            SnovAuthenticationError: If authentication fails
            SnovAPIError: If API returns an error
        """
        try:
            # Get access token (fresh each time)
            token = self.get_access_token()
            
            # Make request with access_token parameter (as per your example)
            params = {
                'access_token': token,
                'url': linkedin_url
            }
            
            response = requests.post(f'{self.BASE_URL}/add-url-for-search', data=params)
            response.raise_for_status()
            
            logger.info(f"Successfully added LinkedIn URL to Snov queue: {linkedin_url}")
            return True
            
        except (SnovAuthenticationError, SnovAPIError):
            # Re-raise these exceptions as-is
            raise
        except requests.RequestException as e:
            logger.error(f"Snov add-url-for-search request failed: {e}")
            raise SnovAPIError(f"API request failed: {e}")
        except (json.JSONDecodeError, KeyError) as e:
            logger.error(f"Failed to parse Snov add-url-for-search response: {e}")
            raise SnovAPIError(f"Invalid API response: {e}")
        except Exception as e:
            logger.error(f"Unexpected error adding URL to Snov queue: {e}")
            raise SnovAPIError(f"Unexpected error: {e}")
    
    def get_emails_from_url(self, linkedin_url: str) -> SnovResult:
        """
        Get processed LinkedIn profile data including emails from Snov.
        
        Args:
            linkedin_url: LinkedIn profile URL to retrieve data for
            
        Returns:
            SnovResult: Structured result with profile data and processing status
        """
        try:
            # Get access token (fresh each time)
            token = self.get_access_token()
            
            # Make request with access_token parameter (as per your example)
            params = {
                'access_token': token,
                'url': linkedin_url
            }
            
            response = requests.post(f'{self.BASE_URL}/get-emails-from-url', data=params)
            response.raise_for_status()
            
            # Parse JSON response
            data = response.json()
            
            # Check if API returned success
            if not data.get('success'):
                error_msg = data.get('error', 'Unknown API error')
                logger.error(f"Snov API get-emails-from-url error: {error_msg}")
                return SnovResult(
                    profile_url=linkedin_url,
                    position="Unknown",
                    emails=[],
                    status="API_ERROR",
                    message=data.get('message', 'Unknown API error')
                )
            
            # Extract profile data
            profile_data = data.get('data', {})
            
            # Extract position from current job
            position = self._extract_position(profile_data)
            
            # Extract and format emails
            emails = self._extract_emails(profile_data)
            
            # Determine status based on email availability
            status = "SUCCESS" if len(emails) > 0 else "NOT_FOUND"
            
            logger.info(f"Successfully processed LinkedIn profile {linkedin_url}: {len(emails)} emails found")
            
            return SnovResult(
                profile_url=linkedin_url,
                position=position,
                emails=emails,
                status=status,
                message=data.get('message', 'Successfully found emails' if status == 'SUCCESS' else 'could not find emails')
            )
            
        except (SnovAuthenticationError, SnovAPIError) as e:
            # Re-raise authentication errors, but return SnovResult for API errors
            if isinstance(e, SnovAuthenticationError):
                raise
            logger.error(f"Snov API error processing {linkedin_url}: {e}")
            return SnovResult(
                profile_url=linkedin_url,
                position="Unknown",
                emails=[],
                status="API_ERROR",
                message=data.get('message', 'Error processing LinkedIn profile')
            )
        except requests.RequestException as e:
            logger.error(f"Snov get-emails-from-url request failed: {e}")
            return SnovResult(
                profile_url=linkedin_url,
                position="Unknown",
                emails=[],
                status="API_ERROR",
                message=data.get('message', 'Error processing LinkedIn profile')
            )
        except Exception as e:
            logger.error(f"Unexpected error getting emails from {linkedin_url}: {e}")
            return SnovResult(
                profile_url=linkedin_url,
                position="Unknown",
                emails=[],
                status="API_ERROR",
                message=data.get('message', 'Error processing LinkedIn profile')
            )
    
    def _extract_position(self, profile_data: Dict) -> str:
        """
        Extract job position from profile data.
        
        Args:
            profile_data: Profile data from Snov API response
            
        Returns:
            str: Current job position or "Unknown" if not found
        """
        try:
            # Try to get position from current job (most recent)
            current_jobs = profile_data.get('currentJob', [])
            if current_jobs and len(current_jobs) > 0:
                position = current_jobs[0].get('position')
                if position:
                    return position
            
            # Fallback: try previous jobs if no current job
            previous_jobs = profile_data.get('previousJob', [])
            if previous_jobs and len(previous_jobs) > 0:
                position = previous_jobs[0].get('position')
                if position:
                    return f"{position} (Previous)"
            
            logger.warning("No position found in profile data")
            return "Unknown"
            
        except Exception as e:
            logger.warning(f"Error extracting position: {e}")
            return "Unknown"
    
    def _extract_emails(self, profile_data: Dict) -> List[str]:
        """
        Extract and format email addresses from profile data.
        
        Args:
            profile_data: Profile data from Snov API response
            
        Returns:
            List[str]: Formatted email strings with status: ["email@company.com (valid)", ...]
        """
        formatted_emails = []
        
        try:
            emails_data = profile_data.get('emails', [])
            
            for email_obj in emails_data:
                if isinstance(email_obj, dict):
                    email_address = email_obj.get('email')
                    email_status = email_obj.get('status', 'unknown')
                    
                    if email_address:
                        formatted_email = f"{email_address} ({email_status})"
                        formatted_emails.append(formatted_email)
            
            logger.info(f"Extracted {len(formatted_emails)} emails from profile data")
            
        except Exception as e:
            logger.warning(f"Error extracting emails: {e}")
        
        return formatted_emails
    
    def process_linkedin_profile(self, linkedin_url: str) -> SnovResult:
        """
        High-level method to process a LinkedIn profile URL through Snov.
        
        Combines the two-step process:
        1. Add URL to Snov queue for processing
        2. Retrieve processed profile data with emails
        
        Args:
            linkedin_url: LinkedIn profile URL to process
            
        Returns:
            SnovResult: Structured result with profile data and processing status
        """
        try:
            logger.info(f"Starting LinkedIn profile processing for: {linkedin_url}")
            
            # Step 1: Add URL to Snov queue
            add_success = self.add_url_for_search(linkedin_url)
            if not add_success:
                logger.error(f"Failed to add LinkedIn URL to queue: {linkedin_url}")
                return SnovResult(
                    profile_url=linkedin_url,
                    position="Unknown",
                    emails=[],
                    status="API_ERROR"
                )
            
            # Step 2: Get processed emails and profile data
            result = self.get_emails_from_url(linkedin_url)
            
            logger.info(f"LinkedIn profile processing completed for {linkedin_url}: {result.status}")
            return result
            
        except SnovAuthenticationError:
            # Re-raise authentication errors
            raise
        except Exception as e:
            logger.error(f"Unexpected error processing LinkedIn profile {linkedin_url}: {e}")
            return SnovResult(
                profile_url=linkedin_url,
                position="Unknown",
                emails=[],
                status="API_ERROR"
            )