"""
BESCOM Bill Downloader Module
Downloads electricity bills from BESCOM portal with automatic CAPTCHA solving
"""

import base64
import re
import time
import traceback
from datetime import datetime
from typing import List, Dict, Optional

import requests
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError


class BESCOMBillDownloader:
    """BESCOM Bill Downloader with CAPTCHA solving support"""
    
    def __init__(self, username: str, password: str, capsolver_api_key: str):
        """
        Initialize BESCOM Bill Downloader
        
        Args:
            username: BESCOM account username/consumer ID
            password: BESCOM account password
            capsolver_api_key: CapSolver API key for captcha solving
        """
        self.username = username
        self.password = password
        self.capsolver_api_key = capsolver_api_key
        self.login_url = "https://bescom.co.in/bescom/login"
        self.alert_message = None

    def solve_captcha(self, page, captcha_element_xpath: str, captcha_input_xpath: str, max_retries: int = 3) -> bool:
        """
        Solve image captcha using CapSolver API
        
        Args:
            page: Playwright page object
            captcha_element_xpath: XPath for captcha image
            captcha_input_xpath: XPath for captcha input field
            max_retries: Maximum number of retry attempts
            
        Returns:
            True if captcha solved successfully, False otherwise
        """
        for attempt in range(max_retries):
            try:
                # Get captcha element
                captcha_element = page.locator(captcha_element_xpath)
                
                if not captcha_element.is_visible():
                    continue
                
                # Screenshot captcha
                image_bytes = captcha_element.screenshot()
                
                # Solve captcha using CapSolver
                captcha_text = self._ocr_captcha(image_bytes)
                
                if not captcha_text:
                    if attempt < max_retries - 1:
                        time.sleep(2)
                    continue
                
                captcha_text = re.sub(r"\s+", "", captcha_text).upper()  # BESCOM captchas are uppercase
                
                # Fill captcha
                page.locator(captcha_input_xpath).fill(captcha_text)
                
                return True
                
            except Exception as e:
                if attempt < max_retries - 1:
                    time.sleep(2)
                else:
                    raise Exception(f"Failed to solve captcha after {max_retries} attempts: {str(e)}")
        
        return False

    def _ocr_captcha(self, image_bytes: bytes) -> str:
        """
        Solve captcha using CapSolver API
        
        Args:
            image_bytes: Captcha image as bytes
            
        Returns:
            Captcha text or empty string if failed
        """
        if not self.capsolver_api_key:
            return ""
        
        try:
            # Convert image bytes to base64
            image_base64 = base64.b64encode(image_bytes).decode('utf-8')
            
            if not image_base64 or len(image_base64) < 100:
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
            
            response = requests.post(create_task_url, json=task_payload, timeout=30)
            
            if response.status_code != 200:
                return ""
            
            result = response.json()
            
            # Check for API errors
            error_id = result.get("errorId", -1)
            if error_id != 0:
                return ""
            
            # Check if solution is already in the response (fast solve)
            if result.get("status") == "ready":
                captcha_text = result.get("solution", {}).get("text", "")
                if captcha_text:
                    return captcha_text
            
            # Otherwise, get task ID and poll for result
            task_id = result.get("taskId")
            if not task_id:
                return ""
            
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
                    continue
                
                result = response.json()
                status = result.get("status", "")
                
                if status == "ready":
                    captcha_text = result.get("solution", {}).get("text", "")
                    if captcha_text:
                        return captcha_text
                    return ""
                elif status == "processing":
                    continue
                elif status == "failed":
                    return ""
            
            return ""
            
        except Exception:
            return ""

    def login(self, page) -> None:
        """
        Login to BESCOM portal
        
        Args:
            page: Playwright page object
            
        Raises:
            Exception: If login fails
        """
        page.goto(self.login_url, timeout=120000)
        page.wait_for_load_state("networkidle")
        
        page.locator('input[formcontrolname="userId"]').fill(self.username)
        page.locator('input[formcontrolname="password"]').fill(self.password)
        
        # Solve captcha
        self.solve_captcha(
            page,
            "//canvas[@id='captcha']",
            "//input[@id='cpatchaInput']"
        )
        
        # Submit login
        page.locator('button[type="submit"]').click()
        
        # Wait for login to complete
        page.wait_for_load_state("networkidle")
        time.sleep(10)
        
        # Check for login errors
        try:
            error_element = page.locator("form.ng-submitted")
            if error_element.is_visible():
                error_text = error_element.text_content()
                if "Invalid UserName and Password" in error_text:
                    raise Exception("Invalid username or password")
        except Exception as e:
            if "Invalid username or password" in str(e):
                raise e

    def download_bills_for_account(self, page, fetch_history: bool = False, bill_month: Optional[str] = None) -> List[Dict]:
        """
        Download bills for the logged-in account
        
        Args:
            page: Playwright page object
            fetch_history: Download all available bills or just latest
            bill_month: Specific bill month to download (e.g., "NOV-2024")
            
        Returns:
            List of downloaded bill dictionaries with filename and data
        """
        bills = []
        
        # Wait for dashboard to load
        page.wait_for_selector(".multiselect-dropdown", state="visible", timeout=120000)
        page.wait_for_load_state("networkidle")
        time.sleep(5)
        
        # Get available consumer IDs
        bill_ids_locator = page.locator(
            ".dropdown-list .multiselect-item-checkbox input[type='checkbox']"
        )
        
        bill_ids = [
            option.get_attribute("aria-label")
            for option in bill_ids_locator.all()
            if not option.get_attribute("disabled")
        ]
        
        # Process each consumer ID
        for bill_id in bill_ids:
            consumer_bills = self._download_bills_for_id(page, bill_id, fetch_history, bill_month)
            bills.extend(consumer_bills)
        
        return bills

    def _download_bills_for_id(self, page, bill_id: str, fetch_history: bool, bill_month: Optional[str] = None) -> List[Dict]:
        """
        Download bills for a specific consumer ID
        
        Args:
            page: Playwright page object
            bill_id: Consumer ID
            fetch_history: Download all bills or just latest
            bill_month: Specific bill month to download
            
        Returns:
            List of downloaded bill dictionaries
        """
        bills = []
        
        # Select consumer ID from dropdown
        selected = page.query_selector("span.selected-item span")
        is_selected = selected and selected.text_content().strip().startswith(str(bill_id))
        
        if not is_selected:
            multiselect_dropdown = page.locator(".multiselect-dropdown span.dropdown-btn")
            multiselect_dropdown.scroll_into_view_if_needed()
            multiselect_dropdown.click()
            
            multiselect_element = page.locator(
                f"li:has(input[type='checkbox'][aria-label='{str(bill_id)}'])"
            )
            multiselect_element.scroll_into_view_if_needed()
            multiselect_element.click()
            
            page.wait_for_load_state("networkidle")
            page.wait_for_selector("span.selected-item", state="attached")
        
        page.wait_for_load_state("networkidle")
        
        # Get available bill dates
        bill_date_options = page.query_selector_all('select[name="billDates"] option')
        
        if not bill_date_options:
            return bills
        
        # Filter bills based on parameters
        if bill_month:
            bills_to_download = []
            for option in bill_date_options:
                bill_text = option.text_content().strip()
                if bill_month.upper() in bill_text.upper():
                    bills_to_download.append(option)
            
            if not bills_to_download:
                return bills
        elif fetch_history:
            bills_to_download = bill_date_options
        else:
            bills_to_download = [bill_date_options[0]]
        
        for option in bills_to_download:
            bill_text = option.text_content().strip()
            if not bill_text:
                continue
            
            # Select bill date
            page.select_option('select[name="billDates"]', option.get_attribute("value"))
            page.wait_for_load_state("networkidle")
            
            # Download bill
            download_button = page.locator(".download-bill-history button")
            
            try:
                with page.expect_download(timeout=15000) as download_info:
                    download_button.click()
                
                download = download_info.value
                
                # Read file data
                pdf_data = download.read_all_bytes()
                
                # Generate filename
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = f"{bill_id}_{bill_text.replace('/', '_')}_{timestamp}.pdf"
                
                bills.append({
                    "filename": filename,
                    "data": pdf_data,
                    "consumer_id": bill_id,
                    "bill_month": bill_text,
                    "size": len(pdf_data)
                })
                
                page.wait_for_load_state("networkidle")
                
            except Exception:
                continue
        
        return bills
