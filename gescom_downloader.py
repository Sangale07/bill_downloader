"""
GESCOM Bill Downloader - Standalone Script
Downloads electricity bills from GESCOM portal with custom credentials
Supports multiple user accounts
"""

import os
import re
import time
import traceback
import base64
import requests
from datetime import datetime
from pathlib import Path
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError
import logging

# Configuration
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class GESCOMBillDownloader:
    def __init__(self, username: str, password: str, download_folder: str = "bills", 
                 capsolver_api_key: str = None, target_ca_number: str = None):
        """
        Initialize GESCOM Bill Downloader
        
        Args:
            username: GESCOM account username/consumer ID
            password: GESCOM account password
            download_folder: Folder to save downloaded bills
            capsolver_api_key: CapSolver API key for captcha solving
            target_ca_number: Specific CA number to download (if None, downloads all available)
        """
        self.username = username
        self.password = password
        self.download_folder = Path(download_folder)
        self.download_folder.mkdir(exist_ok=True)
        self.capsolver_api_key = capsolver_api_key
        self.target_ca_number = target_ca_number
        self.login_url = "https://www.gescomglb.org/gescom/login"
        self.pdf_data = None
        self.alert_message = None

    def solve_captcha(self, page, captcha_element_xpath, captcha_input_xpath, max_retries=3):
        """
        Solve image captcha using CapSolver API
        
        Args:
            page: Playwright page object
            captcha_element_xpath: XPath for captcha image
            captcha_input_xpath: XPath for captcha input field
            max_retries: Maximum number of retry attempts
        """
        for attempt in range(max_retries):
            try:
                logger.info(f"Captcha attempt {attempt + 1}/{max_retries}")
                
                # Get captcha element
                captcha_element = page.locator(captcha_element_xpath)
                if not captcha_element.is_visible():
                    logger.error("Captcha element not visible")
                    continue
                
                # Screenshot captcha
                image_bytes = captcha_element.screenshot()
                
                # Solve using CapSolver
                captcha_text = self._ocr_captcha(image_bytes)
                captcha_text = re.sub(r"\s+", "", captcha_text).upper()
                logger.info(f"Detected captcha: {captcha_text}")
                
                # Fill captcha
                page.locator(captcha_input_xpath).clear()
                page.locator(captcha_input_xpath).fill(captcha_text)
                
                return True
                
            except Exception as e:
                logger.error(f"Captcha attempt {attempt + 1} failed: {str(e)}")
                if attempt < max_retries - 1:
                    time.sleep(2)
                else:
                    raise Exception("Failed to solve captcha after all attempts")
        
        return False

    def _ocr_captcha(self, image_bytes):
        """
        Solve captcha using CapSolver API
        
        Args:
            image_bytes: Captcha image as bytes
            
        Returns:
            Captcha text or empty string if failed
        """
        if not self.capsolver_api_key:
            logger.error("CapSolver API key not provided")
            return ""
        
        try:
            logger.info("🔍 Solving captcha with CapSolver...")
            
            # Convert image bytes to base64
            image_base64 = base64.b64encode(image_bytes).decode('utf-8')
            
            # Validate base64 image
            if not image_base64 or len(image_base64) < 100:
                logger.error(f"✗ Invalid captcha image (too short: {len(image_base64)} chars)")
                return ""
            
            # Create task
            create_task_url = "https://api.capsolver.com/createTask"
            task_payload = {
                "clientKey": self.capsolver_api_key,
                "task": {
                    "type": "ImageToTextTask",
                    "body": image_base64,
                    "module": "common",
                    "score": 0.5,
                    "case": False
                }
            }
            
            logger.info(f"📤 Sending captcha to CapSolver (image size: {len(image_base64)} chars)")
            response = requests.post(create_task_url, json=task_payload, timeout=30)
            
            # Check HTTP status
            if response.status_code != 200:
                logger.error(f"✗ CapSolver HTTP error: {response.status_code}")
                logger.error(f"Response: {response.text[:200]}")
                return ""
            
            result = response.json()
            logger.info(f"📥 CapSolver response: {result}")
            
            # Check for API errors
            error_id = result.get("errorId", -1)
            if error_id != 0:
                error_msg = result.get('errorDescription', 'Unknown error')
                error_code = result.get('errorCode', 'N/A')
                logger.error(f"✗ CapSolver error (ID: {error_id}, Code: {error_code}): {error_msg}")
                
                # Provide helpful hints for common errors
                if "insufficient balance" in error_msg.lower() or "balance" in error_msg.lower():
                    logger.info("💡 Hint: Check your CapSolver account balance at https://dashboard.capsolver.com/")
                elif "invalid" in error_msg.lower() and "key" in error_msg.lower():
                    logger.info("💡 Hint: Verify your CapSolver API key is correct")
                
                return ""
            
            # Check if solution is already in the response (fast solve)
            if result.get("status") == "ready":
                captcha_text = result.get("solution", {}).get("text", "")
                if captcha_text:
                    logger.info(f"✓ Captcha solved immediately: '{captcha_text}'")
                    return captcha_text
                else:
                    logger.error(f"✗ No text in immediate solution: {result}")
                    return ""
            
            # Otherwise, get task ID and poll for result
            task_id = result.get("taskId")
            if not task_id:
                logger.error("✗ No task ID received from CapSolver")
                return ""
            
            logger.info(f"⏳ Task ID: {task_id}, waiting for solution...")
            
            # Poll for result
            get_result_url = "https://api.capsolver.com/getTaskResult"
            for attempt in range(30):  # Try for up to 30 seconds
                time.sleep(1)
                
                result_payload = {
                    "clientKey": self.capsolver_api_key,
                    "taskId": task_id
                }
                
                response = requests.post(get_result_url, json=result_payload, timeout=30)
                
                if response.status_code != 200:
                    logger.error(f"✗ CapSolver result HTTP error: {response.status_code}")
                    continue
                
                result = response.json()
                status = result.get("status", "")
                
                if status == "ready":
                    captcha_text = result.get("solution", {}).get("text", "")
                    if captcha_text:
                        logger.info(f"✓ Captcha solved: '{captcha_text}'")
                        return captcha_text
                    else:
                        logger.error(f"✗ No text in solution: {result}")
                        return ""
                elif status == "processing":
                    if attempt % 5 == 0:
                        logger.info(f"⏳ Still processing... (attempt {attempt}/30)")
                    continue
                elif status == "failed":
                    error_desc = result.get('errorDescription', 'Unknown')
                    logger.error(f"✗ CapSolver task failed: {error_desc}")
                    return ""
                else:
                    logger.error(f"✗ Unknown CapSolver status: {status}, full response: {result}")
            
            logger.error("✗ Captcha solving timeout after 30 seconds")
            return ""
            
        except requests.exceptions.Timeout:
            logger.error("✗ CapSolver API timeout - network issue or service is slow")
            return ""
        except requests.exceptions.RequestException as e:
            logger.error(f"✗ CapSolver network error: {str(e)[:200]}")
            return ""
        except Exception as e:
            logger.error(f"✗ Captcha solving error: {str(e)[:200]}")
            logger.error(f"Traceback: {traceback.format_exc()[:300]}")
            return ""

    def login(self, page):
        """
        Login to GESCOM portal
        
        Args:
            page: Playwright page object
        """
        logger.info("Navigating to login page")
        page.goto(self.login_url, timeout=120000)
        page.wait_for_load_state("networkidle")
        
        logger.info("Filling login credentials")
        page.locator('input[formcontrolname="userId"]').fill(self.username)
        page.locator('input[formcontrolname="password"]').fill(self.password)
        
        # Solve captcha
        logger.info("Attempting to solve captcha")
        self.solve_captcha(
            page,
            "//canvas[@id='captcha']",
            "//input[@id='cpatchaInput']"
        )
        
        # Submit login
        logger.info("Submitting login form")
        page.locator('button[type="submit"]').click()
        
        # Wait for login to complete
        page.wait_for_load_state("networkidle")
        time.sleep(10)  # Additional wait for page to stabilize
        
        # Check for login errors
        error_element = page.locator("form.ng-submitted")
        if error_element.is_visible():
            error_text = error_element.text_content()
            if "Invalid UserName and Password" in error_text:
                raise Exception("Login failed: Invalid username or password")
        
        logger.info("Login successful")

    def download_bills(self, headless=False, fetch_history=False, bill_month=None):
        """
        Download bills from GESCOM portal
        
        Args:
            headless: Run browser in headless mode
            fetch_history: Download all available bills or just latest
            bill_month: Specific bill month to download (e.g., "NOV-2024")
        """
        with sync_playwright() as p:
            try:
                logger.info("Launching browser")
                browser = p.chromium.launch(
                    headless=headless,
                    timeout=120000,
                    args=[
                        "--ignore-ssl-errors=yes",
                        "--ignore-certificate-errors",
                    ]
                )
                
                context = browser.new_context(ignore_https_errors=True)
                page = context.new_page()
                
                # Setup dialog handler for alerts
                page.on("dialog", lambda dialog: (
                    setattr(self, "alert_message", dialog.message()),
                    dialog.dismiss()
                ))
                
                # Login
                self.login(page)
                
                # Wait for dashboard to load
                logger.info("Waiting for dashboard")
                page.wait_for_selector(".multiselect-dropdown", state="visible", timeout=120000)
                page.wait_for_load_state("networkidle")
                time.sleep(5)
                
                # Get available consumer IDs
                logger.info("Fetching available consumer IDs")
                bill_ids_locator = page.locator(".dropdown-list .multiselect-item-checkbox input[type='checkbox']")
                bill_ids = [
                    option.get_attribute("aria-label")
                    for option in bill_ids_locator.all()
                    if not option.get_attribute("disabled")
                ]
                
                logger.info(f"Found consumer IDs: {bill_ids}")
                
                # Filter consumer IDs if target CA number is specified
                if self.target_ca_number:
                    logger.info(f"Looking for specific CA number: {self.target_ca_number}")
                    matching_ids = [bid for bid in bill_ids if self.target_ca_number in str(bid)]
                    if not matching_ids:
                        logger.warning(f"CA number '{self.target_ca_number}' not found in available consumer IDs: {bill_ids}")
                        return
                    bill_ids = matching_ids
                    logger.info(f"Found matching CA number(s): {bill_ids}")
                
                # Process each consumer ID
                for bill_id in bill_ids:
                    logger.info(f"Processing consumer ID: {bill_id}")
                    self._download_bills_for_id(page, bill_id, fetch_history, bill_month)
                
                browser.close()
                logger.info("Download complete!")
                
            except Exception as e:
                logger.error(f"Error during download: {traceback.format_exc()}")
                browser.close()
                raise e

    def _download_bills_for_id(self, page, bill_id, fetch_history, bill_month=None):
        """
        Download bills for a specific consumer ID
        
        Args:
            page: Playwright page object
            bill_id: Consumer ID
            fetch_history: Download all bills or just latest
            bill_month: Specific bill month to download
        """
        # Select consumer ID from dropdown
        selected = page.query_selector("span.selected-item span")
        is_selected = selected.text_content().strip().startswith(str(bill_id))
        
        if not is_selected:
            multiselect_dropdown = page.locator(".multiselect-dropdown span.dropdown-btn")
            multiselect_dropdown.scroll_into_view_if_needed()
            multiselect_dropdown.click()
            
            multiselect_element = page.locator(f"li:has(input[type='checkbox'][aria-label='{str(bill_id)}'])")
            multiselect_element.scroll_into_view_if_needed()
            multiselect_element.click()
            
            page.wait_for_load_state("networkidle")
            page.wait_for_selector("span.selected-item", state="attached")
            page.wait_for_load_state("networkidle")
        
        # Get available bill dates
        bill_date_options = page.query_selector_all('select[name="billDates"] option')
        
        # Check if any bills are available
        if not bill_date_options:
            logger.warning(f"No bills available for consumer ID: {bill_id}")
            return
        
        # Filter bills based on parameters
        if bill_month:
            # Search for specific month
            logger.info(f"Looking for bill month: {bill_month}")
            bills_to_download = []
            for option in bill_date_options:
                bill_text = option.text_content().strip()
                if bill_month.upper() in bill_text.upper():
                    bills_to_download.append(option)
                    logger.info(f"Found matching bill: {bill_text}")
            
            if not bills_to_download:
                logger.warning(f"No bill found for month '{bill_month}' for consumer ID: {bill_id}")
                logger.info(f"Available bills: {[opt.text_content().strip() for opt in bill_date_options]}")
                return
        elif fetch_history:
            bills_to_download = bill_date_options
        else:
            bills_to_download = [bill_date_options[0]]
        
        for option in bills_to_download:
            bill_text = option.text_content().strip()
            if not bill_text:
                continue
            
            logger.info(f"Downloading bill for: {bill_text}")
            
            # Select bill date
            page.select_option('select[name="billDates"]', option.get_attribute("value"))
            page.wait_for_load_state("networkidle")
            
            # Download bill
            download_button = page.locator(".download-bill-history button")
            with page.expect_download(timeout=15000) as download_info:
                download_button.click()
            
            download = download_info.value
            
            # Save file
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"{bill_id}_{bill_text.replace('/', '_')}_{timestamp}.pdf"
            filepath = self.download_folder / filename
            download.save_as(filepath)
            
            logger.info(f"Saved bill to: {filepath}")
            page.wait_for_load_state("networkidle")


def main():
    """Main function - Configure your credentials here"""
    
    # ============= CONFIGURATION =============
    # Add accounts with CA numbers in format: [(username, password, ca_number), ...]
    # If ca_number is None, downloads all available CA numbers for that login
    ACCOUNTS = [
        ("username1", "password1", "CA123456789"),  # Specific CA number
        ("username2", "password2", None),           # All CA numbers for this login
        # Add more accounts as needed
    ]
    
    CAPSOLVER_API_KEY = "CAP-ADCA94D1B80ACF6A5A0E9E57B4E90158"  # Your CapSolver API key
    DOWNLOAD_FOLDER = "gescom_bills"  # Folder to save bills
    FETCH_HISTORY = False  # Set to True to download all available bills
    BILL_MONTH = None  # Specify bill month (e.g., "NOV-2024") or None for latest/all
    HEADLESS = True  # Set to False to see browser window
    # ========================================
    
    if not CAPSOLVER_API_KEY or CAPSOLVER_API_KEY == "your_capsolver_api_key":
        print("ERROR: Please update CAPSOLVER_API_KEY in the script!")
        return
    
    if not ACCOUNTS or ACCOUNTS[0][0] == "username1":
        print("ERROR: Please update ACCOUNTS with your credentials!")
        print("Format: ACCOUNTS = [(username, password, ca_number), ...]")
        print("Example: ACCOUNTS = [('user1', 'pass1', 'CA123456789'), ('user2', 'pass2', None)]")
        return
    
    logger.info("Starting GESCOM Bill Downloader")
    logger.info(f"Number of accounts: {len(ACCOUNTS)}")
    logger.info(f"Download folder: {DOWNLOAD_FOLDER}")
    if BILL_MONTH:
        logger.info(f"Target bill month: {BILL_MONTH}")
    
    # Process each account
    for idx, account_info in enumerate(ACCOUNTS, 1):
        if len(account_info) == 3:
            username, password, ca_number = account_info
        else:
            username, password = account_info
            ca_number = None
        
        logger.info(f"\n{'='*60}")
        logger.info(f"Processing Account {idx}/{len(ACCOUNTS)}: {username}")
        if ca_number:
            logger.info(f"Target CA Number: {ca_number}")
        else:
            logger.info("Target CA Number: All available")
        logger.info(f"{'='*60}")
        
        downloader = GESCOMBillDownloader(
            username=username,
            password=password,
            download_folder=DOWNLOAD_FOLDER,
            capsolver_api_key=CAPSOLVER_API_KEY,
            target_ca_number=ca_number
        )
        
        try:
            downloader.download_bills(
                headless=HEADLESS,
                fetch_history=FETCH_HISTORY,
                bill_month=BILL_MONTH
            )
            
            ca_info = f" - CA: {ca_number}" if ca_number else " - All CAs"
            print(f"\n✓ Account {idx} ({username}{ca_info}): Bills downloaded successfully!")
            
        except Exception as e:
            ca_info = f" - CA: {ca_number}" if ca_number else " - All CAs"
            print(f"\n✗ Account {idx} ({username}{ca_info}): Error - {str(e)}")
            logger.error(f"Failed to download bills for {username} (CA: {ca_number}): {traceback.format_exc()}")
            continue
    
    print(f"\n{'='*60}")
    print(f"All accounts processed! Bills saved to '{DOWNLOAD_FOLDER}' folder")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()