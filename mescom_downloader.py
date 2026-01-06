"""
MESCOM Bill Downloader - Standalone Script
Downloads electricity bills from MESCOM portal with custom credentials
Supports multiple user accounts
No captcha required - only login ID and password
"""

import os
import re
import time
import traceback
from datetime import datetime
from pathlib import Path
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError
import logging

# Configuration
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class MESCOMBillDownloader:
    def __init__(self, username: str, password: str, download_folder: str = "bills", 
                 target_ca_number: str = None):
        """
        Initialize MESCOM Bill Downloader
        
        Args:
            username: MESCOM account username/consumer ID
            password: MESCOM account password
            download_folder: Folder to save downloaded bills
            target_ca_number: Specific CA number to download (if None, downloads all available)
        """
        self.username = username
        self.password = password
        self.download_folder = Path(download_folder)
        self.download_folder.mkdir(exist_ok=True)
        self.target_ca_number = target_ca_number
        self.login_url = "https://mescom.org.in/mescom/login"
        self.pdf_data = None
        self.alert_message = None

    def login(self, page):
        """
        Login to MESCOM portal
        
        Args:
            page: Playwright page object
        """
        logger.info("Navigating to login page")
        page.goto(self.login_url, timeout=120000)
        page.wait_for_load_state("networkidle")
        
        logger.info("Filling login credentials")
        page.locator('input[formcontrolname="userId"]').fill(self.username)
        page.locator('input[formcontrolname="password"]').fill(self.password)
        
        # Submit login (no captcha required)
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
        Download bills from MESCOM portal
        
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
    
    DOWNLOAD_FOLDER = "mescom_bills"  # Folder to save bills
    FETCH_HISTORY = False  # Set to True to download all available bills
    BILL_MONTH = None  # Specify bill month (e.g., "NOV-2024") or None for latest/all
    HEADLESS = True  # Set to False to see browser window
    # ========================================
    
    if not ACCOUNTS or ACCOUNTS[0][0] == "username1":
        print("ERROR: Please update ACCOUNTS with your credentials!")
        print("Format: ACCOUNTS = [(username, password, ca_number), ...]")
        print("Example: ACCOUNTS = [('user1', 'pass1', 'CA123456789'), ('user2', 'pass2', None)]")
        return
    
    logger.info("Starting MESCOM Bill Downloader")
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
        
        downloader = MESCOMBillDownloader(
            username=username,
            password=password,
            download_folder=DOWNLOAD_FOLDER,
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