# # app.py
# # --------------------------------------------------------------------
# # Flask backend for multi-board bill downloader.
# #
# # Install once:
# #   pip install flask flask-cors requests playwright beautifulsoup4 pycryptodome
# #   playwright install chromium
# #
# # Run:
# #   python app.py
# # Then open the frontend (index.html) in your browser or visit http://localhost:5000/ if you serve it here.
# # --------------------------------------------------------------------

# import base64
# import io
# import json
# import re
# import threading
# import time
# import uuid
# import zipfile
# from datetime import datetime
# from typing import Optional, Dict

# import requests
# from flask import Flask, request, jsonify, send_file
# from flask_cors import CORS

# # Optional deps for MSEDCL (we check inside functions)
# try:
#     from bs4 import BeautifulSoup
# except Exception:
#     BeautifulSoup = None

# try:
#     from Crypto.Cipher import AES
# except Exception:
#     AES = None

# app = Flask(__name__)
# CORS(app)

# downloads: Dict[str, dict] = {}


# def _log(session_id: str, msg: str):
#     try:
#         downloads[session_id]["logs"].append(msg)
#     except Exception:
#         pass


# # -------------------- Chandigarh --------------------
# def download_chandigarh(ca_numbers, session_id):
#     try:
#         downloads[session_id] = {
#             "status": "downloading",
#             "progress": 0,
#             "completed": 0,
#             "total": len(ca_numbers),
#             "logs": [],
#             "files": {}
#         }
#         BASE_URL = "https://chandigarhpower.com/CPDL%20Billing%20History%20Document/root_output_folder"
#         months = ['092025']

#         for ca in ca_numbers:
#             ca = str(ca).strip()
#             for month in months:
#                 url = f"{BASE_URL}/{month}/{ca}_{month}.pdf"
#                 try:
#                     r = requests.get(url, timeout=30)
#                     if r.status_code == 200 and len(r.content) > 500:
#                         downloads[session_id]["files"][f"{ca}_{month}.pdf"] = r.content
#                         _log(session_id, f"✓ {ca}: Downloaded successfully ({len(r.content)} bytes)")
#                     else:
#                         _log(session_id, f"✗ {ca}: HTTP {r.status_code}")
#                 except Exception as e:
#                     _log(session_id, f"✗ {ca}: {str(e)[:120]}")

#             downloads[session_id]["completed"] += 1
#             downloads[session_id]["progress"] = int(downloads[session_id]["completed"] * 100 / downloads[session_id]["total"])

#         downloads[session_id]["status"] = "completed"
#     except Exception as e:
#         downloads[session_id]["status"] = "error"
#         _log(session_id, f"Error: {str(e)}")


# # -------------------- BSES (robust) --------------------
# def download_bses(ca_numbers, session_id):
#     try:
#         from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout  # type: ignore
#         from urllib.parse import urljoin
#         import re as _re
#     except Exception:
#         downloads[session_id] = {
#             "status": "error",
#             "logs": ["Playwright not installed. Run: pip install playwright && playwright install chromium"]
#         }
#         return

#     downloads[session_id] = {
#         "status": "downloading",
#         "progress": 0,
#         "completed": 0,
#         "total": len(ca_numbers),
#         "logs": [],
#         "files": {}
#     }

#     def log(m): _log(session_id, m)

#     for ca in ca_numbers:
#         ca = str(ca).strip()
#         pdf_data = None
#         suggested_name = f"BSES_{ca}.pdf"
#         try:
#             with sync_playwright() as p:
#                 browser = p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-blink-features=AutomationControlled"])
#                 context = browser.new_context(
#                     accept_downloads=True,
#                     ignore_https_errors=True,
#                     user_agent=("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
#                                 "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"),
#                     viewport={"width": 1366, "height": 900}
#                 )
#                 context.add_init_script("Object.defineProperty(navigator,'webdriver',{get:()=>undefined})")

#                 seen = {"url": None, "filename": None}
#                 def on_resp(resp):
#                     try:
#                         ct = (resp.headers.get("content-type") or "").lower()
#                         if ("pdf" in ct) or (".pdf" in resp.url.lower()):
#                             seen["url"] = resp.url
#                             cd = resp.headers.get("content-disposition") or ""
#                             m = _re.search(r'filename\*?=(?:UTF-8\'\')?"?([^";]+)"?', cd, _re.I)
#                             if m:
#                                 name = m.group(1).strip('" ')
#                                 if name.lower().endswith(".pdf"):
#                                     seen["filename"] = name
#                     except:
#                         pass
#                 context.on("response", on_resp)

#                 page = context.new_page()
#                 url = f"https://bsesbrpl.co.in:7879/DirectPayment/PayViewBill_BRPL.aspx?CA={ca}"
#                 page.goto(url, wait_until="domcontentloaded", timeout=60000)

#                 def try_click():
#                     clicked = False
#                     try:
#                         page.get_by_role("button", name=_re.compile("view bill", _re.I)).click(timeout=4000); clicked = True
#                     except: pass
#                     if not clicked:
#                         try:
#                             page.locator('#btnBillView, input[id*="btnBill"], input[value*="View Bill"], button:has-text("View Bill")').first.click(timeout=4000); clicked = True
#                         except: pass
#                     if not clicked:
#                         page.evaluate("""
#                           [...document.querySelectorAll('button,input[type=button],input[type=submit],a')]
#                           .find(el => /view/i.test((el.innerText||'') + ' ' + (el.value||'')))?.click();
#                         """)
#                     return True

#                 new_page = None
#                 try:
#                     with context.expect_page(timeout=12000) as pop:
#                         try_click()
#                     new_page = pop.value
#                 except PWTimeout:
#                     try:
#                         try_click()
#                     except: pass

#                 target = new_page or page

#                 dl = None
#                 try:
#                     with target.expect_download(timeout=15000) as di:
#                         try:
#                             target.get_by_role("button", name=_re.compile("view bill", _re.I)).click(timeout=3000)
#                         except: pass
#                     dl = di.value
#                 except PWTimeout:
#                     dl = None

#                 try:
#                     target.wait_for_load_state("networkidle", timeout=15000)
#                 except: pass

#                 if dl:
#                     try:
#                         pdf_data = dl.read_all_bytes()
#                     except Exception:
#                         tmp = f"/tmp/bses_{ca}.pdf"
#                         dl.save_as(tmp)
#                         with open(tmp, "rb") as f:
#                             pdf_data = f.read()
#                     suggested_name = dl.suggested_filename or suggested_name

#                 if not pdf_data and seen["url"]:
#                     r = context.request.get(seen["url"], timeout=60000)
#                     if r.ok and len(r.body()) > 500:
#                         pdf_data = r.body()
#                         suggested_name = seen["filename"] or suggested_name

#                 if not pdf_data:
#                     try:
#                         sel = ('embed[type="application/pdf"], iframe[src*=".pdf"], a[href$=".pdf"], a[href*="viewbill"], a[href*=".pdf"]')
#                         el = target.locator(sel)
#                         if el.count() > 0:
#                             src = el.first.get_attribute("src") or el.first.get_attribute("href")
#                             if src:
#                                 src = urljoin(target.url, src)
#                                 r2 = context.request.get(src, timeout=60000)
#                                 if r2.ok and len(r2.body()) > 500:
#                                     pdf_data = r2.body()
#                                     cd = r2.headers.get("content-disposition") or ""
#                                     m = _re.search(r'filename\*?=(?:UTF-8\'\')?"?([^";]+)"?', cd, _re.I)
#                                     if m and m.group(1).lower().endswith(".pdf"):
#                                         suggested_name = m.group(1)
#                     except:
#                         pass

#                 browser.close()
#         except Exception as e:
#             log(f"✗ {ca}: error {str(e)[:160]}")

#         if pdf_data and len(pdf_data) > 500:
#             downloads[session_id]["files"][suggested_name] = pdf_data
#             log(f"✓ {ca}: Downloaded ({len(pdf_data)} bytes)")
#         else:
#             log(f"✗ {ca}: Could not capture PDF")

#         downloads[session_id]["completed"] += 1
#         downloads[session_id]["progress"] = int(downloads[session_id]["completed"] * 100 / downloads[session_id]["total"])

#     downloads[session_id]["status"] = "completed"


# # -------------------- Jharkhand --------------------
# def download_jharkhand(ca_numbers, months, session_id):
#     try:
#         total = len(ca_numbers) * len(months)
#         downloads[session_id] = {
#             "status": "downloading",
#             "progress": 0,
#             "completed": 0,
#             "total": total,
#             "logs": [],
#             "files": {}
#         }

#         base = "https://cisapi.jbvnl.co.in/billing/rest/getviewbill/"
#         for mm in months:
#             m, y = int(mm[:2]), int(mm[2:])
#             for ca in ca_numbers:
#                 url = f"{base}{ca},{m},{y}"
#                 try:
#                     r = requests.get(url, timeout=60)
#                     if r.status_code == 200 and len(r.content) > 1000:
#                         downloads[session_id]["files"][f"Jharkhand_{ca}_{m}_{y}.pdf"] = r.content
#                         _log(session_id, f"✓ {ca} ({m}/{y}): Downloaded ({len(r.content)} bytes)")
#                     else:
#                         _log(session_id, f"✗ {ca} ({m}/{y}): HTTP {r.status_code}")
#                 except Exception as e:
#                     _log(session_id, f"✗ {ca} ({m}/{y}): {str(e)[:120]}")
#                 downloads[session_id]["completed"] += 1
#                 downloads[session_id]["progress"] = int(downloads[session_id]["completed"] * 100 / total)

#         downloads[session_id]["status"] = "completed"
#     except Exception as e:
#         downloads[session_id]["status"] = "error"
#         _log(session_id, f"Error: {str(e)}")


# # -------------------- North Bihar --------------------
# def download_north_bihar(ca_numbers, session_id):
#     try:
#         downloads[session_id] = {
#             "status": "downloading",
#             "progress": 0,
#             "completed": 0,
#             "total": len(ca_numbers),
#             "logs": [],
#             "files": {}
#         }
#         base = "https://api.bsphcl.co.in/nbWSMobileApp/ViewBill.asmx/GetViewBill?strCANumber="
#         for ca in ca_numbers:
#             ca = str(ca).strip()
#             try:
#                 r = requests.get(base + ca, timeout=30)
#                 if r.status_code == 200 and len(r.content) > 1000:
#                     downloads[session_id]["files"][f"NorthBihar_{ca}.pdf"] = r.content
#                     _log(session_id, f"✓ {ca}: Downloaded ({len(r.content)} bytes)")
#                 else:
#                     _log(session_id, f"✗ {ca}: HTTP {r.status_code}")
#             except Exception as e:
#                 _log(session_id, f"✗ {ca}: {str(e)[:120]}")
#             downloads[session_id]["completed"] += 1
#             downloads[session_id]["progress"] = int(downloads[session_id]["completed"] * 100 / downloads[session_id]["total"])
#         downloads[session_id]["status"] = "completed"
#     except Exception as e:
#         downloads[session_id]["status"] = "error"
#         _log(session_id, f"Error: {str(e)}")


# # -------------------- Dakshin Haryana --------------------
# def download_dakshin_haryana(ca_numbers, session_id):
#     try:
#         from playwright.sync_api import sync_playwright  # type: ignore
#         from urllib.parse import urljoin
#     except Exception:
#         downloads[session_id] = {
#             "status": "error",
#             "logs": ["Playwright not installed. Run: pip install playwright && playwright install chromium"]
#         }
#         return

#     downloads[session_id] = {
#         "status": "downloading",
#         "progress": 0,
#         "completed": 0,
#         "total": len(ca_numbers),
#         "logs": [],
#         "files": {}
#     }

#     for ca in ca_numbers:
#         ca = str(ca).strip()
#         pdf = None
#         try:
#             with sync_playwright() as p:
#                 browser = p.chromium.launch(headless=True, args=['--no-sandbox', '--disable-dev-shm-usage'])
#                 context = browser.new_context(accept_downloads=True)
#                 page = context.new_page()
#                 page.goto(f"https://dhbvn.org.in/Rapdrp/BD?UID={ca}", wait_until='domcontentloaded', timeout=30000)

#                 hit = {"u": None}
#                 def on_resp(resp):
#                     try:
#                         if 'pdf' in (resp.headers.get('content-type','').lower()):
#                             hit["u"] = resp.url
#                     except: pass
#                 context.on("response", on_resp)

#                 try:
#                     page.wait_for_load_state("networkidle", timeout=10000)
#                 except: pass

#                 if hit["u"]:
#                     r = context.request.get(hit["u"])
#                     if r.ok:
#                         pdf = r.body()
#                 else:
#                     for sel in ['embed[type="application/pdf"]','iframe[src*=".pdf"]','a[href$=".pdf"]']:
#                         el = page.query_selector(sel)
#                         if el:
#                             src = el.get_attribute("src") or el.get_attribute("href")
#                             if src:
#                                 src = urljoin(page.url, src)
#                                 rr = context.request.get(src)
#                                 if rr.ok:
#                                     pdf = rr.body()
#                                     break

#                 browser.close()
#         except Exception:
#             pdf = None

#         if pdf and len(pdf) > 1000:
#             downloads[session_id]["files"][f"DakshinHaryana_{ca}.pdf"] = pdf
#             _log(session_id, f"✓ {ca}: Downloaded ({len(pdf)} bytes)")
#         else:
#             _log(session_id, f"✗ {ca}: Could not capture PDF")

#         downloads[session_id]["completed"] += 1
#         downloads[session_id]["progress"] = int(downloads[session_id]["completed"] * 100 / downloads[session_id]["total"])

#     downloads[session_id]["status"] = "completed"


# # -------------------- MSEDCL helpers --------------------
# def _msedcl_requirements_ok():
#     missing = []
#     try:
#         from bs4 import BeautifulSoup as _B  # noqa
#     except Exception:
#         missing.append("beautifulsoup4")
#     try:
#         from Crypto.Cipher import AES as _A  # noqa
#     except Exception:
#         missing.append("pycryptodome")
#     try:
#         from playwright.sync_api import sync_playwright  # noqa
#     except Exception:
#         missing.append("playwright (and chromium)")
#     return (len(missing) == 0, missing)

# def _pad_pkcs7(b: bytes, blk=16) -> bytes:
#     n = blk - (len(b) % blk)
#     return b + bytes([n]) * n

# def _cryptojs_compat_aes_cbc_base64(plaintext: str) -> str:
#     # same key logic as your Node code
#     function_key = "WjTfQcM@H)E&B$y9"
#     reversed_key = function_key[::-1]
#     key = reversed_key.encode("utf-8")
#     iv  = reversed_key.encode("utf-8")
#     cipher = AES.new(key, AES.MODE_CBC, iv)
#     ct = cipher.encrypt(_pad_pkcs7(plaintext.encode("utf-8")))
#     return base64.b64encode(ct).decode("utf-8")

# def _bill_month_to_yyyymm(m: str) -> str:
#     mon = {'Jan':'01','Feb':'02','Mar':'03','Apr':'04','May':'05','Jun':'06',
#            'Jul':'07','Aug':'08','Sep':'09','Oct':'10','Nov':'11','Dec':'12'}
#     parts = (m or "").strip().split()
#     if len(parts) != 2 or parts[0] not in mon or not parts[1].isdigit():
#         raise ValueError(f"Bad billMonth: {m}. Use e.g. 'Sep 2025'")
#     return f"{parts[1]}{mon[parts[0]]}"

# def _extract_new_bill_container(html: str, check_not_found=False) -> str:
#     soup = BeautifulSoup(html, "html.parser")
#     for link in soup.select('link[rel="stylesheet"]'):
#         href = link.get("href","")
#         if "css/jquery.jqplot.css" in href:
#             link["href"] = "https://wss.mahadiscom.in/wss/css/jquery.jqplot.css"
#         if "css/wss.css" in href:
#             link["href"] = "https://wss.mahadiscom.in/wss/css/wss.css"
#     head_html = str(soup.head) if soup.head else ""
#     container = soup.select_one(".new_bill_container")
#     if not container:
#         raise RuntimeError("Could not find .new_bill_container in the HTML")
#     if check_not_found:
#         lab = soup.select_one("#billDate")
#         if (lab is None) or (not lab.get_text(strip=True)):
#             raise RuntimeError("Bill not found")
#     if soup.body and soup.body.has_attr("style"):
#         style = soup.body["style"]
#         soup.body["style"] = ";".join([r for r in style.split(";") if "background" not in r.lower()])
#     scripts_html = "\n".join([str(s) for s in soup.find_all("script")])
#     return f"<html>{head_html}<body>{str(container)}{scripts_html}</body></html>"

# def _render_html_to_pdf_bytes(html: str) -> bytes:
#     from playwright.sync_api import sync_playwright  # type: ignore
#     with sync_playwright() as p:
#         browser = p.chromium.launch(headless=True, args=["--no-sandbox","--disable-dev-shm-usage"])
#         ctx = browser.new_context()
#         page = ctx.new_page()
#         page.set_content(html, wait_until="networkidle")
#         try:
#             page.wait_for_selector("#ddlLanguage", timeout=300)
#             page.evaluate("""
#                 (() => {
#                   const s = document.getElementById('ddlLanguage');
#                   if (s) s.value = '1';
#                   if (typeof setLanguageLT === 'function') setLanguageLT();
#                 })();
#             """)
#             page.wait_for_timeout(150)
#         except Exception:
#             pass
#         pdf_bytes = page.pdf(format="A4", print_background=True, margin={"top":"0","right":"0","bottom":"0","left":"0"})
#         browser.close()
#         return pdf_bytes


# # -------------------- MSEDCL main --------------------
# def download_msedcl(ca_numbers, session_id, mode: str, bill_month: str,
#                     cookie_header: str = "", bu_map: Optional[Dict[str, str]] = None):
#     ok, missing = _msedcl_requirements_ok()
#     if not ok:
#         downloads[session_id] = {
#             "status": "error",
#             "progress": 0,
#             "completed": 0,
#             "total": 0,
#             "logs": [
#                 "✗ MSEDCL prerequisites are missing: " + ", ".join(missing),
#                 "Install: pip install beautifulsoup4 pycryptodome playwright",
#                 "Then: playwright install chromium"
#             ],
#             "files": {}
#         }
#         return

#     bill_month = (bill_month or "").strip() or datetime.now().strftime("%b %Y")
#     downloads[session_id] = {
#         "status": "downloading",
#         "progress": 0,
#         "completed": 0,
#         "total": len(ca_numbers),
#         "logs": [],
#         "files": {}
#     }

#     s = requests.Session()
#     headers_base = {
#         "Origin": "https://wss.mahadiscom.in",
#         "Referer": "https://wss.mahadiscom.in/wss/wss",
#         "User-Agent": "Mozilla/5.0",
#         "Content-Type": "application/x-www-form-urlencoded"
#     }
#     base_url = "https://wss.mahadiscom.in/wss/wss"
#     bill_not_found_check = False  # keep same as your Node option

#     for ca in ca_numbers:
#         ca_str = str(ca).strip()
#         try:
#             if mode.upper() == "LT":
#                 enc_ca = _cryptojs_compat_aes_cbc_base64(ca_str)
#                 enc_month = _cryptojs_compat_aes_cbc_base64(bill_month)
#                 form = {
#                     "uiActionName": "getLTEnergyBillPage",
#                     "hdnConsumerNumber": enc_ca,
#                     "isViaForm": "Y",
#                     "hdnBillMonth": enc_month,
#                     "hdnPC": "3",
#                     "hdnFreezeCode": "0",
#                     "consumerType": "1",
#                     "billingNo": "-1",
#                     "ddlCircleCode": "-1",
#                 }
#                 r = s.post(base_url, headers=headers_base, data=form, timeout=60)
#                 if r.status_code != 200 or "<html" not in r.text.lower():
#                     snippet = r.text[:180].replace("\n"," ").replace("\r"," ")
#                     _log(session_id, f"✗ {ca_str}: LT HTML not returned (HTTP {r.status_code}). Snippet: {snippet}")
#                     raise RuntimeError("LT HTML not returned")
#                 extracted = _extract_new_bill_container(r.text, bill_not_found_check)
#                 pdf = _render_html_to_pdf_bytes(extracted)
#                 fname = f"MSEDCL_LT_{ca_str}_{bill_month.replace(' ','_')}.pdf"
#                 downloads[session_id]["files"][fname] = pdf
#                 _log(session_id, f"✓ {ca_str} [LT]: PDF generated ({len(pdf)} bytes)")

#             elif mode.upper() == "HT":
#                 if not cookie_header:
#                     _log(session_id, f"✗ {ca_str}: Cookie required for HT (valid ~15 min)")
#                     raise RuntimeError("Cookie missing")
#                 headers_ht = headers_base.copy()
#                 headers_ht["Cookie"] = cookie_header
#                 form = {
#                     "hdnConsumerNumber": ca_str,
#                     "hdnBillMonth": bill_month,
#                     "uiActionName": "getHTEnergyBill",
#                 }
#                 r = s.post(base_url, headers=headers_ht, data=form, timeout=60)
#                 if r.status_code != 200 or "<html" not in r.text.lower():
#                     snippet = r.text[:180].replace("\n"," ").replace("\r"," ")
#                     _log(session_id, f"✗ {ca_str}: HT HTML not returned (HTTP {r.status_code}). Snippet: {snippet}")
#                     raise RuntimeError("HT HTML not returned")
#                 extracted = _extract_new_bill_container(r.text, bill_not_found_check)
#                 pdf = _render_html_to_pdf_bytes(extracted)
#                 fname = f"MSEDCL_HT_{ca_str}_{bill_month.replace(' ','_')}.pdf"
#                 downloads[session_id]["files"][fname] = pdf
#                 _log(session_id, f"✓ {ca_str} [HT]: PDF generated ({len(pdf)} bytes)")

#             elif mode.upper() == "HT2":
#                 if not bu_map or ca_str not in bu_map:
#                     _log(session_id, f"✗ {ca_str}: BU/Circle id missing. Provide mapping like '170019088370: 517'.")
#                     raise RuntimeError("BU missing")
#                 bu = str(bu_map[ca_str]).strip()
#                 form = {
#                     "sortBy": "BILL_MTH",
#                     "sortCriteria": "desc",
#                     "isLT": "N",
#                     "IS_LT_BILL_PDF": "Y",
#                     "IS_HT_BILL_PDF": "Y",
#                     "uiActionName": "getHTEnergyBillPagePDFPrint",
#                     "hdnConsumerNumber": ca_str,
#                     "hdnBillMonth": bill_month,
#                     "hdnBU": bu,
#                     "_xpf": "",
#                     "_xpt": "1",
#                     "_xf": "pdf",
#                     "billmnthArr": "",
#                     "billAmntArr": "",
#                     "billConsumpArr": ""
#                 }
#                 r = s.post(base_url, headers=headers_base, data=form, timeout=60)
#                 if r.status_code != 200:
#                     _log(session_id, f"✗ {ca_str}: HT2 init failed (HTTP {r.status_code})")
#                     raise RuntimeError("HT2 init failed")

#                 time.sleep(2.0)
#                 yyyymm = _bill_month_to_yyyymm(bill_month)
#                 pdf_url = f"https://wss.mahadiscom.in/wss/HTBillPDF/{bu}_{ca_str}_{yyyymm}.PDF"
#                 pr = s.get(pdf_url, timeout=60)
#                 if pr.status_code == 200 and len(pr.content) > 500:
#                     fname = f"MSEDCL_HT2_{ca_str}_{bill_month.replace(' ','_')}.pdf"
#                     downloads[session_id]["files"][fname] = pr.content
#                     _log(session_id, f"✓ {ca_str} [HT2]: Downloaded ({len(pr.content)} bytes)")
#                 else:
#                     _log(session_id, f"✗ {ca_str} [HT2]: PDF not returned (HTTP {pr.status_code})")
#                     raise RuntimeError("HT2 PDF not returned")

#             else:
#                 _log(session_id, f"✗ {ca_str}: Invalid mode '{mode}'")
#                 raise RuntimeError("Bad mode")

#         except Exception as e:
#             _log(session_id, f"✗ {ca_str}: {str(e)[:160]}")

#         downloads[session_id]["completed"] += 1
#         downloads[session_id]["progress"] = int(downloads[session_id]["completed"] * 100 / downloads[session_id]["total"])

#     downloads[session_id]["status"] = "completed"


# # -------------------- API --------------------
# @app.route('/download', methods=['POST'])
# def start_download():
#     data = request.json or {}
#     board = data.get('board')
#     ca_numbers = data.get('ca_numbers', [])
#     months = data.get('months', ['092025'])

#     msedcl_mode = (data.get('msedcl_mode') or '').upper()
#     bill_month = data.get('bill_month', '')
#     cookie_header = data.get('cookie', '')
#     bu_map = data.get('bu_map', {})

#     if board != "msedcl" and not ca_numbers:
#         return jsonify({"error": "CA numbers required"}), 400

#     session_id = str(uuid.uuid4())

#     if board == "chandigarh":
#         threading.Thread(target=download_chandigarh, args=(ca_numbers, session_id)).start()
#     elif board == "bses":
#         threading.Thread(target=download_bses, args=(ca_numbers, session_id)).start()
#     elif board == "jharkhand":
#         threading.Thread(target=download_jharkhand, args=(ca_numbers, months, session_id)).start()
#     elif board == "north_bihar":
#         threading.Thread(target=download_north_bihar, args=(ca_numbers, session_id)).start()
#     elif board == "dakshin_haryana":
#         threading.Thread(target=download_dakshin_haryana, args=(ca_numbers, session_id)).start()
#     elif board == "msedcl":
#         if msedcl_mode == "HT2" and not ca_numbers and isinstance(bu_map, dict) and bu_map:
#             ca_numbers = list(bu_map.keys())
#         if not ca_numbers:
#             return jsonify({"error": "CA numbers required for MSEDCL"}), 400
#         threading.Thread(
#             target=download_msedcl,
#             args=(ca_numbers, session_id, msedcl_mode, bill_month, cookie_header, bu_map)
#         ).start()
#     else:
#         return jsonify({"error": "Invalid board"}), 400

#     return jsonify({"session_id": session_id, "status": "started"})


# @app.route('/status/<session_id>', methods=['GET'])
# def get_status(session_id):
#     if session_id not in downloads:
#         return jsonify({"error": "Session not found"}), 404
#     status = downloads[session_id].copy()
#     status["file_count"] = len(status.get("files", {}))
#     status["total_size"] = sum(len(f) for f in status.get("files", {}).values())
#     status.pop("files", None)
#     return jsonify(status)


# @app.route('/download/<session_id>', methods=['GET'])
# def download_files(session_id):
#     if session_id not in downloads:
#         return jsonify({"error": "Session not found"}), 404
#     files = downloads[session_id].get("files", {})
#     if not files:
#         return jsonify({"error": "No files to download"}), 404
#     zip_buffer = io.BytesIO()
#     with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
#         for name, data in files.items():
#             zf.writestr(name, data)
#     zip_buffer.seek(0)
#     return send_file(zip_buffer, mimetype='application/zip', as_attachment=True,
#                      download_name=f"bills_{session_id[:8]}.zip")


# @app.route('/boards', methods=['GET'])
# def get_boards():
#     return jsonify({
#         "boards": [
#             {"id": "chandigarh", "name": "Chandigarh Power", "icon": "⚡"},
#             {"id": "bses", "name": "BSES (Delhi)", "icon": "🏢"},
#             {"id": "jharkhand", "name": "Jharkhand (JBVNL)", "icon": "🔌"},
#             {"id": "north_bihar", "name": "North Bihar", "icon": "💡"},
#             {"id": "dakshin_haryana", "name": "Dakshin Haryana", "icon": "🌐"},
#             {"id": "msedcl", "name": "MSEDCL (Maharashtra)", "icon": "🇮🇳"},
#         ]
#     })


# if __name__ == "__main__":
#     app.run(host="0.0.0.0", port=5000, debug=False)


# app.py
# --------------------------------------------------------------------
# Flask backend for multi-board bill downloader.
#
# Install once:
#   pip install flask flask-cors requests playwright beautifulsoup4 pycryptodome
#   playwright install chromium
#
# Run:
#   python app.py
# Then open the frontend (index.html) in your browser or visit http://localhost:5000/ if you serve it here.
# --------------------------------------------------------------------

import base64
import io
import json
import re
import threading
import time
import uuid
import sys
import zipfile
from datetime import datetime
from typing import Optional, Dict

import requests
from flask import Flask, request, jsonify, send_file
from flask_cors import CORS

# PDF processing for date extraction
try:
    from pypdf import PdfReader
except ImportError:
    PdfReader = None

# Optional deps for MSEDCL (we check inside functions)
try:
    from bs4 import BeautifulSoup
except Exception:
    BeautifulSoup = None

try:
    from Crypto.Cipher import AES
except Exception:
    AES = None

app = Flask(__name__)
CORS(app)

def generate_month_range(start_month, end_month, format_type="MMYYYY"):
    """
    Generate a list of months between start_month and end_month (inclusive)
    
    Args:
        start_month: Start month in format "YYYY-MM" or "MMYYYY"
        end_month: End month in format "YYYY-MM" or "MMYYYY" 
        format_type: Output format - "MMYYYY" or "YYYY-MM"
    
    Returns:
        List of months in the specified format
    """
    from datetime import datetime, timedelta
    import calendar
    
    def parse_month(month_str):
        """Parse month string in various formats"""
        month_str = str(month_str).strip()
        
        # Handle MMYYYY format (e.g., "012025")
        if len(month_str) == 6 and month_str.isdigit():
            mm, yyyy = month_str[:2], month_str[2:]
            return int(yyyy), int(mm)
        
        # Handle YYYY-MM format (e.g., "2025-01")
        if "-" in month_str:
            parts = month_str.split("-")
            if len(parts) == 2:
                return int(parts[0]), int(parts[1])
        
        # Handle MM/YYYY format (e.g., "01/2025")
        if "/" in month_str:
            parts = month_str.split("/")
            if len(parts) == 2:
                return int(parts[1]), int(parts[0])
        
        raise ValueError(f"Invalid month format: {month_str}")
    
    def format_month(year, month, fmt):
        """Format month according to specified format"""
        if fmt == "MMYYYY":
            return f"{month:02d}{year}"
        elif fmt == "YYYY-MM":
            return f"{year}-{month:02d}"
        else:
            raise ValueError(f"Unsupported format: {fmt}")
    
    try:
        start_year, start_month_num = parse_month(start_month)
        end_year, end_month_num = parse_month(end_month)
        
        # Create datetime objects for the first day of each month
        start_date = datetime(start_year, start_month_num, 1)
        end_date = datetime(end_year, end_month_num, 1)
        
        if start_date > end_date:
            raise ValueError("Start month cannot be after end month")
        
        months = []
        current_date = start_date
        
        while current_date <= end_date:
            months.append(format_month(current_date.year, current_date.month, format_type))
            
            # Move to next month
            if current_date.month == 12:
                current_date = current_date.replace(year=current_date.year + 1, month=1)
            else:
                current_date = current_date.replace(month=current_date.month + 1)
        
        return months
        
    except Exception as e:
        raise ValueError(f"Error generating month range: {str(e)}")

downloads: Dict[str, dict] = {}


def _log(session_id: str, msg: str):
    try:
        downloads[session_id]["logs"].append(msg)
    except Exception:
        pass


def extract_bill_date_from_pdf(pdf_data: bytes, board_prefix: str = "") -> Optional[str]:
    """
    Extract bill date from PDF content and return in DD-MM-YYYY format.
    Returns None if no date found or if pypdf is not available.
    """
    if not PdfReader or not pdf_data:
        return None
    
    try:
        # Create a PDF reader from bytes
        pdf_reader = PdfReader(io.BytesIO(pdf_data))
        
        # Extract text from all pages (usually first page contains the date)
        text = ""
        for page_num in range(min(3, len(pdf_reader.pages))):  # Check first 3 pages max
            page = pdf_reader.pages[page_num]
            text += page.extract_text() + "\n"
        
        # MSEDCL specific patterns (they use DD-MON-YY format like 18-NOV-25)
        if board_prefix.upper() in ["MSEDCL", "MAHARASHTRA"]:
            msedcl_patterns = [
                # DD-MON-YY format (18-NOV-25)
                r'\b(\d{1,2})[-/.]([A-Z]{3})[-/.](\d{2})\b',
                # DD-MON-YYYY format (18-NOV-2025)  
                r'\b(\d{1,2})[-/.]([A-Z]{3})[-/.](\d{4})\b',
                # DD MON YY format (18 NOV 25)
                r'\b(\d{1,2})\s+([A-Z]{3})\s+(\d{2})\b',
                # DD MON YYYY format (18 NOV 2025)
                r'\b(\d{1,2})\s+([A-Z]{3})\s+(\d{4})\b'
            ]
            
            # Look for MSEDCL specific bill date patterns
            msedcl_keywords = [
                r'bill\s*date[:\s]*([^\n\r]+)',
                r'billing\s*date[:\s]*([^\n\r]+)',
                r'date[:\s]*([^\n\r]*(?:NOV|DEC|JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT)[^\n\r]*)',
            ]
            
            # First try keyword-based search for MSEDCL
            for keyword_pattern in msedcl_keywords:
                matches = re.finditer(keyword_pattern, text, re.IGNORECASE)
                for match in matches:
                    date_text = match.group(1).strip().upper()
                    for pattern in msedcl_patterns:
                        date_match = re.search(pattern, date_text)
                        if date_match:
                            formatted = format_msedcl_date(date_match, pattern)
                            if formatted and is_reasonable_bill_date(formatted):
                                return formatted
            
            # If no keyword match, search entire text for MSEDCL patterns
            for pattern in msedcl_patterns:
                matches = re.finditer(pattern, text, re.IGNORECASE)
                for match in matches:
                    formatted = format_msedcl_date(match, pattern)
                    if formatted and is_reasonable_bill_date(formatted):
                        return formatted

        # UPCL specific patterns (they use DD-MM-YYYY format like 27-12-2025)
        if board_prefix.upper() in ["UPCL", "UTTARAKHAND"]:
            # Debug: Print that we're in UPCL mode
            # print(f"DEBUG: UPCL mode activated for board_prefix: {board_prefix}")
            
            upcl_patterns = [
                # DD-MM-YYYY format (27-12-2025)
                r'\b(\d{1,2})[-/.](\d{1,2})[-/.](\d{4})\b',
                # DD-MM-YY format (27-12-25)  
                r'\b(\d{1,2})[-/.](\d{1,2})[-/.](\d{2})\b',
                # DD/MM/YYYY format (27/12/2025)
                r'\b(\d{1,2})/(\d{1,2})/(\d{4})\b',
                # DD.MM.YYYY format (27.12.2025)
                r'\b(\d{1,2})\.(\d{1,2})\.(\d{4})\b'
            ]
            
            # Look for UPCL specific bill date patterns
            upcl_keywords = [
                r'bill\s*date[:\s]*([^\n\r]+)',
                r'billing\s*date[:\s]*([^\n\r]+)',
                r'issue\s*date[:\s]*([^\n\r]+)',
                r'date[:\s]*([^\n\r]*\d{1,2}[-/.]?\d{1,2}[-/.]?\d{2,4}[^\n\r]*)',
                # Look for dates in the format DD-MM-YYYY or DD/MM/YYYY
                r'(\d{1,2}[-/.]?\d{1,2}[-/.]?\d{2,4})',
            ]
            
            # First try keyword-based search for UPCL
            for keyword_pattern in upcl_keywords:
                matches = re.finditer(keyword_pattern, text, re.IGNORECASE)
                for match in matches:
                    date_text = match.group(1).strip()
                    # Debug: Print found keyword match
                    # print(f"DEBUG: UPCL keyword match: '{date_text}'")
                    for pattern in upcl_patterns:
                        date_match = re.search(pattern, date_text)
                        if date_match:
                            formatted = format_extracted_date(date_match, pattern)
                            # Debug: Print formatted result
                            # print(f"DEBUG: UPCL formatted: {date_match.group(0)} -> {formatted}")
                            if formatted and is_reasonable_bill_date(formatted):
                                # print(f"DEBUG: UPCL returning: {formatted}")
                                return formatted
            
            # If no keyword match, search entire text for UPCL patterns
            for pattern in upcl_patterns:
                matches = re.finditer(pattern, text)
                for match in matches:
                    formatted = format_extracted_date(match, pattern)
                    # Debug: Print direct pattern match
                    # print(f"DEBUG: UPCL direct match: {match.group(0)} -> {formatted}")
                    if formatted and is_reasonable_bill_date(formatted):
                        # print(f"DEBUG: UPCL returning direct: {formatted}")
                        return formatted

        # UPPCL specific patterns (they use DD-MON-YYYY format like 02-NOV-2025)
        if board_prefix.upper() in ["UPPCL", "DVVNL", "MVVNL", "PVVNL", "PU", "KESCO"]:
            uppcl_patterns = [
                # DD-MON-YYYY format (02-NOV-2025)
                r'\b(\d{1,2})[-/.]([A-Z]{3})[-/.](\d{4})\b',
                # DD-MON-YY format (02-NOV-25)  
                r'\b(\d{1,2})[-/.]([A-Z]{3})[-/.](\d{2})\b',
                # DD MON YYYY format (02 NOV 2025)
                r'\b(\d{1,2})\s+([A-Z]{3})\s+(\d{4})\b',
                # DD MON YY format (02 NOV 25)
                r'\b(\d{1,2})\s+([A-Z]{3})\s+(\d{2})\b'
            ]
            
            # Look for UPPCL specific bill date patterns
            uppcl_keywords = [
                r'bill\s*date[:\s]*([^\n\r]+)',
                r'billing\s*date[:\s]*([^\n\r]+)',
                r'due\s*date[:\s]*([^\n\r]+)',
                r'date[:\s]*([^\n\r]*(?:NOV|DEC|JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT)[^\n\r]*)',
                # Look for the specific pattern in UPPCL bills
                r'(\d{1,2}[-/.](?:JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)[-/.](?:\d{2}|\d{4}))',
            ]
            
            # First try keyword-based search for UPPCL
            for keyword_pattern in uppcl_keywords:
                matches = re.finditer(keyword_pattern, text, re.IGNORECASE)
                for match in matches:
                    date_text = match.group(1).strip().upper()
                    for pattern in uppcl_patterns:
                        date_match = re.search(pattern, date_text)
                        if date_match:
                            formatted = format_uppcl_date(date_match, pattern)
                            if formatted and is_reasonable_bill_date(formatted):
                                return formatted
            
            # If no keyword match, search entire text for UPPCL patterns
            for pattern in uppcl_patterns:
                matches = re.finditer(pattern, text, re.IGNORECASE)
                for match in matches:
                    formatted = format_uppcl_date(match, pattern)
                    if formatted and is_reasonable_bill_date(formatted):
                        return formatted
        
        # Enhanced general date patterns for fallback
        enhanced_date_patterns = [
            # DD-MM-YYYY, DD/MM/YYYY, DD.MM.YYYY (more flexible)
            r'(\d{1,2})[-/.](\d{1,2})[-/.](\d{4})',
            # DD-MM-YY, DD/MM/YY, DD.MM.YY  
            r'(\d{1,2})[-/.](\d{1,2})[-/.](\d{2})',
            # Month DD, YYYY or DD Month YYYY
            r'(\d{1,2})\s+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+(\d{4})',
            r'(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+(\d{1,2}),?\s+(\d{4})',
            # YYYY-MM-DD format
            r'(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})'
        ]
        
        # Look for bill date keywords
        bill_keywords = [
            r'bill\s*date[:\s]*([^\n\r]+)',
            r'billing\s*date[:\s]*([^\n\r]+)', 
            r'issue\s*date[:\s]*([^\n\r]+)',
            r'generated\s*on[:\s]*([^\n\r]+)',
            r'date\s*of\s*bill[:\s]*([^\n\r]+)',
            r'bill\s*period[:\s]*([^\n\r]+)',
        ]
        
        # First try to find dates near bill keywords
        for keyword_pattern in bill_keywords:
            matches = re.finditer(keyword_pattern, text, re.IGNORECASE)
            for match in matches:
                date_text = match.group(1).strip()
                # Try to extract date from this text
                for pattern in enhanced_date_patterns:
                    date_match = re.search(pattern, date_text, re.IGNORECASE)
                    if date_match:
                        formatted = format_extracted_date(date_match, pattern)
                        if formatted and is_reasonable_bill_date(formatted):
                            return formatted
        
        # If no keyword-based date found, look for any date in the text
        for pattern in enhanced_date_patterns:
            matches = re.finditer(pattern, text, re.IGNORECASE)
            for match in matches:
                formatted_date = format_extracted_date(match, pattern)
                if formatted_date and is_reasonable_bill_date(formatted_date):
                    return formatted_date
                    
    except Exception as e:
        # Silently fail - we don't want PDF date extraction to break the download
        pass
    
    return None


def format_uppcl_date(match, pattern: str) -> Optional[str]:
    """Format UPPCL specific date formats into DD-MM-YYYY format"""
    try:
        groups = match.groups()
        if len(groups) == 3:
            day, month_abbr, year = groups
            
            # Month abbreviation mapping
            month_map = {
                'JAN': '01', 'FEB': '02', 'MAR': '03', 'APR': '04',
                'MAY': '05', 'JUN': '06', 'JUL': '07', 'AUG': '08',
                'SEP': '09', 'OCT': '10', 'NOV': '11', 'DEC': '12'
            }
            
            month = month_map.get(month_abbr.upper())
            if not month:
                return None
            
            # Handle 2-digit years (convert to 4-digit)
            if len(year) == 2:
                year_int = int(year)
                if year_int >= 0 and year_int <= 50:  # 00-50 -> 2000-2050
                    year = f"20{year}"
                else:  # 51-99 -> 1951-1999
                    year = f"19{year}"
            
            # Validate ranges
            day_int, year_int = int(day), int(year)
            if 1 <= day_int <= 31 and 1900 <= year_int <= 2100:
                return f"{day_int:02d}-{month}-{year}"
                
    except (ValueError, IndexError):
        pass
    
    return None


def format_msedcl_date(match, pattern: str) -> Optional[str]:
    """Format MSEDCL specific date formats into DD-MM-YYYY format"""
    try:
        groups = match.groups()
        if len(groups) == 3:
            day, month_abbr, year = groups
            
            # Month abbreviation mapping
            month_map = {
                'JAN': '01', 'FEB': '02', 'MAR': '03', 'APR': '04',
                'MAY': '05', 'JUN': '06', 'JUL': '07', 'AUG': '08',
                'SEP': '09', 'OCT': '10', 'NOV': '11', 'DEC': '12'
            }
            
            month = month_map.get(month_abbr.upper())
            if not month:
                return None
            
            # Handle 2-digit years (convert to 4-digit)
            if len(year) == 2:
                year_int = int(year)
                if year_int >= 0 and year_int <= 50:  # 00-50 -> 2000-2050
                    year = f"20{year}"
                else:  # 51-99 -> 1951-1999
                    year = f"19{year}"
            
            # Validate ranges
            day_int, year_int = int(day), int(year)
            if 1 <= day_int <= 31 and 1900 <= year_int <= 2100:
                return f"{day_int:02d}-{month}-{year}"
                
    except (ValueError, IndexError):
        pass
    
    return None


def format_extracted_date(match, pattern: str) -> Optional[str]:
    """Format the extracted date match into DD-MM-YYYY format"""
    try:
        groups = match.groups()
        
        if 'Jan|Feb|Mar' in pattern:  # Month name patterns
            if len(groups) == 3:
                if groups[0].isdigit():  # DD Month YYYY
                    day, month_name, year = groups
                else:  # Month DD, YYYY
                    month_name, day, year = groups
                
                month_map = {
                    'jan': '01', 'feb': '02', 'mar': '03', 'apr': '04',
                    'may': '05', 'jun': '06', 'jul': '07', 'aug': '08', 
                    'sep': '09', 'oct': '10', 'nov': '11', 'dec': '12'
                }
                month = month_map.get(month_name.lower()[:3])
                if month:
                    return f"{int(day):02d}-{month}-{year}"
        
        elif len(groups) == 3:
            if pattern.startswith(r'\b(\d{4})'):  # YYYY-MM-DD
                year, month, day = groups
            else:  # DD-MM-YYYY or DD-MM-YY
                day, month, year = groups
                if len(year) == 2:  # Convert YY to YYYY
                    year = f"20{year}" if int(year) < 50 else f"19{year}"
            
            # Validate ranges
            day, month, year = int(day), int(month), int(year)
            if 1 <= day <= 31 and 1 <= month <= 12 and 1900 <= year <= 2100:
                return f"{day:02d}-{month:02d}-{year}"
                
    except (ValueError, IndexError):
        pass
    
    return None


def is_reasonable_bill_date(date_str: str) -> bool:
    """Check if the extracted date is reasonable for a bill date"""
    try:
        day, month, year = map(int, date_str.split('-'))
        date_obj = datetime(year, month, day)
        now = datetime.now()
        
        # Bill date should be within last 3 years and up to 6 months in future
        days_diff = (date_obj - now).days
        return -1095 <= days_diff <= 180  # 3 years back to 6 months forward
    except:
        return False


def rename_pdf_with_date(original_filename: str, pdf_data: bytes, board_prefix: str = "") -> str:
    """
    Rename PDF file with extracted bill date.
    Format: BoardPrefix_DD-MM-YYYY_OriginalName.pdf or BoardPrefix_OriginalName.pdf if no date found
    """
    try:
        extracted_date = extract_bill_date_from_pdf(pdf_data, board_prefix)
        
        if extracted_date:
            # Remove .pdf extension from original filename
            base_name = original_filename.replace('.pdf', '')
            
            # If board prefix is provided and not already in filename, add it
            if board_prefix and not base_name.upper().startswith(board_prefix.upper()):
                return f"{board_prefix}_{extracted_date}_{base_name}.pdf"
            else:
                return f"{base_name}_{extracted_date}.pdf"
        else:
            # If no date extracted, return original filename with board prefix if needed
            if board_prefix and not original_filename.upper().startswith(board_prefix.upper()):
                base_name = original_filename.replace('.pdf', '')
                return f"{board_prefix}_{base_name}.pdf"
            return original_filename
            
    except Exception:
        # If anything fails, return original filename
        return original_filename


# -------------------- Chandigarh --------------------
def download_chandigarh(ca_numbers, months, session_id):
    try:
        total = len(ca_numbers) * len(months)
        downloads[session_id] = {
            "status": "downloading",
            "progress": 0,
            "completed": 0,
            "total": total,
            "logs": [],
            "files": {}
        }
        BASE_URL = "https://chandigarhpower.com/CPDL%20Billing%20History%20Document/root_output_folder"

        for ca in ca_numbers:
            ca = str(ca).strip()
            for month in months:
                url = f"{BASE_URL}/{month}/{ca}_{month}.pdf"
                try:
                    r = requests.get(url, timeout=30)
                    if r.status_code == 200 and len(r.content) > 500:
                        filename = f"Chandigarh_{ca}_{month}.pdf"
                        # Rename with extracted date
                        filename = rename_pdf_with_date(filename, r.content, "Chandigarh")
                        downloads[session_id]["files"][filename] = r.content
                        _log(session_id, f"✓ {ca} ({month}): Downloaded successfully ({len(r.content)} bytes) - {filename}")
                    else:
                        _log(session_id, f"✗ {ca} ({month}): HTTP {r.status_code}")
                except Exception as e:
                    _log(session_id, f"✗ {ca} ({month}): {str(e)[:120]}")

                downloads[session_id]["completed"] += 1
                downloads[session_id]["progress"] = int(downloads[session_id]["completed"] * 100 / total)

        downloads[session_id]["status"] = "completed"
    except Exception as e:
        downloads[session_id]["status"] = "error"
        _log(session_id, f"Error: {str(e)}")


# -------------------- BSES (robust) --------------------
def download_bses(ca_numbers, session_id):
    try:
        from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout  # type: ignore
        from urllib.parse import urljoin
        import re as _re
    except Exception:
        downloads[session_id] = {
            "status": "error",
            "logs": ["Playwright not installed. Run: pip install playwright && playwright install chromium"]
        }
        return

    downloads[session_id] = {
        "status": "downloading",
        "progress": 0,
        "completed": 0,
        "total": len(ca_numbers),
        "logs": [],
        "files": {}
    }

    def log(m): _log(session_id, m)

    for ca in ca_numbers:
        ca = str(ca).strip()
        pdf_data = None
        suggested_name = f"BSES_{ca}.pdf"
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-blink-features=AutomationControlled"])
                context = browser.new_context(
                    accept_downloads=True,
                    ignore_https_errors=True,
                    user_agent=("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                                "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"),
                    viewport={"width": 1366, "height": 900}
                )
                context.add_init_script("Object.defineProperty(navigator,'webdriver',{get:()=>undefined})")

                seen = {"url": None, "filename": None}
                def on_resp(resp):
                    try:
                        ct = (resp.headers.get("content-type") or "").lower()
                        if ("pdf" in ct) or (".pdf" in resp.url.lower()):
                            seen["url"] = resp.url
                            cd = resp.headers.get("content-disposition") or ""
                            m = _re.search(r'filename\*?=(?:UTF-8\'\')?"?([^";]+)"?', cd, _re.I)
                            if m:
                                name = m.group(1).strip('" ')
                                if name.lower().endswith(".pdf"):
                                    seen["filename"] = name
                    except:
                        pass
                context.on("response", on_resp)

                page = context.new_page()
                url = f"https://bsesbrpl.co.in:7879/DirectPayment/PayViewBill_BRPL.aspx?CA={ca}"
                page.goto(url, wait_until="domcontentloaded", timeout=60000)

                def try_click():
                    clicked = False
                    try:
                        page.get_by_role("button", name=_re.compile("view bill", _re.I)).click(timeout=4000); clicked = True
                    except: pass
                    if not clicked:
                        try:
                            page.locator('#btnBillView, input[id*="btnBill"], input[value*="View Bill"], button:has-text("View Bill")').first.click(timeout=4000); clicked = True
                        except: pass
                    if not clicked:
                        page.evaluate("""
                          [...document.querySelectorAll('button,input[type=button],input[type=submit],a')]
                          .find(el => /view/i.test((el.innerText||'') + ' ' + (el.value||'')))?.click();
                        """)
                    return True

                new_page = None
                try:
                    with context.expect_page(timeout=12000) as pop:
                        try_click()
                    new_page = pop.value
                except PWTimeout:
                    try:
                        try_click()
                    except: pass

                target = new_page or page

                dl = None
                try:
                    with target.expect_download(timeout=15000) as di:
                        try:
                            target.get_by_role("button", name=_re.compile("view bill", _re.I)).click(timeout=3000)
                        except: pass
                    dl = di.value
                except PWTimeout:
                    dl = None

                try:
                    target.wait_for_load_state("networkidle", timeout=15000)
                except: pass

                if dl:
                    try:
                        pdf_data = dl.read_all_bytes()
                    except Exception:
                        tmp = f"/tmp/bses_{ca}.pdf"
                        dl.save_as(tmp)
                        with open(tmp, "rb") as f:
                            pdf_data = f.read()
                    suggested_name = dl.suggested_filename or suggested_name

                if not pdf_data and seen["url"]:
                    r = context.request.get(seen["url"], timeout=60000)
                    if r.ok and len(r.body()) > 500:
                        pdf_data = r.body()
                        suggested_name = seen["filename"] or suggested_name

                if not pdf_data:
                    try:
                        sel = ('embed[type="application/pdf"], iframe[src*=".pdf"], a[href$=".pdf"], a[href*="viewbill"], a[href*=".pdf"]')
                        el = target.locator(sel)
                        if el.count() > 0:
                            src = el.first.get_attribute("src") or el.first.get_attribute("href")
                            if src:
                                src = urljoin(target.url, src)
                                r2 = context.request.get(src, timeout=60000)
                                if r2.ok and len(r2.body()) > 500:
                                    pdf_data = r2.body()
                                    cd = r2.headers.get("content-disposition") or ""
                                    m = _re.search(r'filename\*?=(?:UTF-8\'\')?"?([^";]+)"?', cd, _re.I)
                                    if m and m.group(1).lower().endswith(".pdf"):
                                        suggested_name = m.group(1)
                    except:
                        pass

                browser.close()
        except Exception as e:
            log(f"✗ {ca}: error {str(e)[:160]}")

        if pdf_data and len(pdf_data) > 500:
            # Rename with extracted date
            suggested_name = rename_pdf_with_date(suggested_name, pdf_data, "BSES")
            downloads[session_id]["files"][suggested_name] = pdf_data
            log(f"✓ {ca}: Downloaded ({len(pdf_data)} bytes) - {suggested_name}")
        else:
            log(f"✗ {ca}: Could not capture PDF")

        downloads[session_id]["completed"] += 1
        downloads[session_id]["progress"] = int(downloads[session_id]["completed"] * 100 / downloads[session_id]["total"])

    downloads[session_id]["status"] = "completed"


# -------------------- Jharkhand --------------------
def download_jharkhand(ca_numbers, months, session_id):
    try:
        total = len(ca_numbers) * len(months)
        downloads[session_id] = {
            "status": "downloading",
            "progress": 0,
            "completed": 0,
            "total": total,
            "logs": [],
            "files": {}
        }

        base = "https://cisapi.jbvnl.co.in/billing/rest/getviewbill/"
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        
        for mm in months:
            m, y = int(mm[:2]), int(mm[2:])
            for ca in ca_numbers:
                url = f"{base}{ca},{m},{y}"
                try:
                    _log(session_id, f"Downloading {ca} for {m}/{y}...")
                    r = requests.get(url, headers=headers, timeout=60)
                    _log(session_id, f"Response: {r.status_code}, Content-Length: {len(r.content)}")
                    
                    if r.status_code == 200 and len(r.content) > 1000:
                        filename = f"Jharkhand_{ca}_{m}_{y}.pdf"
                        # Rename with extracted date
                        filename = rename_pdf_with_date(filename, r.content, "Jharkhand")
                        downloads[session_id]["files"][filename] = r.content
                        _log(session_id, f"✓ {ca} ({m}/{y}): Downloaded ({len(r.content)} bytes) - {filename}")
                    else:
                        _log(session_id, f"✗ {ca} ({m}/{y}): HTTP {r.status_code}, Content: {r.text[:200] if r.text else 'No content'}")
                except Exception as e:
                    _log(session_id, f"✗ {ca} ({m}/{y}): {str(e)[:120]}")
                downloads[session_id]["completed"] += 1
                downloads[session_id]["progress"] = int(downloads[session_id]["completed"] * 100 / total)

        downloads[session_id]["status"] = "completed"
    except Exception as e:
        downloads[session_id]["status"] = "error"
        _log(session_id, f"Error: {str(e)}")


# -------------------- North Bihar --------------------
def download_north_bihar(ca_numbers, session_id):
    try:
        downloads[session_id] = {
            "status": "downloading",
            "progress": 0,
            "completed": 0,
            "total": len(ca_numbers),
            "logs": [],
            "files": {}
        }
        base = "https://api.bsphcl.co.in/nbWSMobileApp/ViewBill.asmx/GetViewBill?strCANumber="
        for ca in ca_numbers:
            ca = str(ca).strip()
            try:
                r = requests.get(base + ca, timeout=30)
                if r.status_code == 200 and len(r.content) > 1000:
                    filename = f"NorthBihar_{ca}.pdf"
                    # Rename with extracted date
                    filename = rename_pdf_with_date(filename, r.content, "NorthBihar")
                    downloads[session_id]["files"][filename] = r.content
                    _log(session_id, f"✓ {ca}: Downloaded ({len(r.content)} bytes) - {filename}")
                else:
                    _log(session_id, f"✗ {ca}: HTTP {r.status_code}")
            except Exception as e:
                _log(session_id, f"✗ {ca}: {str(e)[:120]}")
            downloads[session_id]["completed"] += 1
            downloads[session_id]["progress"] = int(downloads[session_id]["completed"] * 100 / downloads[session_id]["total"])
        downloads[session_id]["status"] = "completed"
    except Exception as e:
        downloads[session_id]["status"] = "error"
        _log(session_id, f"Error: {str(e)}")


# -------------------- Dakshin Haryana --------------------
def download_dakshin_haryana(ca_numbers, session_id):
    try:
        from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout  # type: ignore
        from urllib.parse import urljoin
        import base64
    except Exception:
        downloads[session_id] = {
            "status": "error",
            "logs": ["Playwright not installed. Run: pip install playwright && playwright install chromium"]
        }
        return

    downloads[session_id] = {
        "status": "downloading",
        "progress": 0,
        "completed": 0,
        "total": len(ca_numbers),
        "logs": [],
        "files": {}
    }

    def log(m): _log(session_id, m)

    def looks_like_pdf(b: bytes) -> bool:
        return bool(b) and (b[:5] == b"%PDF-")

    for ca in ca_numbers:
        ca = str(ca).strip()
        pdf = None
        try:
            with sync_playwright() as p:
                UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
                browser = p.chromium.launch(
                    headless=True,
                    args=['--no-sandbox', '--disable-dev-shm-usage', '--disable-blink-features=AutomationControlled']
                )
                context = browser.new_context(
                    accept_downloads=True,
                    ignore_https_errors=True,
                    user_agent=UA,
                    viewport={"width": 1366, "height": 900}
                )
                context.add_init_script("Object.defineProperty(navigator,'webdriver',{get:()=>undefined})")

                page = context.new_page()
                url = f"https://dhbvn.org.in/Rapdrp/BD?UID={ca}"

                # A) Try direct fetch first (often the server immediately returns the PDF)
                try:
                    r0 = context.request.get(url, timeout=45000)
                    if r0.ok:
                        body0 = r0.body()
                        if looks_like_pdf(body0):
                            pdf = body0
                except Exception:
                    pass

                if not pdf:
                    # B) Catch PDF as the navigation response
                    def is_pdf_resp(r):
                        ct = (r.headers.get('content-type') or '').lower()
                        return ('.pdf' in r.url.lower()) or ('pdf' in ct) or ('octet-stream' in ct)
                    try:
                        with page.expect_response(is_pdf_resp, timeout=25000) as resp_info:
                            page.goto(url, wait_until='domcontentloaded', timeout=45000)
                        resp = resp_info.value
                        if resp.ok:
                            body = resp.body()
                            if looks_like_pdf(body):
                                pdf = body
                            # Sometimes header says octet-stream; still OK if body looks like PDF
                    except PWTimeout:
                        page.goto(url, wait_until='domcontentloaded', timeout=45000)
                    except Exception:
                        pass

                    # C) Listen for late PDF loads (iframes, background reqs)
                    hit = {"u": None}
                    def on_resp(r):
                        try:
                            ct = (r.headers.get('content-type') or '').lower()
                            if ('pdf' in ct) or ('.pdf' in r.url.lower()):
                                hit["u"] = r.url
                        except Exception:
                            pass
                    context.on("response", on_resp)

                    try:
                        page.wait_for_load_state("networkidle", timeout=8000)
                    except Exception:
                        pass

                    if not pdf and hit["u"]:
                        try:
                            rr = context.request.get(hit["u"], timeout=30000)
                            body = rr.body()
                            if rr.ok and looks_like_pdf(body):
                                pdf = body
                        except Exception:
                            pass

                    # D) DOM fallbacks (iframe/object/embed/a) + data: URL support
                    if not pdf:
                        selectors = [
                            'embed[type="application/pdf"]',
                            'object[type="application/pdf"]',
                            'iframe[src*=".pdf" i]',
                            'a[href*=".pdf" i]'
                        ]
                        for sel in selectors:
                            try:
                                el = page.query_selector(sel)
                                if not el:
                                    continue
                                src = el.get_attribute("src") or el.get_attribute("href")
                                if not src:
                                    continue
                                if src.startswith("data:application/pdf;base64,"):
                                    try:
                                        pdf = base64.b64decode(src.split(",",1)[1])
                                        if looks_like_pdf(pdf):
                                            break
                                        else:
                                            pdf = None
                                    except Exception:
                                        pdf = None
                                else:
                                    src = urljoin(page.url, src)
                                    rr2 = context.request.get(src, timeout=30000)
                                    body2 = rr2.body()
                                    if rr2.ok and looks_like_pdf(body2):
                                        pdf = body2
                                        break
                            except Exception:
                                pass

                    # E) Content-Disposition download fallback
                    if not pdf:
                        try:
                            trigger = page.locator(
                                'a:has-text("Download"), a:has-text("View"), button:has-text("Download"), button:has-text("View")'
                            ).first
                            if trigger and trigger.count() > 0:
                                with page.expect_download(timeout=15000) as di:
                                    trigger.click(timeout=3000)
                                dl = di.value
                                try:
                                    pdf = dl.read_all_bytes()
                                except Exception:
                                    import tempfile, os
                                    tmp = tempfile.mkstemp(suffix=".pdf")[1]
                                    dl.save_as(tmp)
                                    with open(tmp, "rb") as f:
                                        pdf = f.read()
                                    try: os.remove(tmp)
                                    except Exception: pass
                        except Exception:
                            pass

                browser.close()
        except Exception as e:
            log(f"✗ {ca}: error {str(e)[:160]}")

        if pdf and len(pdf) > 500 and pdf.startswith(b"%PDF-"):
            filename = f"DakshinHaryana_{ca}.pdf"
            # Rename with extracted date
            filename = rename_pdf_with_date(filename, pdf, "DakshinHaryana")
            downloads[session_id]["files"][filename] = pdf
            log(f"✓ {ca}: Downloaded ({len(pdf)} bytes) - {filename}")
        else:
            log(f"✗ {ca}: Could not capture PDF")

        downloads[session_id]["completed"] += 1
        downloads[session_id]["progress"] = int(downloads[session_id]["completed"] * 100 / downloads[session_id]["total"])

    downloads[session_id]["status"] = "completed"



# -------------------- Telangana Southern Power DISCOM --------------------
def download_tgspdcl(ca_numbers, session_id):
    try:
        from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
    except Exception:
        downloads[session_id] = {
            "status": "error",
            "logs": ["Playwright not installed. Run: pip install playwright && playwright install chromium"]
        }
        return

    downloads[session_id] = {
        "status": "downloading",
        "progress": 0,
        "completed": 0,
        "total": len(ca_numbers),
        "logs": [],
        "files": {}
    }

    def log(m): _log(session_id, m)

    for ca in ca_numbers:
        ca = str(ca).strip()
        pdf_data = None
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(
                    headless=True,
                    args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-blink-features=AutomationControlled"]
                )
                context = browser.new_context(
                    accept_downloads=True,
                    ignore_https_errors=True,
                    user_agent=("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                                "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"),
                    viewport={"width": 1366, "height": 900}
                )
                context.add_init_script("Object.defineProperty(navigator,'webdriver',{get:()=>undefined})")

                page = context.new_page()
                url = f"https://tgsouthernpower.org/ops/DuplicateBill4Login.jsp?ctscno={ca}"
                
                log(f"Loading bill page for CA: {ca}")
                page.goto(url, wait_until="domcontentloaded", timeout=60000)

                # Wait for page to load
                try:
                    page.wait_for_load_state("networkidle", timeout=15000)
                except:
                    pass

                # Try to find and click the Print button
                try:
                    # Wait for the print button to be available
                    page.wait_for_selector('input[value="Print"]', timeout=10000)
                    
                    # Click the print button and capture the PDF
                    with page.expect_download(timeout=20000) as download_info:
                        page.click('input[value="Print"]')
                    
                    download = download_info.value
                    pdf_data = download.read_all_bytes()
                    
                except PWTimeout:
                    log(f"⚠ {ca}: Print button timeout, trying alternative method")
                    
                    # Alternative: Try to print the page directly
                    try:
                        pdf_data = page.pdf(
                            format="A4",
                            print_background=True,
                            margin={"top": "0.5cm", "right": "0.5cm", "bottom": "0.5cm", "left": "0.5cm"}
                        )
                    except Exception as e:
                        log(f"✗ {ca}: PDF generation failed - {str(e)[:100]}")

                browser.close()

        except Exception as e:
            log(f"✗ {ca}: Error - {str(e)[:160]}")

        if pdf_data and len(pdf_data) > 500:
            filename = f"TGSPDCL_{ca}.pdf"
            # Rename with extracted date
            filename = rename_pdf_with_date(filename, pdf_data, "TGSPDCL")
            downloads[session_id]["files"][filename] = pdf_data
            log(f"✓ {ca}: Downloaded ({len(pdf_data)} bytes) - {filename}")
        else:
            log(f"✗ {ca}: Could not capture PDF")

        downloads[session_id]["completed"] += 1
        downloads[session_id]["progress"] = int(downloads[session_id]["completed"] * 100 / downloads[session_id]["total"])

    downloads[session_id]["status"] = "completed"


# -------------------- Uttar Haryana --------------------
def download_uttar_haryana(ca_numbers, session_id):
    try:
        from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout  # type: ignore
        from urllib.parse import urljoin
        import base64
    except Exception:
        downloads[session_id] = {
            "status": "error",
            "logs": ["Playwright not installed. Run: pip install playwright && playwright install chromium"]
        }
        return

    downloads[session_id] = {
        "status": "downloading",
        "progress": 0,
        "completed": 0,
        "total": len(ca_numbers),
        "logs": [],
        "files": {}
    }

    def log(m): _log(session_id, m)

    def looks_like_pdf(b: bytes) -> bool:
        return bool(b) and (b[:5] == b"%PDF-")

    for ca in ca_numbers:
        ca = str(ca).strip()
        pdf = None
        try:
            with sync_playwright() as p:
                UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
                browser = p.chromium.launch(
                    headless=True,
                    args=['--no-sandbox', '--disable-dev-shm-usage', '--disable-blink-features=AutomationControlled']
                )
                context = browser.new_context(
                    accept_downloads=True,
                    ignore_https_errors=True,
                    user_agent=UA,
                    viewport={"width": 1366, "height": 900}
                )
                context.add_init_script("Object.defineProperty(navigator,'webdriver',{get:()=>undefined})")

                page = context.new_page()
                url = f"https://uhbvn.org.in/Rapdrp/BD?UID={ca}"

                # A) Try direct fetch first (often the server immediately returns the PDF)
                try:
                    r0 = context.request.get(url, timeout=45000)
                    if r0.ok:
                        body0 = r0.body()
                        if looks_like_pdf(body0):
                            pdf = body0
                except Exception:
                    pass

                if not pdf:
                    # B) Catch PDF as the navigation response
                    def is_pdf_resp(r):
                        ct = (r.headers.get('content-type') or '').lower()
                        return ('.pdf' in r.url.lower()) or ('pdf' in ct) or ('octet-stream' in ct)
                    try:
                        with page.expect_response(is_pdf_resp, timeout=25000) as resp_info:
                            page.goto(url, wait_until='domcontentloaded', timeout=45000)
                        resp = resp_info.value
                        if resp.ok:
                            body = resp.body()
                            if looks_like_pdf(body):
                                pdf = body
                            # Sometimes header says octet-stream; still OK if body looks like PDF
                    except PWTimeout:
                        page.goto(url, wait_until='domcontentloaded', timeout=45000)
                    except Exception:
                        pass

                    # C) Listen for late PDF loads (iframes, background reqs)
                    hit = {"u": None}
                    def on_resp(r):
                        try:
                            ct = (r.headers.get('content-type') or '').lower()
                            if ('pdf' in ct) or ('.pdf' in r.url.lower()):
                                hit["u"] = r.url
                        except Exception:
                            pass
                    context.on("response", on_resp)

                    try:
                        page.wait_for_load_state("networkidle", timeout=8000)
                    except Exception:
                        pass

                    if not pdf and hit["u"]:
                        try:
                            rr = context.request.get(hit["u"], timeout=30000)
                            body = rr.body()
                            if rr.ok and looks_like_pdf(body):
                                pdf = body
                        except Exception:
                            pass

                    # D) DOM fallbacks (iframe/object/embed/a) + data: URL support
                    if not pdf:
                        selectors = [
                            'embed[type="application/pdf"]',
                            'object[type="application/pdf"]',
                            'iframe[src*=".pdf" i]',
                            'a[href*=".pdf" i]'
                        ]
                        for sel in selectors:
                            try:
                                el = page.query_selector(sel)
                                if not el:
                                    continue
                                src = el.get_attribute("src") or el.get_attribute("href")
                                if not src:
                                    continue
                                if src.startswith("data:application/pdf;base64,"):
                                    try:
                                        pdf = base64.b64decode(src.split(",",1)[1])
                                        if looks_like_pdf(pdf):
                                            break
                                        else:
                                            pdf = None
                                    except Exception:
                                        pdf = None
                                else:
                                    src = urljoin(page.url, src)
                                    rr2 = context.request.get(src, timeout=30000)
                                    body2 = rr2.body()
                                    if rr2.ok and looks_like_pdf(body2):
                                        pdf = body2
                                        break
                            except Exception:
                                pass

                    # E) Content-Disposition download fallback
                    if not pdf:
                        try:
                            trigger = page.locator(
                                'a:has-text("Download"), a:has-text("View"), button:has-text("Download"), button:has-text("View")'
                            ).first
                            if trigger and trigger.count() > 0:
                                with page.expect_download(timeout=15000) as di:
                                    trigger.click(timeout=3000)
                                dl = di.value
                                try:
                                    pdf = dl.read_all_bytes()
                                except Exception:
                                    import tempfile, os
                                    tmp = tempfile.mkstemp(suffix=".pdf")[1]
                                    dl.save_as(tmp)
                                    with open(tmp, "rb") as f:
                                        pdf = f.read()
                                    try: os.remove(tmp)
                                    except Exception: pass
                        except Exception:
                            pass

                browser.close()
        except Exception as e:
            log(f"✗ {ca}: error {str(e)[:160]}")

        if pdf and len(pdf) > 500 and pdf.startswith(b"%PDF-"):
            filename = f"UttarHaryana_{ca}.pdf"
            # Rename with extracted date
            filename = rename_pdf_with_date(filename, pdf, "UttarHaryana")
            downloads[session_id]["files"][filename] = pdf
            log(f"✓ {ca}: Downloaded ({len(pdf)} bytes) - {filename}")
        else:
            log(f"✗ {ca}: Could not capture PDF")

        downloads[session_id]["completed"] += 1
        downloads[session_id]["progress"] = int(downloads[session_id]["completed"] * 100 / downloads[session_id]["total"])

    downloads[session_id]["status"] = "completed"



# -------------------- MSEDCL helpers --------------------
def _msedcl_requirements_ok():
    missing = []
    try:
        from bs4 import BeautifulSoup as _B  # noqa
    except Exception:
        missing.append("beautifulsoup4")
    try:
        from Crypto.Cipher import AES as _A  # noqa
    except Exception:
        missing.append("pycryptodome")
    try:
        from playwright.sync_api import sync_playwright  # noqa
    except Exception:
        missing.append("playwright (and chromium)")
    return (len(missing) == 0, missing)

def _pad_pkcs7(b: bytes, blk=16) -> bytes:
    n = blk - (len(b) % blk)
    return b + bytes([n]) * n

def _cryptojs_compat_aes_cbc_base64(plaintext: str) -> str:
    function_key = "WjTfQcM@H)E&B$y9"
    reversed_key = function_key[::-1]
    key = reversed_key.encode("utf-8")
    iv  = reversed_key.encode("utf-8")
    cipher = AES.new(key, AES.MODE_CBC, iv)
    ct = cipher.encrypt(_pad_pkcs7(plaintext.encode("utf-8")))
    return base64.b64encode(ct).decode("utf-8")

def _bill_month_to_yyyymm(m: str) -> str:
    mon = {'Jan':'01','Feb':'02','Mar':'03','Apr':'04','May':'05','Jun':'06',
           'Jul':'07','Aug':'08','Sep':'09','Oct':'10','Nov':'11','Dec':'12'}
    parts = (m or "").strip().split()
    if len(parts) != 2 or parts[0] not in mon or not parts[1].isdigit():
        raise ValueError(f"Bad billMonth: {m}. Use e.g. 'Sep 2025'")
    return f"{parts[1]}{mon[parts[0]]}"

def _extract_new_bill_container(html: str, check_not_found=False) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for link in soup.select('link[rel="stylesheet"]'):
        href = link.get("href","")
        if "css/jquery.jqplot.css" in href:
            link["href"] = "https://wss.mahadiscom.in/wss/css/jquery.jqplot.css"
        if "css/wss.css" in href:
            link["href"] = "https://wss.mahadiscom.in/wss/css/wss.css"
    head_html = str(soup.head) if soup.head else ""
    container = soup.select_one(".new_bill_container")
    if not container:
        raise RuntimeError("Could not find .new_bill_container in the HTML")
    if check_not_found:
        lab = soup.select_one("#billDate")
        if (lab is None) or (not lab.get_text(strip=True)):
            raise RuntimeError("Bill not found")
    if soup.body and soup.body.has_attr("style"):
        style = soup.body["style"]
        soup.body["style"] = ";".join([r for r in style.split(";") if "background" not in r.lower()])
    scripts_html = "\n".join([str(s) for s in soup.find_all("script")])
    return f"<html>{head_html}<body>{str(container)}{scripts_html}</body></html>"

def _render_html_to_pdf_bytes(html: str) -> bytes:
    from playwright.sync_api import sync_playwright  # type: ignore
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox","--disable-dev-shm-usage"])
        ctx = browser.new_context()
        page = ctx.new_page()
        page.set_content(html, wait_until="networkidle")
        try:
            page.wait_for_selector("#ddlLanguage", timeout=300)
            page.evaluate("""
                (() => {
                  const s = document.getElementById('ddlLanguage');
                  if (s) s.value = '1';
                  if (typeof setLanguageLT === 'function') setLanguageLT();
                })();
            """)
            page.wait_for_timeout(150)
        except Exception:
            pass
        pdf_bytes = page.pdf(format="A4", print_background=True, margin={"top":"0","right":"0","bottom":"0","left":"0"})
        browser.close()
        return pdf_bytes


# -------------------- MSEDCL main --------------------
def download_msedcl(ca_numbers, session_id, mode: str, bill_months,
                    cookie_header: str = "", bu_map: Optional[Dict[str, str]] = None):
    ok, missing = _msedcl_requirements_ok()
    if not ok:
        downloads[session_id] = {
            "status": "error",
            "progress": 0,
            "completed": 0,
            "total": 0,
            "logs": [
                "✗ MSEDCL prerequisites are missing: " + ", ".join(missing),
                "Install: pip install beautifulsoup4 pycryptodome playwright",
                "Then: playwright install chromium"
            ],
            "files": {}
        }
        return

    # Handle both single month (string) and multiple months (list) for backward compatibility
    if isinstance(bill_months, str):
        bill_months = [bill_months]
    if not bill_months or not bill_months[0]:
        bill_months = [datetime.now().strftime("%b %Y")]
    
    # Clean up month strings
    bill_months = [(month or "").strip() for month in bill_months if (month or "").strip()]
    
    downloads[session_id] = {
        "status": "downloading",
        "progress": 0,
        "completed": 0,
        "total": len(ca_numbers) * len(bill_months),
        "logs": [],
        "files": {}
    }

    try:
        s = requests.Session()
        headers_base = {
            "Origin": "https://wss.mahadiscom.in",
            "Referer": "https://wss.mahadiscom.in/wss/wss",
            "User-Agent": "Mozilla/5.0",
            "Content-Type": "application/x-www-form-urlencoded"
        }
        base_url = "https://wss.mahadiscom.in/wss/wss"
        bill_not_found_check = False

        for ca in ca_numbers:
            ca_str = str(ca).strip()
            for bill_month in bill_months:
                try:
                    if mode.upper() == "LT":
                        enc_ca = _cryptojs_compat_aes_cbc_base64(ca_str)
                        enc_month = _cryptojs_compat_aes_cbc_base64(bill_month)
                        form = {
                            "uiActionName": "getLTEnergyBillPage",
                            "hdnConsumerNumber": enc_ca,
                            "isViaForm": "Y",
                            "hdnBillMonth": enc_month,
                            "hdnPC": "3",
                            "hdnFreezeCode": "0",
                            "consumerType": "1",
                            "billingNo": "-1",
                            "ddlCircleCode": "-1",
                        }
                        r = s.post(base_url, headers=headers_base, data=form, timeout=60)
                        if r.status_code != 200 or "<html" not in r.text.lower():
                            snippet = r.text[:180].replace("\n"," ").replace("\r"," ")
                            _log(session_id, f"✗ {ca_str} ({bill_month}): LT HTML not returned (HTTP {r.status_code}). Snippet: {snippet}")
                            raise RuntimeError("LT HTML not returned")
                        extracted = _extract_new_bill_container(r.text, bill_not_found_check)
                        pdf = _render_html_to_pdf_bytes(extracted)
                        fname = f"MSEDCL_LT_{ca_str}_{bill_month.replace(' ','_')}.pdf"
                        # Rename with extracted date
                        fname = rename_pdf_with_date(fname, pdf, "MSEDCL")
                        downloads[session_id]["files"][fname] = pdf
                        _log(session_id, f"✓ {ca_str} ({bill_month}) [LT]: PDF generated ({len(pdf)} bytes) - {fname}")

                    elif mode.upper() == "HT":
                        if not cookie_header:
                            _log(session_id, f"✗ {ca_str} ({bill_month}): Cookie required for HT (valid ~15 min)")
                            raise RuntimeError("Cookie missing")
                        headers_ht = headers_base.copy()
                        headers_ht["Cookie"] = cookie_header
                        form = {
                            "hdnConsumerNumber": ca_str,
                            "hdnBillMonth": bill_month,
                            "uiActionName": "getHTEnergyBill",
                        }
                        r = s.post(base_url, headers=headers_ht, data=form, timeout=60)
                        if r.status_code != 200 or "<html" not in r.text.lower():
                            snippet = r.text[:180].replace("\n"," ").replace("\r"," ")
                            _log(session_id, f"✗ {ca_str} ({bill_month}): HT HTML not returned (HTTP {r.status_code}). Snippet: {snippet}")
                            raise RuntimeError("HT HTML not returned")
                        extracted = _extract_new_bill_container(r.text, bill_not_found_check)
                        pdf = _render_html_to_pdf_bytes(extracted)
                        fname = f"MSEDCL_HT_{ca_str}_{bill_month.replace(' ','_')}.pdf"
                        # Rename with extracted date
                        fname = rename_pdf_with_date(fname, pdf, "MSEDCL")
                        downloads[session_id]["files"][fname] = pdf
                        _log(session_id, f"✓ {ca_str} ({bill_month}) [HT]: PDF generated ({len(pdf)} bytes) - {fname}")

                    elif mode.upper() == "HT2":
                        if not bu_map or ca_str not in bu_map:
                            _log(session_id, f"✗ {ca_str}: BU/Circle id missing. Provide mapping like '170019088370: 517'.")
                            raise RuntimeError("BU missing")
                        bu = str(bu_map[ca_str]).strip()
                        form = {
                            "sortBy": "BILL_MTH",
                            "sortCriteria": "desc",
                            "isLT": "N",
                            "IS_LT_BILL_PDF": "Y",
                            "IS_HT_BILL_PDF": "Y",
                            "uiActionName": "getHTEnergyBillPagePDFPrint",
                            "hdnConsumerNumber": ca_str,
                            "hdnBillMonth": bill_month,
                            "hdnBU": bu,
                            "_xpf": "",
                            "_xpt": "1",
                            "_xf": "pdf",
                            "billmnthArr": "",
                            "billAmntArr": "",
                            "billConsumpArr": ""
                        }
                        r = s.post(base_url, headers=headers_base, data=form, timeout=60)
                        if r.status_code != 200:
                            _log(session_id, f"✗ {ca_str}: HT2 init failed (HTTP {r.status_code})")
                            raise RuntimeError("HT2 init failed")

                        time.sleep(2.0)
                        yyyymm = _bill_month_to_yyyymm(bill_month)
                        pdf_url = f"https://wss.mahadiscom.in/wss/HTBillPDF/{bu}_{ca_str}_{yyyymm}.PDF"
                        pr = s.get(pdf_url, timeout=60)
                        if pr.status_code == 200 and len(pr.content) > 500:
                            fname = f"MSEDCL_HT2_{ca_str}_{bill_month.replace(' ', '_')}.pdf"
                            # Rename with extracted date
                            fname = rename_pdf_with_date(fname, pr.content, "MSEDCL")
                            downloads[session_id]["files"][fname] = pr.content
                            _log(session_id, f"✓ {ca_str} [HT2]: Downloaded ({len(pr.content)} bytes) - {fname}")
                        else:
                            _log(session_id, f"✗ {ca_str} [HT2]: PDF not returned (HTTP {pr.status_code})")
                            raise RuntimeError("HT2 PDF not returned")

                    else:
                        _log(session_id, f"✗ {ca_str}: Invalid mode '{mode}'")
                        raise RuntimeError("Bad mode")

                except Exception as e:
                    error_msg = str(e)[:160]
                    _log(session_id, f"✗ {ca_str}: {error_msg}")

                downloads[session_id]["completed"] += 1
                downloads[session_id]["progress"] = int(downloads[session_id]["completed"] * 100 / downloads[session_id]["total"])

        downloads[session_id]["status"] = "completed"
    except Exception as e:
        downloads[session_id]["status"] = "error"
        _log(session_id, f"Error: {str(e)}")


# -------------------- Madhya Pradesh Poorva Kshetra DISCOM --------------------
def download_mp_poorva_kshetra(ca_numbers, bill_months, session_id):
    """
    Download bills from MP Poorva Kshetra DISCOM (MPEZ/MPPKVVCL)
    """
    # Handle both single month (string) and multiple months (list) for backward compatibility
    if isinstance(bill_months, str):
        bill_months = [bill_months]
    if not bill_months:
        bill_months = [datetime.now().strftime("%Y-%m")]
    
    total_requests = len(ca_numbers) * len(bill_months)
    downloads[session_id] = {
        "status": "downloading",
        "progress": 0,
        "completed": 0,
        "total": total_requests,
        "logs": [],
        "files": {}
    }

    def log(m): _log(session_id, m)

    BASE_URL = "https://billing.mpez.co.in/"
    ENDPOINT = "NGBReport"

    def normalize_ivrs(raw: str) -> str:
        """Remove 'N' prefix and keep only digits"""
        s = raw.strip().upper()
        if s.startswith("N"):
            s = s[1:]
        return "".join(ch for ch in s if ch.isdigit())

    def build_txtdate(year: int, month: int) -> str:
        """Build date string in format YYYYMM01"""
        return f"{year:04d}{month:02d}01"

    s = requests.Session()
    s.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36',
        'Referer': BASE_URL.rstrip("/"),
        'Origin': BASE_URL.rstrip("/")
    })

    for ca_number in ca_numbers:
        ca_number = str(ca_number).strip()
        for bill_month in bill_months:
            try:
                log(f"Processing CA: {ca_number} for {bill_month} (MP Poorva Kshetra)")

                # Parse bill month (format: YYYY-MM)
                try:
                    year_str, month_str = bill_month.split("-")
                    year, month = int(year_str), int(month_str)
                    if not (1 <= month <= 12):
                        raise ValueError("Invalid month")
                except Exception as e:
                    log(f"✗ Invalid bill month format: {bill_month}. Use YYYY-MM (e.g., 2025-10)")
                    downloads[session_id]["completed"] += 1
                    downloads[session_id]["progress"] = int(downloads[session_id]["completed"] * 100 / total_requests)
                    continue

                # Normalize CA number
                ivrs = normalize_ivrs(ca_number)
                log(f"Normalized IVRS: {ivrs}")

                # Build request
                url = f"{BASE_URL}{ENDPOINT}"
                payload = {
                    "ivrs": ivrs,
                    "txtDate": build_txtdate(year, month)
                }

                # Try to fetch PDF (with retry)
                pdf_data = None
                last_error = None

                for attempt in range(2):  # 2 attempts
                    try:
                        response = s.post(url, data=payload, timeout=30, allow_redirects=True)

                        if response.status_code == 200:
                            content = response.content

                            # Check if it's a PDF
                            if content[:5] == b'%PDF-':
                                pdf_data = content
                                break
                            
                            # Check content type
                            content_type = response.headers.get('Content-Type', '').lower()
                            if 'pdf' in content_type:
                                pdf_data = content
                                break
                            
                            last_error = f"Not a PDF (Content-Type: {content_type or 'unknown'})"
                        else:
                            last_error = f"HTTP {response.status_code}"

                    except requests.exceptions.Timeout:
                        last_error = "Request timeout"
                    except requests.exceptions.RequestException as e:
                        last_error = f"Network error: {str(e)[:50]}"

                    if attempt == 0 and not pdf_data:
                        time.sleep(1)  # Wait before retry

                if pdf_data and len(pdf_data) > 1000:
                    # Save PDF
                    filename = f"MPPK_{ivrs}_{year:04d}-{month:02d}.pdf"
                    # Rename with extracted date
                    filename = rename_pdf_with_date(filename, pdf_data, "MPPK")
                    downloads[session_id]["files"][filename] = pdf_data
                    log(f"✓ {ca_number} ({bill_month}): Downloaded ({len(pdf_data)} bytes) - {filename}")
                else:
                    log(f"✗ {ca_number} ({bill_month}): {last_error or 'No PDF received'}")

            except Exception as e:
                log(f"✗ {ca_number} ({bill_month}): {str(e)[:120]}")

            downloads[session_id]["completed"] += 1
            downloads[session_id]["progress"] = int(downloads[session_id]["completed"] * 100 / total_requests)

            # Small delay between requests
            time.sleep(1)

    downloads[session_id]["status"] = "completed"


# -------------------- UPCL DISCOM --------------------
def download_upcl_discom(account_numbers, session_id):
    """
    Download bills from UPCL (Uttarakhand Power Corporation Limited)
    Simple direct download from API endpoint
    """
    downloads[session_id] = {
        "status": "downloading",
        "progress": 0,
        "completed": 0,
        "total": len(account_numbers),
        "logs": [],
        "files": {}
    }

    def log(m): _log(session_id, m)

    BASE_URL = "https://www.upcl.org/wssservices/api/v1/downloadNewBill?accountNumber="

    s = requests.Session()
    s.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36'
    })

    for idx, account_number in enumerate(account_numbers):
        account_number = str(account_number).strip()
        try:
            log(f"Processing Account: {account_number} (UPCL)")

            # Build download URL
            download_url = f"{BASE_URL}{account_number}"
            log(f"Downloading from: {download_url}")

            # Download the bill
            response = s.get(download_url, timeout=60, allow_redirects=True)

            if response.status_code == 200:
                # Check if response is actually a PDF
                content_type = response.headers.get('content-type', '').lower()
                content = response.content

                # Verify it's a PDF
                if content[:4] == b'%PDF' or 'application/pdf' in content_type:
                    if len(content) > 1000:  # Valid PDF should be larger than 1KB
                        # Always use clean filename format: Uttarakhand_AccountNumber.pdf
                        filename = f"Uttarakhand_{account_number}.pdf"
                        # Rename with extracted date
                        filename = rename_pdf_with_date(filename, content, "Uttarakhand")

                        downloads[session_id]["files"][filename] = content
                        log(f"✓ {account_number}: Downloaded ({len(content)} bytes) - {filename}")
                    else:
                        log(f"✗ {account_number}: PDF too small ({len(content)} bytes), likely error")
                else:
                    # Not a PDF, might be error message
                    try:
                        error_text = content.decode('utf-8')[:200]
                        if 'error' in error_text.lower() or 'not found' in error_text.lower():
                            log(f"✗ {account_number}: {error_text}")
                        else:
                            log(f"✗ {account_number}: Response is not a PDF")
                    except:
                        log(f"✗ {account_number}: Invalid response (not a PDF)")
            else:
                log(f"✗ {account_number}: HTTP {response.status_code}")

        except requests.exceptions.Timeout:
            log(f"✗ {account_number}: Request timeout")
        except requests.exceptions.RequestException as e:
            log(f"✗ {account_number}: Network error - {str(e)[:100]}")
        except Exception as e:
            log(f"✗ {account_number}: {str(e)[:120]}")

        downloads[session_id]["completed"] += 1
        downloads[session_id]["progress"] = int(downloads[session_id]["completed"] * 100 / downloads[session_id]["total"])

        # Small delay between requests
        if idx < len(account_numbers) - 1:
            time.sleep(1)

    downloads[session_id]["status"] = "completed"


# -------------------- UPPCL DISCOM --------------------
def download_uppcl_discom(board, ca_numbers, bill_months, session_id):
    try:
        import base64
    except Exception as e:
        downloads[session_id] = {
            "status": "error",
            "logs": [f"Missing dependencies: {str(e)}"]
        }
        return

    # Handle both single month (string) and multiple months (list) for backward compatibility
    if isinstance(bill_months, str):
        bill_months = [bill_months]
    if not bill_months:
        bill_months = [datetime.now().strftime("%Y-%m")]

    total_requests = len(ca_numbers) * len(bill_months)
    downloads[session_id] = {
        "status": "downloading",
        "progress": 0,
        "completed": 0,
        "total": total_requests,
        "logs": [],
        "files": {}
    }

    def log(m): _log(session_id, m)

    BOARDS = {
        'mvvnl': {
            'get_bill_details_url': 'https://mvvnlbill.uppclonline.com/APDRP/Billing/Services/BillingRPS/GetBillDetails',
            'bill_view_url': 'https://mvvnlbill.uppclonline.com/Ext/Service/RPS/BillView',
            'name': 'MVVNL'
        },
        'dvvnl': {
            'get_bill_details_url': 'https://dvvnlbill.uppclonline.com/APDRP/Billing/Services/BillingRPS/GetBillDetails',
            'bill_view_url': 'https://dvvnlbill.uppclonline.com/Ext/Service/RPS/BillView',
            'name': 'DVVNL'
        },
        'pvvnl': {
            'get_bill_details_url': 'https://pvvnlbill.uppclonline.com/APDRP/Billing/Services/BillingRPS/GetBillDetails',
            'bill_view_url': 'https://pvvnlbill.uppclonline.com/Ext/Service/RPS/BillView',
            'name': 'PVVNL'
        },
        'pu': {
            'get_bill_details_url': 'https://pubill.uppclonline.com/APDRP/Billing/Services/BillingRPS/GetBillDetails',
            'bill_view_url': 'https://pubill.uppclonline.com/Ext/Service/RPS/BillView',
            'name': 'PU'
        },
        'kesco': {
            'get_bill_details_url': 'https://kescobill.uppclonline.com/APDRP/Billing/Services/BillingRPS/GetBillDetails',
            'bill_view_url': 'https://kescobill.uppclonline.com/Ext/Service/RPS/BillView',
            'name': 'KESCO'
        }
    }

    HEADERS = {
        'Authorization': 'Basic TU9CQVBJVVNFUjo3NCMhMSQwZCFrbThRUg==',
        'Content-Type': 'application/json'
    }

    if board not in BOARDS:
        log(f"✗ Invalid board: {board}")
        downloads[session_id]["status"] = "error"
        return

    board_config = BOARDS[board]
    board_name = board_config['name']

    s = requests.Session()

    for ca_number in ca_numbers:
        ca_number = str(ca_number).strip()
        for bill_month in bill_months:
            try:
                log(f"Processing CA: {ca_number} for {bill_month} ({board_name})")

                # Parse bill month (format: YYYY-MM)
                try:
                    year, month = bill_month.split('-')
                    from_date = f"01-{month}-{year}"
                    import calendar
                    last_day = calendar.monthrange(int(year), int(month))[1]
                    to_date = f"{last_day}-{month}-{year}"
                    log(f"📅 Searching for bills: {from_date} to {to_date}")
                except Exception as e:
                    log(f"✗ Invalid bill month format: {bill_month}")
                    downloads[session_id]["completed"] += 1
                    downloads[session_id]["progress"] = int(downloads[session_id]["completed"] * 100 / total_requests)
                    continue

                # Step 1: Get bill details
                payload1 = {
                    "KNumber": ca_number,
                    "SearchParameters": {
                        "DateRange": {
                            "FromDate": from_date,
                            "ToDate": to_date
                        }
                    }
                }

                r1 = s.post(board_config['get_bill_details_url'], 
                           json=payload1, 
                           headers=HEADERS, 
                           timeout=30)

                if r1.status_code != 200:
                    log(f"✗ {ca_number} ({bill_month}): HTTP {r1.status_code}")
                    downloads[session_id]["completed"] += 1
                    downloads[session_id]["progress"] = int(downloads[session_id]["completed"] * 100 / total_requests)
                    continue

                bill_details_response = r1.json()

                if bill_details_response.get('ResCode') != '1':
                    msg = bill_details_response.get('ResMsg', 'Unknown error')
                    if 'no bill' in msg.lower():
                        log(f"⚠ {ca_number} ({bill_month}): No bills found")
                    else:
                        log(f"✗ {ca_number} ({bill_month}): {msg}")
                    downloads[session_id]["completed"] += 1
                    downloads[session_id]["progress"] = int(downloads[session_id]["completed"] * 100 / total_requests)
                    continue

                bill_details = bill_details_response.get('BillDetails', [])
                if not bill_details:
                    log(f"⚠ {ca_number} ({bill_month}): No bill details")
                    downloads[session_id]["completed"] += 1
                    downloads[session_id]["progress"] = int(downloads[session_id]["completed"] * 100 / total_requests)
                    continue

                first_bill = bill_details[0]
                bill_info = first_bill.get('BillInfo', {})
                bill_no = bill_info.get('BillNo')
                bill_month_year = first_bill.get('BillMonthYear')

                if not bill_no or not bill_month_year:
                    log(f"✗ {ca_number} ({bill_month}): Invalid bill data")
                    downloads[session_id]["completed"] += 1
                    downloads[session_id]["progress"] = int(downloads[session_id]["completed"] * 100 / total_requests)
                    continue

                # Step 2: Get bill PDF
                payload2 = {
                    "BillId": bill_no,
                    "Flag": "BILL"
                }

                r2 = s.post(board_config['bill_view_url'], 
                           json=payload2, 
                           headers=HEADERS, 
                           timeout=30)

                if r2.status_code != 200:
                    log(f"✗ {ca_number} ({bill_month}): PDF HTTP {r2.status_code}")
                    downloads[session_id]["completed"] += 1
                    downloads[session_id]["progress"] = int(downloads[session_id]["completed"] * 100 / total_requests)
                    continue

                bill_view_response = r2.json()

                if bill_view_response.get('ResCode') != '1':
                    log(f"✗ {ca_number} ({bill_month}): {bill_view_response.get('ResMsg', 'PDF error')}")
                    downloads[session_id]["completed"] += 1
                    downloads[session_id]["progress"] = int(downloads[session_id]["completed"] * 100 / total_requests)
                    continue

                base64_pdf = bill_view_response.get('ReportContents')
                if not base64_pdf:
                    log(f"✗ {ca_number} ({bill_month}): No PDF content")
                    downloads[session_id]["completed"] += 1
                    downloads[session_id]["progress"] = int(downloads[session_id]["completed"] * 100 / total_requests)
                    continue

                # Decode PDF
                pdf_bytes = base64.b64decode(base64_pdf)

                # Create filename
                parts = bill_month_year.split('-')
                if len(parts) == 3:
                    mm, yyyy = parts[1], parts[2]
                else:
                    mm, yyyy = month, year

                filename = f"{mm}_{yyyy}_{board}_{ca_number}_{bill_no}.pdf"
                # Rename with extracted date
                filename = rename_pdf_with_date(filename, pdf_bytes, board.upper())
                downloads[session_id]["files"][filename] = pdf_bytes

                log(f"✓ {ca_number} ({bill_month}): Downloaded ({len(pdf_bytes)} bytes) - {filename}")

            except Exception as e:
                log(f"✗ {ca_number} ({bill_month}): {str(e)[:120]}")

            downloads[session_id]["completed"] += 1
            downloads[session_id]["progress"] = int(downloads[session_id]["completed"] * 100 / total_requests)
            
            # Add delay between requests
            time.sleep(2)

    downloads[session_id]["status"] = "completed"


# -------------------- Goa DISCOM --------------------
def download_goa_discom(login_id, password, bill_numbers, session_id):
    try:
        from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
        from urllib.parse import urlsplit, urlunsplit, parse_qsl
        from pypdf import PdfReader, PdfWriter
        import pathlib
    except Exception as e:
        downloads[session_id] = {
            "status": "error",
            "logs": [f"Missing dependencies: {str(e)}. Install: pip install playwright pypdf"]
        }
        return

    downloads[session_id] = {
        "status": "downloading",
        "progress": 0,
        "completed": 0,
        "total": len(bill_numbers),
        "logs": [],
        "files": {}
    }

    def log(m): _log(session_id, m)

    LOGIN_URL = "https://consumer.goaelectricity.gov.in:44302/bdisu/public/frameset_top_html.jsp"
    PDF_BASE_URL = ("https://consumer.goaelectricity.gov.in:44302/bdisu/getpdfbill.sap"
                    "?doAction=searchBill&singleBillIdx=0&searchDateId=365&billType=3"
                    "&opt_Bill=X&opt_Inst=&opt_Bills=Request"
                    "&pdfbill_num=010300081302"
                    "&pdfinstallbill_num="
                    "&BP_Pdf=1000148580"
                    "&download.x=6&download.y=10")

    MONTH_MAP = {
        "jan": 1, "january": 1, "feb": 2, "february": 2, "mar": 3, "march": 3,
        "apr": 4, "april": 4, "may": 5, "jun": 6, "june": 6, "jul": 7, "july": 7,
        "aug": 8, "august": 8, "sep": 9, "sept": 9, "september": 9,
        "oct": 10, "october": 10, "nov": 11, "november": 11, "dec": 12, "december": 12,
    }

    def build_pdf_url(bill_no: str) -> str:
        parts = urlsplit(PDF_BASE_URL)
        q = dict(parse_qsl(parts.query, keep_blank_values=True))
        q["pdfbill_num"] = bill_no
        new_query = "&".join(f"{k}={v}" for k, v in q.items())
        return urlunsplit((parts.scheme, parts.netloc, parts.path, new_query, parts.fragment))

    def parse_month_year(text: str):
        if not text:
            return None
        t = " ".join(text.split())
        m = re.search(r"(?:BILL\s*MONTH|Bill\s*Month|BillMonth)\s*[:\-]?\s*([A-Za-z]{3,9})\s*[-/\s]?\s*(\d{2,4})", t, re.I)
        if m:
            mon_raw, y_raw = m.group(1).lower(), m.group(2)
            mm = MONTH_MAP.get(mon_raw)
            if mm:
                yyyy = int(y_raw)
                if yyyy < 100:
                    yyyy += 2000
                return yyyy, mm
        return None

    def split_pdf_bytes(pdf_bytes: bytes, bill_no: str):
        saved = {}
        try:
            from io import BytesIO
            reader = PdfReader(BytesIO(pdf_bytes))
            total = len(reader.pages)
            for idx in range(total):
                page = reader.pages[idx]
                try:
                    text = page.extract_text() or ""
                except Exception:
                    text = ""
                ym = parse_month_year(text)
                if ym:
                    yyyy, mm = ym
                    base_name = f"{bill_no}_{yyyy:04d}-{mm:02d}.pdf"
                else:
                    base_name = f"{bill_no}_page{idx+1:02d}.pdf"
                
                writer = PdfWriter()
                writer.add_page(page)
                pdf_buffer = BytesIO()
                writer.write(pdf_buffer)
                saved[base_name] = pdf_buffer.getvalue()
        except Exception as e:
            log(f"✗ {bill_no}: Split failed - {str(e)[:100]}")
        return saved

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"])
            context = browser.new_context(accept_downloads=True, ignore_https_errors=True)
            page = context.new_page()

            # Login
            page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=60000)
            
            def find_login_frame():
                for _ in range(40):
                    for f in page.frames:
                        try:
                            if f.locator("#logonuidfield").count() and f.locator("#logonpassfield").count():
                                return f
                        except Exception:
                            pass
                    page.wait_for_timeout(250)
                return None

            login_frame = find_login_frame()
            if not login_frame:
                log("✗ Could not find login fields")
                downloads[session_id]["status"] = "error"
                browser.close()
                return

            login_frame.fill("#logonuidfield", login_id)
            login_frame.fill("#logonpassfield", password)
            if login_frame.locator("#uidPasswordLogon").count():
                login_frame.click("#uidPasswordLogon")
            else:
                login_frame.press("#logonpassfield", "Enter")

            page.wait_for_load_state("networkidle", timeout=30000)
            time.sleep(1.5)

            # Download bills
            request_ctx = p.request.new_context(
                ignore_https_errors=True,
                storage_state=context.storage_state()
            )

            for bill in bill_numbers:
                bill = str(bill).strip()
                url = build_pdf_url(bill)
                try:
                    resp = request_ctx.get(url, timeout=120_000)
                    if not resp.ok:
                        log(f"✗ {bill}: HTTP {resp.status}")
                        continue

                    ctype = (resp.headers.get("content-type") or "").lower()
                    body = resp.body()
                    looks_pdf = body[:4] == b"%PDF"

                    if "application/pdf" in ctype or looks_pdf:
                        # Split by month
                        parts = split_pdf_bytes(body, bill)
                        if parts:
                            for name, data in parts.items():
                                downloads[session_id]["files"][name] = data
                            log(f"✓ {bill}: Downloaded and split into {len(parts)} files")
                        else:
                            # Fallback: save as single file
                            downloads[session_id]["files"][f"GoaDISCOM_{bill}.pdf"] = body
                            log(f"✓ {bill}: Downloaded ({len(body)} bytes)")
                    else:
                        log(f"✗ {bill}: Response was not a PDF")
                except Exception as e:
                    log(f"✗ {bill}: {str(e)[:120]}")

                downloads[session_id]["completed"] += 1
                downloads[session_id]["progress"] = int(downloads[session_id]["completed"] * 100 / downloads[session_id]["total"])

            request_ctx.dispose()
            browser.close()

        downloads[session_id]["status"] = "completed"
    except Exception as e:
        downloads[session_id]["status"] = "error"
        log(f"Error: {str(e)}")


# -------------------- Dakshin Gujarat DISCOM --------------------
def download_dakshin_gujarat(ca_numbers, session_id):
    """
    Download bills from Dakshin Gujarat DISCOM with captcha solving
    """
    try:
        from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
        import base64
    except Exception as e:
        downloads[session_id] = {
            "status": "error",
            "logs": [f"Missing dependencies: {str(e)}. Install: pip install playwright"]
        }
        return

    downloads[session_id] = {
        "status": "downloading",
        "progress": 0,
        "completed": 0,
        "total": len(ca_numbers),
        "logs": [],
        "files": {}
    }

    def log(m): _log(session_id, m)

    CAPSOLVER_API_KEY = "CAP-ADCA94D1B80ACF6A5A0E9E57B4E90158"
    BASE_URL = "https://bps.dgvcl.co.in/BillDetail/index.php"

    def solve_captcha_with_capsolver(image_base64):
        """Solve captcha using CapSolver API"""
        try:
            log("🔍 Solving captcha with CapSolver...")
            
            # Remove data URL prefix if present
            if "," in image_base64 and image_base64.startswith("data:"):
                image_base64 = image_base64.split(",", 1)[1]
            
            # Validate base64 image
            if not image_base64 or len(image_base64) < 100:
                log(f"✗ Invalid captcha image (too short: {len(image_base64)} chars)")
                return None
            
            # Create task
            create_task_url = "https://api.capsolver.com/createTask"
            task_payload = {
                "clientKey": CAPSOLVER_API_KEY,
                "task": {
                    "type": "ImageToTextTask",
                    "body": image_base64,
                    "module": "common",
                    "score": 0.5,
                    "case": False
                }
            }
            
            log(f"📤 Sending captcha to CapSolver (image size: {len(image_base64)} chars)")
            response = requests.post(create_task_url, json=task_payload, timeout=30)
            
            # Check HTTP status
            if response.status_code != 200:
                log(f"✗ CapSolver HTTP error: {response.status_code}")
                log(f"Response: {response.text[:200]}")
                return None
            
            result = response.json()
            log(f"📥 CapSolver response: {result}")
            
            # Check for API errors
            error_id = result.get("errorId", -1)
            if error_id != 0:
                error_msg = result.get('errorDescription', 'Unknown error')
                error_code = result.get('errorCode', 'N/A')
                log(f"✗ CapSolver error (ID: {error_id}, Code: {error_code}): {error_msg}")
                
                # Provide helpful hints for common errors
                if "insufficient balance" in error_msg.lower() or "balance" in error_msg.lower():
                    log("💡 Hint: Check your CapSolver account balance at https://dashboard.capsolver.com/")
                elif "invalid" in error_msg.lower() and "key" in error_msg.lower():
                    log("💡 Hint: Verify your CapSolver API key is correct")
                
                return None
            
            # Check if solution is already in the response (fast solve)
            if result.get("status") == "ready":
                captcha_text = result.get("solution", {}).get("text", "")
                if captcha_text:
                    log(f"✓ Captcha solved immediately: '{captcha_text}'")
                    return captcha_text
                else:
                    log(f"✗ No text in immediate solution: {result}")
                    return None
            
            # Otherwise, get task ID and poll for result
            task_id = result.get("taskId")
            if not task_id:
                log("✗ No task ID received from CapSolver")
                return None
            
            log(f"⏳ Task ID: {task_id}, waiting for solution...")
            
            # Poll for result
            get_result_url = "https://api.capsolver.com/getTaskResult"
            for attempt in range(30):  # Try for up to 30 seconds
                time.sleep(1)
                result_payload = {
                    "clientKey": CAPSOLVER_API_KEY,
                    "taskId": task_id
                }
                
                response = requests.post(get_result_url, json=result_payload, timeout=30)
                
                if response.status_code != 200:
                    log(f"✗ CapSolver result HTTP error: {response.status_code}")
                    continue
                
                result = response.json()
                status = result.get("status", "")
                
                if status == "ready":
                    captcha_text = result.get("solution", {}).get("text", "")
                    if captcha_text:
                        log(f"✓ Captcha solved: '{captcha_text}'")
                        return captcha_text
                    else:
                        log(f"✗ No text in solution: {result}")
                        return None
                elif status == "processing":
                    if attempt % 5 == 0:
                        log(f"⏳ Still processing... (attempt {attempt}/30)")
                    continue
                elif status == "failed":
                    error_desc = result.get('errorDescription', 'Unknown')
                    log(f"✗ CapSolver task failed: {error_desc}")
                    return None
                else:
                    log(f"✗ Unknown CapSolver status: {status}, full response: {result}")
            
            log("✗ Captcha solving timeout after 30 seconds")
            return None
            
        except requests.exceptions.Timeout:
            log("✗ CapSolver API timeout - network issue or service is slow")
            return None
        except requests.exceptions.RequestException as e:
            log(f"✗ CapSolver network error: {str(e)[:200]}")
            return None
        except Exception as e:
            log(f"✗ Captcha solving error: {str(e)[:200]}")
            import traceback
            log(f"Traceback: {traceback.format_exc()[:300]}")
            return None

    for idx, ca_number in enumerate(ca_numbers):
        ca_number = str(ca_number).strip()
        pdf_data = None
        
        try:
            log(f"Processing CA: {ca_number} (Dakshin Gujarat)")
            
            with sync_playwright() as p:
                browser = p.chromium.launch(
                    headless=True,
                    args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-blink-features=AutomationControlled"]
                )
                context = browser.new_context(
                    accept_downloads=True,
                    ignore_https_errors=True,
                    user_agent=("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                                "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"),
                    viewport={"width": 1366, "height": 900}
                )
                context.add_init_script("Object.defineProperty(navigator,'webdriver',{get:()=>undefined})")
                
                page = context.new_page()
                
                # Navigate to the page
                log(f"Loading page for CA: {ca_number}")
                page.goto(BASE_URL, wait_until="domcontentloaded", timeout=60000)
                
                # Wait for page to load
                try:
                    page.wait_for_selector("#consumerno", timeout=10000)
                except:
                    log(f"✗ {ca_number}: Page load timeout")
                    browser.close()
                    continue
                
                # Enter consumer number
                log(f"Entering consumer number: {ca_number}")
                page.fill("#consumerno", ca_number)
                
                # Get captcha image
                try:
                    page.wait_for_selector("#captchaimg", timeout=5000)
                    captcha_element = page.query_selector("#captchaimg")
                    
                    if captcha_element:
                        # Get captcha image as base64
                        captcha_src = captcha_element.get_attribute("src")
                        log(f"Captcha src attribute: {captcha_src[:100] if captcha_src else 'None'}...")
                        
                        image_base64 = None
                        
                        if captcha_src and captcha_src.startswith("data:image"):
                            # Extract base64 from data URL
                            image_base64 = captcha_src.split(",")[1]
                            log(f"Extracted base64 from data URL (length: {len(image_base64)})")
                        elif captcha_src:
                            # Download captcha image
                            try:
                                # Build full URL
                                if captcha_src.startswith("http"):
                                    captcha_url = captcha_src
                                elif captcha_src.startswith("/"):
                                    from urllib.parse import urlparse
                                    parsed = urlparse(page.url)
                                    captcha_url = f"{parsed.scheme}://{parsed.netloc}{captcha_src}"
                                else:
                                    captcha_url = page.url.rsplit("/", 1)[0] + "/" + captcha_src
                                
                                log(f"Downloading captcha from: {captcha_url}")
                                response = context.request.get(captcha_url)
                                
                                if response.ok:
                                    image_bytes = response.body()
                                    image_base64 = base64.b64encode(image_bytes).decode('utf-8')
                                    log(f"Downloaded captcha image ({len(image_bytes)} bytes, base64: {len(image_base64)} chars)")
                                else:
                                    log(f"✗ Failed to download captcha: HTTP {response.status}")
                            except Exception as e:
                                log(f"✗ Error downloading captcha: {str(e)[:100]}")
                        else:
                            log("✗ Captcha src is empty or invalid")
                        
                        if not image_base64:
                            log(f"✗ {ca_number}: Could not extract captcha image")
                            browser.close()
                            continue
                        
                        # Solve captcha
                        captcha_text = solve_captcha_with_capsolver(image_base64)
                        
                        if not captcha_text:
                            log(f"✗ {ca_number}: Failed to solve captcha")
                            browser.close()
                            continue
                        
                        # Enter captcha
                        log(f"Entering captcha: {captcha_text}")
                        page.fill("#captcha", captcha_text)
                        
                        # Click submit button
                        log(f"Clicking submit button")
                        page.click("#sendotp")
                        
                        # Wait for navigation or response
                        try:
                            page.wait_for_load_state("networkidle", timeout=15000)
                        except:
                            pass
                        
                        # Check if we reached the bill page
                        time.sleep(2)
                        
                        # Check for error messages (wrong captcha, invalid CA, etc.)
                        error_selectors = [
                            'div.error', 'span.error', 'p.error',
                            'div[class*="error"]', 'span[class*="error"]',
                            'div.alert-danger', 'div.alert'
                        ]
                        
                        for selector in error_selectors:
                            error_element = page.query_selector(selector)
                            if error_element:
                                error_text = error_element.inner_text().strip()
                                if error_text:
                                    log(f"⚠ Error message on page: {error_text[:200]}")
                                    if "captcha" in error_text.lower():
                                        log(f"✗ {ca_number}: Captcha was incorrect")
                                        browser.close()
                                        continue
                                    break
                        
                        # Look for View Bill button or bill details
                        try:
                            # Wait a bit for page to update after captcha submission
                            time.sleep(3)
                            
                            log(f"Looking for View Bill button after captcha submission...")
                            
                            # Try to find and click View Bill button with specific selectors
                            view_bill_selectors = [
                                '.btn.btn-primary.btn-sm',  # Specific class from your screenshot
                                'a.btn.btn-primary.btn-sm',
                                'button.btn.btn-primary.btn-sm',
                                'a:has-text("View Bill")',  # Text-based selector
                                'button:has-text("View Bill")',
                                'a[normalize-space()="View Bill"]',  # XPath equivalent
                                'input[value*="View Bill"]',
                                'button:has-text("view bill")',
                                'a:has-text("view bill")',
                                'button[onclick*="bill"]',
                                'a[href*="bill"]',
                                'a[href*="billview"]',
                                '#viewbill',
                                '.viewbill'
                            ]
                            
                            view_bill_button = None
                            used_selector = None
                            for selector in view_bill_selectors:
                                try:
                                    view_bill_button = page.query_selector(selector)
                                    if view_bill_button:
                                        used_selector = selector
                                        log(f"✓ Found View Bill button with selector: {selector}")
                                        break
                                except:
                                    continue
                            
                            # If CSS selectors don't work, try XPath
                            if not view_bill_button:
                                try:
                                    log(f"Trying XPath selector...")
                                    view_bill_button = page.query_selector('xpath=//a[normalize-space()="View Bill"]')
                                    if view_bill_button:
                                        used_selector = 'xpath=//a[normalize-space()="View Bill"]'
                                        log(f"✓ Found View Bill button with XPath")
                                except:
                                    pass
                            
                            if view_bill_button:
                                log(f"Clicking View Bill button (selector: {used_selector})...")
                                
                                # Try to capture PDF from new page/popup
                                new_page = None
                                try:
                                    log(f"Waiting for new page to open...")
                                    with context.expect_page(timeout=15000) as popup:
                                        view_bill_button.click()
                                    new_page = popup.value
                                    log(f"✓ New window opened successfully")
                                except PWTimeout:
                                    log(f"⚠ No popup detected, clicking anyway...")
                                    try:
                                        view_bill_button.click()
                                    except:
                                        log(f"⚠ Normal click failed, trying JavaScript click...")
                                        page.evaluate("(el) => el.click()", view_bill_button)
                                    time.sleep(4)
                                    # Check if new page was opened
                                    if len(context.pages) > 1:
                                        new_page = context.pages[-1]
                                        log(f"✓ Found new page in context")
                                except Exception as e:
                                    log(f"⚠ Error during click: {str(e)[:100]}")
                                    try:
                                        view_bill_button.click()
                                    except:
                                        page.evaluate("(el) => el.click()", view_bill_button)
                                    time.sleep(4)
                                    if len(context.pages) > 1:
                                        new_page = context.pages[-1]
                                
                                target_page = new_page if new_page else page
                                log(f"Target page URL: {target_page.url}")
                                
                                # Wait for PDF to load
                                try:
                                    log(f"Waiting for page to load...")
                                    target_page.wait_for_load_state("domcontentloaded", timeout=10000)
                                    time.sleep(2)
                                    target_page.wait_for_load_state("networkidle", timeout=15000)
                                    log(f"✓ Page loaded")
                                except:
                                    log(f"⚠ Page load timeout, continuing...")
                                    time.sleep(3)
                                
                                # Try to get PDF content
                                # Method 1: Check if page URL is PDF
                                if "pdf" in target_page.url.lower() or target_page.url.endswith(".pdf") or "billview" in target_page.url.lower():
                                    try:
                                        log(f"Page appears to be PDF, fetching content...")
                                        response = context.request.get(target_page.url, timeout=30000)
                                        if response.ok:
                                            body = response.body()
                                            if body and len(body) > 500:
                                                # Check if it's actually a PDF
                                                if body[:4] == b'%PDF':
                                                    pdf_data = body
                                                    log(f"✓ PDF fetched from URL ({len(pdf_data)} bytes)")
                                                else:
                                                    log(f"⚠ Content is not PDF, will try other methods")
                                    except Exception as e:
                                        log(f"⚠ Error fetching PDF from URL: {str(e)[:100]}")
                                
                                # Method 2: Look for PDF embed/iframe/object
                                if not pdf_data:
                                    try:
                                        log(f"Looking for PDF embed elements...")
                                        time.sleep(2)
                                        
                                        pdf_selectors = [
                                            'embed[type="application/pdf"]',
                                            'object[type="application/pdf"]',
                                            'iframe[src*=".pdf"]',
                                            'embed[src*=".pdf"]',
                                            'object[data*=".pdf"]',
                                            'embed',
                                            'object[data]',
                                            'iframe'
                                        ]
                                        
                                        for selector in pdf_selectors:
                                            pdf_element = target_page.query_selector(selector)
                                            if pdf_element:
                                                pdf_src = pdf_element.get_attribute("src") or pdf_element.get_attribute("data")
                                                if pdf_src:
                                                    log(f"Found PDF element '{selector}' with src: {pdf_src[:100]}")
                                                    from urllib.parse import urljoin
                                                    pdf_url = urljoin(target_page.url, pdf_src)
                                                    log(f"Fetching PDF from: {pdf_url}")
                                                    response = context.request.get(pdf_url, timeout=30000)
                                                    if response.ok:
                                                        body = response.body()
                                                        if body and len(body) > 500:
                                                            if body[:4] == b'%PDF':
                                                                pdf_data = body
                                                                log(f"✓ PDF fetched from {selector} ({len(pdf_data)} bytes)")
                                                                break
                                                            else:
                                                                log(f"⚠ Content from {selector} is not PDF")
                                        
                                        if not pdf_data:
                                            log(f"⚠ No PDF embed elements found")
                                    except Exception as e:
                                        log(f"⚠ Error finding PDF embed: {str(e)[:100]}")
                                
                                # Method 3: Print page as PDF (last resort)
                                if not pdf_data:
                                    try:
                                        log(f"Generating PDF from page content as last resort...")
                                        pdf_data = target_page.pdf(
                                            format="A4",
                                            print_background=True,
                                            margin={"top": "0.5cm", "right": "0.5cm", "bottom": "0.5cm", "left": "0.5cm"}
                                        )
                                        log(f"✓ PDF generated from page ({len(pdf_data)} bytes)")
                                    except Exception as e:
                                        log(f"✗ PDF generation failed: {str(e)[:100]}")
                                
                                # Close new page if it was opened
                                if new_page:
                                    try:
                                        new_page.close()
                                        log(f"Closed new window")
                                    except:
                                        pass
                            else:
                                log(f"✗ View Bill button not found on page")
                                log(f"Page URL: {page.url}")
                                log(f"Page title: {page.title()}")
                                
                                # Check if bill summary is displayed
                                bill_summary = page.query_selector('div:has-text("Consumer No"), div:has-text("Bill Date"), div:has-text("Due Date")')
                                if bill_summary:
                                    log(f"⚠ Bill summary found but no View Bill button, generating PDF from current page...")
                                    try:
                                        pdf_data = page.pdf(
                                            format="A4",
                                            print_background=True,
                                            margin={"top": "0.5cm", "right": "0.5cm", "bottom": "0.5cm", "left": "0.5cm"}
                                        )
                                        log(f"✓ PDF generated from current page ({len(pdf_data)} bytes)")
                                    except Exception as e:
                                        log(f"✗ PDF generation failed: {str(e)[:100]}")
                                else:
                                    log(f"✗ No bill information found on page")
                        
                        except Exception as e:
                            log(f"✗ {ca_number}: Error in bill capture process - {str(e)[:100]}")
                            import traceback
                            log(f"Traceback: {traceback.format_exc()[:300]}")
                    
                    else:
                        log(f"✗ {ca_number}: Captcha image not found")
                
                except Exception as e:
                    log(f"✗ {ca_number}: Captcha handling error - {str(e)[:100]}")
                
                browser.close()
        
        except Exception as e:
            log(f"✗ {ca_number}: {str(e)[:160]}")
        
        if pdf_data and len(pdf_data) > 500:
            filename = f"DGVCL_{ca_number}.pdf"
            # Rename with extracted date
            filename = rename_pdf_with_date(filename, pdf_data, "DGVCL")
            downloads[session_id]["files"][filename] = pdf_data
            log(f"✓ {ca_number}: Downloaded ({len(pdf_data)} bytes) - {filename}")
        else:
            log(f"✗ {ca_number}: Could not capture PDF")
        
        downloads[session_id]["completed"] += 1
        downloads[session_id]["progress"] = int(downloads[session_id]["completed"] * 100 / downloads[session_id]["total"])
        
        # Small delay between requests
        if idx < len(ca_numbers) - 1:
            time.sleep(2)
    
    downloads[session_id]["status"] = "completed"


# -------------------- Madhya Pradesh Madhya Kshetra DISCOM --------------------
def download_mp_madhya_kshetra(ca_numbers, session_id):
    """
    Download bills from MP Madhya Kshetra DISCOM
    URL: https://resourceutils.mpcz.in:8090/payBill
    """
    try:
        from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
    except Exception:
        downloads[session_id] = {
            "status": "error",
            "logs": ["Playwright not installed. Run: pip install playwright && playwright install chromium"]
        }
        return

    downloads[session_id] = {
        "status": "downloading",
        "progress": 0,
        "completed": 0,
        "total": len(ca_numbers),
        "logs": [],
        "files": {}
    }

    def log(m): _log(session_id, m)

    for ca in ca_numbers:
        ca = str(ca).strip()
        pdf_data = None
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(
                    headless=True,
                    args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-blink-features=AutomationControlled"]
                )
                context = browser.new_context(
                    accept_downloads=True,
                    ignore_https_errors=True,
                    user_agent=("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                                "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"),
                    viewport={"width": 1366, "height": 900}
                )
                context.add_init_script("Object.defineProperty(navigator,'webdriver',{get:()=>undefined})")

                page = context.new_page()
                url = "https://resourceutils.mpcz.in:8090/payBill"
                
                log(f"Loading bill page for CA: {ca}")
                page.goto(url, wait_until="domcontentloaded", timeout=60000)

                # Wait for page to load
                try:
                    page.wait_for_load_state("networkidle", timeout=10000)
                except:
                    pass

                # Enter CA number in the input field
                try:
                    log(f"Entering CA number: {ca}")
                    # Wait for the page to be fully loaded
                    page.wait_for_timeout(2000)
                    
                    # Try multiple selector strategies for the input field
                    input_selectors = [
                        'input[type="text"]',
                        'input.MuiInputBase-input',
                        'div.MuiInputBase-root input',
                        'input[id^=":r"]',  # MUI generated IDs start with :r
                        'input[placeholder*="CA"]',
                        'input[placeholder*="Consumer"]',
                        'input[placeholder*="Account"]',
                        'input',  # Last resort - any input
                    ]
                    
                    input_found = False
                    for selector in input_selectors:
                        try:
                            if page.locator(selector).count() > 0:
                                page.locator(selector).first.fill(ca)
                                input_found = True
                                log(f"Input field found with selector: {selector}")
                                break
                        except:
                            continue
                    
                    if not input_found:
                        log(f"✗ {ca}: Could not find input field")
                        raise Exception("Could not find input field with any selector")
                    
                    # Wait a bit for the input to register
                    page.wait_for_timeout(1500)
                    
                except Exception as e:
                    log(f"✗ {ca}: Failed to enter CA number - {str(e)[:100]}")
                    browser.close()
                    continue

                # Click the search button
                try:
                    log(f"Clicking search button for CA: {ca}")
                    
                    # Try multiple button selectors
                    button_selectors = [
                        'button:has-text("Search")',
                        'button:has-text("Submit")',
                        'button.MuiButton-containedSuccess',
                        'button.MuiButton-contained',
                        'button[type="submit"]',
                        '.MuiButton-root.MuiButton-contained'
                    ]
                    
                    button_found = False
                    for selector in button_selectors:
                        try:
                            if page.locator(selector).count() > 0:
                                page.locator(selector).first.click()
                                button_found = True
                                log(f"Search button clicked with selector: {selector}")
                                break
                        except:
                            continue
                    
                    if not button_found:
                        log(f"✗ {ca}: Could not find search button")
                        raise Exception("Could not find search button")
                    
                    # Wait for search results
                    page.wait_for_timeout(3000)
                    
                except Exception as e:
                    log(f"✗ {ca}: Failed to click search button - {str(e)[:100]}")
                    browser.close()
                    continue

                # Click the download button and capture PDF
                try:
                    log(f"Clicking download button for CA: {ca}")
                    
                    # Wait for the download button to be available
                    page.wait_for_selector('button[aria-label="Download In English"]', timeout=15000)
                    
                    # Click the download button and capture the PDF
                    with page.expect_download(timeout=30000) as download_info:
                        page.click('button[aria-label="Download In English"]')
                    
                    download = download_info.value
                    
                    # Save to temp file and read
                    import tempfile
                    import os
                    with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as tmp:
                        tmp_path = tmp.name
                    
                    download.save_as(tmp_path)
                    
                    with open(tmp_path, 'rb') as f:
                        pdf_data = f.read()
                    
                    # Clean up temp file
                    try:
                        os.unlink(tmp_path)
                    except:
                        pass
                    
                    log(f"✓ {ca}: PDF downloaded successfully")
                    
                except PWTimeout:
                    log(f"✗ {ca}: Download button timeout or bill not found")
                except Exception as e:
                    log(f"✗ {ca}: Download failed - {str(e)[:160]}")

                browser.close()

        except Exception as e:
            log(f"✗ {ca}: Error - {str(e)[:160]}")

        if pdf_data and len(pdf_data) > 500:
            filename = f"MP_Madhya_Kshetra_{ca}.pdf"
            # Rename with extracted date
            filename = rename_pdf_with_date(filename, pdf_data, "MP_Madhya_Kshetra")
            downloads[session_id]["files"][filename] = pdf_data
            log(f"✓ {ca}: Downloaded ({len(pdf_data)} bytes) - {filename}")
        else:
            log(f"✗ {ca}: Could not capture PDF")

        downloads[session_id]["completed"] += 1
        downloads[session_id]["progress"] = int(downloads[session_id]["completed"] * 100 / downloads[session_id]["total"])

    downloads[session_id]["status"] = "completed"


# -------------------- Madhya Pradesh Paschim Kshetra DISCOM --------------------
def download_mp_paschim_kshetra(ca_numbers, session_id):
    """
    Download bills from MP Paschim Kshetra DISCOM
    URL: https://mpwzservices.mpwin.co.in/westdiscom/home
    """
    try:
        from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
    except Exception:
        downloads[session_id] = {
            "status": "error",
            "logs": ["Playwright not installed. Run: pip install playwright && playwright install chromium"]
        }
        return

    downloads[session_id] = {
        "status": "downloading",
        "progress": 0,
        "completed": 0,
        "total": len(ca_numbers),
        "logs": [],
        "files": {}
    }

    def log(m): _log(session_id, m)

    for ca in ca_numbers:
        ca = str(ca).strip()
        pdf_data = None
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(
                    headless=True,
                    args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-blink-features=AutomationControlled"]
                )
                context = browser.new_context(
                    accept_downloads=True,
                    ignore_https_errors=True,
                    user_agent=("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                                "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"),
                    viewport={"width": 1366, "height": 900}
                )
                context.add_init_script("Object.defineProperty(navigator,'webdriver',{get:()=>undefined})")

                page = context.new_page()
                url = "https://mpwzservices.mpwin.co.in/westdiscom/home"
                
                log(f"Loading bill page for CA: {ca}")
                page.goto(url, wait_until="domcontentloaded", timeout=60000)

                # Wait for page to load
                try:
                    page.wait_for_load_state("networkidle", timeout=10000)
                except:
                    pass

                # Enter CA number in the input field inside div[id='home']
                try:
                    log(f"Entering CA number: {ca}")
                    page.wait_for_timeout(2000)
                    
                    # Target the input field inside div[id='home']
                    input_selector = 'div[id="home"] input[type="text"]'
                    
                    # Wait for the input field to be available
                    page.wait_for_selector(input_selector, timeout=10000)
                    
                    # Fill the CA number
                    page.fill(input_selector, ca)
                    log(f"CA number entered successfully")
                    
                    # Wait for input to register
                    page.wait_for_timeout(1000)
                    
                except Exception as e:
                    log(f"✗ {ca}: Failed to enter CA number - {str(e)[:100]}")
                    browser.close()
                    continue

                # Click the "View & Pay Energy Bill" button
                try:
                    log(f"Clicking 'View & Pay Energy Bill' button for CA: {ca}")
                    
                    # Multiple selectors for the button
                    view_pay_selectors = [
                        'input[value="View & Pay Energy Bill"]',
                        'input[type="submit"]',
                        '//input[@value="View & Pay Energy Bill"]',
                    ]
                    
                    clicked = False
                    for selector in view_pay_selectors:
                        try:
                            page.wait_for_selector(selector, timeout=5000, state="visible")
                            
                            # Click and wait for navigation
                            log(f"Clicking with selector: {selector}")
                            
                            # Use Promise.all to wait for navigation
                            try:
                                page.click(selector)
                                log(f"Button clicked, waiting for navigation...")
                                
                                # Wait for navigation or network idle
                                try:
                                    page.wait_for_load_state("networkidle", timeout=15000)
                                except:
                                    page.wait_for_timeout(5000)
                                
                                # Check if we navigated to a new page
                                current_url = page.url
                                log(f"Current URL after click: {current_url}")
                                
                                clicked = True
                                break
                                
                            except Exception as e:
                                log(f"Navigation error: {str(e)[:100]}")
                                
                        except Exception as e:
                            log(f"Selector {selector} failed: {str(e)[:80]}")
                            continue
                    
                    if not clicked:
                        log(f"✗ {ca}: Could not click 'View & Pay Energy Bill' button")
                        browser.close()
                        continue
                    
                    log(f"✓ 'View & Pay Energy Bill' button clicked successfully")
                    
                except Exception as e:
                    log(f"✗ {ca}: Failed to click 'View & Pay Energy Bill' button - {str(e)[:100]}")
                    browser.close()
                    continue

                # Click the "View Latest Month Bill" button and capture PDF
                try:
                    log(f"Clicking 'View Latest Month Bill' button for CA: {ca}")
                    
                    # Wait longer for the page to fully load after previous click
                    log(f"Waiting for page to load completely...")
                    page.wait_for_timeout(5000)
                    
                    # Wait for network to be idle
                    try:
                        page.wait_for_load_state("networkidle", timeout=10000)
                    except:
                        pass
                                 

       
                    # Log page content to see what's available
                    try:
                        all_buttons = page.locator('button').all()
                        log(f"Total buttons on page: {len(all_buttons)}")
                        for i, btn in enumerate(all_buttons[:15]):  # Log first 15 buttons
                            try:
                                text = btn.inner_text().strip()
                                classes = btn.get_attribute('class')
                                visible = btn.is_visible()
                                log(f"Button {i+1}: text='{text}', class='{classes}', visible={visible}")
                            except Exception as e:
                                log(f"Button {i+1}: Error - {str(e)[:50]}")
                    except Exception as e:
                        log(f"Error listing buttons: {str(e)[:80]}")
                    
                    # Check if we need to scroll
                    try:
                        page.evaluate("window.scrollTo(0, document.body.scrollHeight / 2)")
                        log(f"Scrolled page to middle")
                        page.wait_for_timeout(1000)
                    except:
                        pass
                    
                    # Find and click the button using multiple locator strategies
                    view_bill_selectors = [
                        'body > app-root:nth-child(1) > app-viewbill:nth-child(2) > div:nth-child(2) > div:nth-child(1) > div:nth-child(1) > section:nth-child(1) > div:nth-child(1) > div:nth-child(1) > div:nth-child(1) > div:nth-child(2) > div:nth-child(2) > form:nth-child(3) > div:nth-child(2) > div:nth-child(2) > div:nth-child(1) > button:nth-child(1)',
                        '//button[normalize-space()="View Latest Month Bill"]',
                        'button.btn.btn-warning.btn-sm',
                        'button:has-text("View Latest Month Bill")',
                        'form button.btn-warning',
                        'div.col-md-12 button',
                    ]
                    
                    button_found = False
                    for selector in view_bill_selectors:
                        try:
                            # Wait for selector to be available
                            try:
                                page.wait_for_selector(selector, timeout=5000, state="visible")
                            except:
                                continue
                            
                            count = page.locator(selector).count()
                            if count > 0:
                                log(f"✓ Found {count} button(s) with selector: {selector}")
                                button_found = True
                                
                                # Click the button and wait for download
                                log(f"Clicking button and waiting for download...")
                                
                                try:
                                    # Try to catch download
                                    with page.expect_download(timeout=20000) as download_info:
                                        page.locator(selector).first.click()
                                        log(f"Button clicked, waiting for download...")
                                    
                                    download = download_info.value
                                    log(f"✓ Download triggered: {download.suggested_filename}")
                                    
                                    # Save to temp file and read
                                    import tempfile
                                    import os
                                    
                                    with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as tmp:
                                        tmp_path = tmp.name
                                    
                                    download.save_as(tmp_path)
                                    log(f"Download saved to temp file: {tmp_path}")
                                    
                                    with open(tmp_path, 'rb') as f:
                                        pdf_data = f.read()
                                    
                                    # Clean up temp file
                                    try:
                                        os.unlink(tmp_path)
                                    except:
                                        pass
                                    
                                    if pdf_data and len(pdf_data) > 1000:
                                        log(f"✓ {ca}: PDF downloaded successfully ({len(pdf_data)} bytes)")
                                        break
                                    else:
                                        log(f"⚠ Downloaded file too small: {len(pdf_data)} bytes")
                                    
                                except PWTimeout:
                                    log(f"⚠ Download timeout - trying alternative methods...")
                                    
                                    # Wait for any response
                                    page.wait_for_timeout(5000)
                                    
                                    # Check if new window/tab opened
                                    all_pages = context.pages
                                    log(f"Total pages/windows: {len(all_pages)}")
                                    
                                    if len(all_pages) > 1:
                                        log(f"New window detected!")
                                        new_page = all_pages[-1]
                                        
                                        try:
                                            new_page.wait_for_load_state("load", timeout=10000)
                                            new_url = new_page.url
                                            log(f"New window URL: {new_url}")
                                            
                                            # If it's a PDF URL, fetch it
                                            if '.pdf' in new_url.lower():
                                                resp = context.request.get(new_url, timeout=30000)
                                                if resp.ok:
                                                    pdf_data = resp.body()
                                                    log(f"✓ {ca}: PDF fetched from new window ({len(pdf_data)} bytes)")
                                            else:
                                                # Print the new window as PDF
                                                new_page.wait_for_timeout(2000)
                                                pdf_data = new_page.pdf(format="A4", print_background=True)
                                                log(f"✓ {ca}: PDF generated from new window ({len(pdf_data)} bytes)")
                                            
                                            new_page.close()
                                        except Exception as e:
                                            log(f"Error with new window: {str(e)[:100]}")
                                            try:
                                                new_page.close()
                                            except:
                                                pass
                                    
                                    # If still no PDF, check current page
                                    if not pdf_data:
                                        log(f"Checking current page...")
                                        page.wait_for_timeout(2000)
                                        
                                        # Check for iframe with PDF
                                        iframes = page.query_selector_all('iframe')
                                        if iframes:
                                            log(f"Found {len(iframes)} iframe(s)")
                                            for iframe in iframes:
                                                try:
                                                    src = iframe.get_attribute('src')
                                                    if src and 'pdf' in src.lower():
                                                        from urllib.parse import urljoin
                                                        full_url = urljoin(page.url, src)
                                                        log(f"Fetching PDF from iframe: {full_url}")
                                                        resp = context.request.get(full_url, timeout=30000)
                                                        if resp.ok:
                                                            pdf_data = resp.body()
                                                            log(f"✓ {ca}: PDF from iframe ({len(pdf_data)} bytes)")
                                                            break
                                                except Exception as e:
                                                    log(f"Error with iframe: {str(e)[:80]}")
                                        
                                        # Last resort: print page if it has bill content
                                        if not pdf_data:
                                            content = page.content().lower()
                                            if 'ivrs no' in content and 'bill amount' in content:
                                                log(f"Bill content found, generating PDF...")
                                                pdf_data = page.pdf(format="A4", print_background=True)
                                                log(f"✓ {ca}: PDF from page ({len(pdf_data)} bytes)")
                                    
                                    break
                                    
                        except Exception as e:
                            log(f"Error with selector '{selector}': {str(e)[:100]}")
                            continue
                    
                    if not button_found:
                        log(f"⚠ Button not found")
                        raise Exception("Could not find 'View Latest Month Bill' button")
                    
                    if not pdf_data or len(pdf_data) < 500:
                        raise Exception(f"No valid PDF captured (size: {len(pdf_data) if pdf_data else 0} bytes)")
                    
                except Exception as e:
                    log(f"✗ {ca}: Download failed - {str(e)[:160]}")

                browser.close()

        except Exception as e:
            log(f"✗ {ca}: Error - {str(e)[:160]}")

        if pdf_data and len(pdf_data) > 500:
            filename = f"MP_Paschim_Kshetra_{ca}.pdf"
            # Rename with extracted date
            filename = rename_pdf_with_date(filename, pdf_data, "MP_Paschim_Kshetra")
            downloads[session_id]["files"][filename] = pdf_data
            log(f"✓ {ca}: Downloaded ({len(pdf_data)} bytes) - {filename}")
        else:
            log(f"✗ {ca}: Could not capture PDF")

        downloads[session_id]["completed"] += 1
        downloads[session_id]["progress"] = int(downloads[session_id]["completed"] * 100 / downloads[session_id]["total"])

    downloads[session_id]["status"] = "completed"


# -------------------- Kerala State Electricity Board (KSEB) --------------------
# TEMPORARILY DISABLED DUE TO FILE CORRUPTION - NEEDS MANUAL FIX
def download_kerala_kseb_disabled(ca_mobile_pairs, session_id):
    """
    Download bills from Kerala State Electricity Board (KSEB)
    URL: https://old.kseb.in/billview/
    Requires CA number and mobile number for each bill
    """
    try:
        from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
    except Exception:
        downloads[session_id] = {
            "status": "error",
            "logs": ["Playwright not installed. Run: pip install playwright && playwright install chromium"]
        }
        return

    downloads[session_id] = {
        "status": "downloading",
        "progress": 0,
        "completed": 0,
        "total": len(ca_mobile_pairs),
        "logs": [],
        "files": {}
    }

    def log(m): _log(session_id, m)

    for pair in ca_mobile_pairs:
        ca_number = str(pair.get('ca_number', '')).strip()
        mobile_number = str(pair.get('mobile_number', '')).strip()
        
        if not ca_number or not mobile_number:
            log(f"✗ Skipping invalid entry: CA={ca_number}, Mobile={mobile_number}")
            downloads[session_id]["completed"] += 1
            downloads[session_id]["progress"] = int(downloads[session_id]["completed"] * 100 / downloads[session_id]["total"])
            continue
        
        pdf_data = None
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(
                    headless=False,  # Run in visible mode to avoid detection
                    args=[
                        "--no-sandbox",
                        "--disable-dev-shm-usage",
                        "--disable-blink-features=AutomationControlled",
                        "--disable-features=IsolateOrigins,site-per-process"
                    ]
                )
                context = browser.new_context(
                    accept_downloads=True,
                    ignore_https_errors=True,
                    user_agent=("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                                "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"),
                    viewport={"width": 1366, "height": 900},
                    locale="en-US"
                )
                # Enhanced anti-detection
                context.add_init_script("""
                    Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
                    Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]});
                    Object.defineProperty(navigator, 'languages', {get: () => ['en-US', 'en']});
                    window.chrome = {runtime: {}};
                """)

                page = context.new_page()
                
                # Set up request/response interception to capture PDF
                pdf_response = {'data': None}
                
                def handle_response(response):
                    try:
                        content_type = response.headers.get('content-type', '').lower()
                        if 'pdf' in content_type or response.url.endswith('.pdf'):
                            log(f"PDF response intercepted: {response.url}")
                            try:
                                body = response.body()
                                if body and len(body) > 1000 and body[:4] == b'%PDF':
                                    pdf_response['data'] = body
                                    log(f"✓ PDF captured from network ({len(body)} bytes)")
                            except:
                                pass
                    except:
                        pass
                
                page.on('response', handle_response)
                
                url = "https://old.kseb.in/billview/"
                
                log(f"Loading KSEB bill page for CA: {ca_number}")
                page.goto(url, wait_until="domcontentloaded", timeout=60000)

                try:
                    page.wait_for_load_state("networkidle", timeout=10000)
                except:
                    pass

                try:
                    log(f"Entering CA number: {ca_number}")
                    page.wait_for_selector('#consumerno_id', timeout=10000)
                    page.fill('#consumerno_id', ca_number)
                    log(f"CA number entered successfully")
                    page.wait_for_timeout(500)
                except Exception as e:
                    log(f"✗ {ca_number}: Failed to enter CA number - {str(e)[:100]}")
                    browser.close()
                    continue

                try:
                    log(f"Entering mobile number: {mobile_number}")
                    page.wait_for_selector('#regmobno_id', timeout=10000)
                    page.fill('#regmobno_id', mobile_number)
                    log(f"Mobile number entered successfully")
                    page.wait_for_timeout(500)
                except Exception as e:
                    log(f"✗ {ca_number}: Failed to enter mobile number - {str(e)[:100]}")
                    browser.close()
                    continue

                # Click View Bill button - handle both popup and same-page scenarios
                bill_page = None
                try:
                    log(f"Clicking 'View Bill' button for CA: {ca_number}")
                    page.wait_for_selector('#b_submit_0', timeout=10000)
                    
                    # Click the button once and handle response
                    page.click('#b_submit_0')
                    log(f"'View Bill' button clicked, waiting for response...")
                    
                    # Wait a moment for response
                    page.wait_for_timeout(3000)
                    
                    # Check if new page opened
                    all_pages = context.pages
                    if len(all_pages) > 1:
                        bill_page = all_pages[-1]
                        log(f"✓ New page detected! URL: {bill_page.url}")
                        bill_page.wait_for_load_state("domcontentloaded", timeout=30000)
                        bill_page.wait_for_timeout(3000)
                    else:
                        log(f"Bill loading on same page...")
                        # Bill loads on same page
                        bill_page = page
                        
                        # Wait for navigation or content change
                        log(f"Waiting for bill to load...")
                        page.wait_for_timeout(5000)
                        
                        # Check if URL changed or page navigated
                        current_url = page.url
                        log(f"Current URL: {current_url}")
                        
                        # Wait for page to stabilize
                        try:
                            page.wait_for_load_state("networkidle", timeout=10000)
                            log(f"✓ Page loaded")
                        except:
                            log(f"Continuing after timeout...")
                            page.wait_for_timeout(3000)
                        

                    
                    if not bill_page:
                        log(f"✗ {ca_number}: Could not determine bill page")
                        browser.close()
                        continue
                    
                except Exception as e:
                    log(f"✗ {ca_number}: Error clicking View Bill - {str(e)[:150]}")
                    browser.close()
                    continue

                try:
                    log(f"Extracting PDF from bill page...")
                    
                    page_title = bill_page.title()
                    page_url = bill_page.url
                    log(f"Bill page title: {page_title}")
                    log(f"Bill page URL: {page_url}")
                    
                    # Method 0: Check if we captured PDF from network interception
                    if pdf_response['data']:
                        pdf_data = pdf_response['data']
                        log(f"✓ {ca_number}: Using PDF from network interception ({len(pdf_data)} bytes)")
                    else:
                        log(f"No PDF captured from network interception")
                    
                    # Method 0.5: Look for form that generates PDF
                    if not pdf_data:
                        log(f"Checking page HTML for PDF generation forms...")
                        page_html = bill_page.content()
                        
                        # Look for forms that might generate PDF
                        import re
                        form_actions = re.findall(r'<form[^>]*action=["\']([^"\']*pdf[^"\']*)["\']', page_html, re.IGNORECASE)
                        if form_actions:
                            log(f"Found {len(form_actions)} PDF form(s): {form_actions}")
                            for action in form_actions:
                                try:
                                    from urllib.parse import urljoin
                                    full_url = urljoin(bill_page.url, action)
                                    log(f"Trying PDF form action: {full_url}")
                                    
                                    # Try to submit the form or get the PDF
                                    resp = context.request.post(full_url, data={'ca_number': ca_number}, timeout=30000)
                                    if resp.ok:
                                        body = resp.body()
                                        if body and body[:4] == b'%PDF':
                                            pdf_data = body
                                            log(f"✓ {ca_number}: PDF from form action ({len(pdf_data)} bytes)")
                                            break
                                except Exception as e:
                                    log(f"Form action error: {str(e)[:100]}")
                        
                        # Look for direct PDF links in the page
                        pdf_links = re.findall(r'href=["\']([^"\']*\.pdf[^"\']*)["\']', page_html, re.IGNORECASE)
                        if pdf_links:
                            log(f"Found {len(pdf_links)} PDF link(s): {pdf_links}")
                            for link in pdf_links:
                                try:
                                    from urllib.parse import urljoin
                                    full_url = urljoin(bill_page.url, link)
                                    log(f"Trying PDF link: {full_url}")
                                    
                                    resp = context.request.get(full_url, timeout=30000)
                                    if resp.ok:
                                        body = resp.body()
                                        if body and body[:4] == b'%PDF':
                                            pdf_data = body
                                            log(f"✓ {ca_number}: PDF from link ({len(pdf_data)} bytes)")
                                            break
                                except Exception as e:
                                    log(f"PDF link error: {str(e)[:100]}")
                    
                    # Method 1: Check if the page URL is a direct PDF
                    if page_url.endswith('.pdf'):
                        log(f"✓ Direct PDF URL detected!")
                        try:
                            resp = context.request.get(page_url, timeout=30000)
                            if resp.ok:
                                pdf_data = resp.body()
                                if pdf_data and len(pdf_data) > 1000 and pdf_data[:4] == b'%PDF':
                                    log(f"✓ {ca_number}: PDF downloaded from URL ({len(pdf_data)} bytes)")
                        except Exception as e:
                            log(f"Error downloading PDF URL: {str(e)[:100]}")
                    
                    # Method 2: Check page content-type
                    if not pdf_data:
                        try:
                            log(f"Checking page content-type...")
                            response = context.request.get(page_url, timeout=30000)
                            content_type = response.headers.get('content-type', '').lower()
                            log(f"Content-Type: {content_type}")
                            
                            if 'pdf' in content_type or 'application/pdf' in content_type:
                                body = response.body()
                                if body and len(body) > 1000 and body[:4] == b'%PDF':
                                    pdf_data = body
                                    log(f"✓ {ca_number}: PDF from content-type ({len(pdf_data)} bytes)")
                        except Exception as e:
                            log(f"Content-type check error: {str(e)[:100]}")
                    
                    # Method 2: Look for ALL embedded elements (embed, object, iframe)
                    if not pdf_data:
                        log(f"Checking for embedded PDF elements...")
                        
                        # Check ALL embed tags (not just with type attribute)
                        all_embeds = bill_page.query_selector_all('embed')
                        log(f"Found {len(all_embeds)} embed element(s)")
                        
                        for embed in all_embeds:
                            try:
                                src = embed.get_attribute('src')
                                embed_type = embed.get_attribute('type') or ''
                                log(f"Embed - type: {embed_type}, src: {src[:100] if src else 'none'}")
                                
                                # If src is about:blank, the PDF is loaded dynamically
                                if src and src != 'about:blank':
                                    from urllib.parse import urljoin
                                    full_url = urljoin(bill_page.url, src)
                                    log(f"Fetching from embed: {full_url}")
                                    
                                    resp = context.request.get(full_url, timeout=30000)
                                    if resp.ok:
                                        body = resp.body()
                                        if body and len(body) > 1000:
                                            # Check if it's a PDF
                                            if body[:4] == b'%PDF':
                                                pdf_data = body
                                                log(f"✓ {ca_number}: PDF fetched from embed ({len(pdf_data)} bytes)")
                                                break
                                            else:
                                                log(f"Embed content is not PDF (first 4 bytes: {body[:4]})")
                                elif src == 'about:blank' and embed_type == 'application/pdf':
                                    # PDF is loaded dynamically - try to extract from page scripts or data
                                    log(f"PDF embed with about:blank detected - checking for inline PDF data...")
                                    
                                    # Try to find PDF data in page scripts or as base64
                                    page_html = bill_page.content()
                                    
                                    # Look for base64 PDF data
                                    import re
                                    base64_pattern = r'data:application/pdf;base64,([A-Za-z0-9+/=]+)'
                                    matches = re.findall(base64_pattern, page_html)
                                    
                                    if matches:
                                        log(f"Found {len(matches)} base64 PDF data")
                                        import base64
                                        for b64_data in matches:
                                            try:
                                                decoded = base64.b64decode(b64_data)
                                                if decoded[:4] == b'%PDF':
                                                    pdf_data = decoded
                                                    log(f"✓ {ca_number}: PDF extracted from base64 ({len(pdf_data)} bytes)")
                                                    break
                                            except:
                                                pass
                                    
                                    # If still no PDF, try to get it via JavaScript
                                    if not pdf_data:
                                        log(f"Attempting to extract PDF via JavaScript...")
                                        try:
                                            # Try to get the PDF blob URL or data
                                            pdf_url = bill_page.evaluate("""
                                                () => {
                                                    const embed = document.querySelector('embed[type="application/pdf"]');
                                                    if (embed && embed.src && embed.src !== 'about:blank') {
                                                        return embed.src;
                                                    }
                                                    return null;
                                                }
                                            """)
                                            
                                            if pdf_url and pdf_url.startswith('blob:'):
                                                log(f"Found blob URL: {pdf_url}")
                                                # Blob URLs can't be fetched directly, need different approach
                                            elif pdf_url:
                                                log(f"Found PDF URL via JS: {pdf_url}")
                                                resp = context.request.get(pdf_url, timeout=30000)
                                                if resp.ok:
                                                    body = resp.body()
                                                    if body and body[:4] == b'%PDF':
                                                        pdf_data = body
                                                        log(f"✓ {ca_number}: PDF from JS URL ({len(pdf_data)} bytes)")
                                        except Exception as js_err:
                                            log(f"JavaScript extraction failed: {str(js_err)[:100]}")
                                    
                            except Exception as e:
                                log(f"Error with embed: {str(e)[:100]}")
                        
                        # Also check object tags
                        if not pdf_data:
                            objects = bill_page.query_selector_all('object')
                            log(f"Found {len(objects)} object element(s)")
                            
                            for obj in objects:
                                try:
                                    data_attr = obj.get_attribute('data')
                                    obj_type = obj.get_attribute('type') or ''
                                    log(f"Object - type: {obj_type}, data: {data_attr[:100] if data_attr else 'none'}")
                                    
                                    if data_attr:
                                        from urllib.parse import urljoin
                                        full_url = urljoin(bill_page.url, data_attr)
                                        log(f"Fetching from object: {full_url}")
                                        
                                        resp = context.request.get(full_url, timeout=30000)
                                        if resp.ok:
                                            body = resp.body()
                                            if body and len(body) > 1000 and body[:4] == b'%PDF':
                                                pdf_data = body
                                                log(f"✓ {ca_number}: PDF fetched from object ({len(pdf_data)} bytes)")
                                                break
                                except Exception as e:
                                    log(f"Error with object: {str(e)[:100]}")
                    
                    # Method 3: Check iframes
                    if not pdf_data:
                        iframes = bill_page.query_selector_all('iframe')
                        log(f"Found {len(iframes)} iframe(s)")
                        
                        for iframe in iframes:
                            try:
                                src = iframe.get_attribute('src')
                                if src:
                                    log(f"Checking iframe: {src[:100]}")
                                    from urllib.parse import urljoin
                                    full_url = urljoin(bill_page.url, src)
                                    
                                    resp = context.request.get(full_url, timeout=30000)
                                    if resp.ok:
                                        body = resp.body()
                                        if body and len(body) > 1000 and body[:4] == b'%PDF':
                                            pdf_data = body
                                            log(f"✓ {ca_number}: PDF fetched from iframe ({len(pdf_data)} bytes)")
                                            break
                            except Exception as e:
                                log(f"Error with iframe: {str(e)[:80]}")
                    
                    # Method 4: Generate PDF from the rendered page
                    if not pdf_data:
                        log(f"No embedded PDF found, analyzing page content...")
                        page_content = bill_page.content()
                        page_content_lower = page_content.lower()
                        
                        # Check for bill indicators
                        has_kseb = 'kerala state electricity board' in page_content_lower
                        has_demand = 'demand cum disconnection' in page_content_lower
                        has_bill_date = 'bill date' in page_content_lower
                        has_consumer = 'consumer' in page_content_lower and ca_number in page_content
                        has_bill_area = 'bill area' in page_content_lower
                        has_tariff = 'tariff' in page_content_lower
                        
                        log(f"Content check - KSEB: {has_kseb}, Demand: {has_demand}, Bill Date: {has_bill_date}, Consumer: {has_consumer}")
                        
                        # Check if we're still on the form page
                        is_form_page = 'view bill' in page_content_lower and 'b_submit_0' in page_content
                        
                        # If bill content is present, generate PDF
                        if (has_kseb or has_demand or has_bill_date or has_bill_area or has_tariff) and not is_form_page:
                            log(f"✓ Bill content detected! Generating PDF from rendered page...")
                            
                            # Wait a bit more to ensure everything is rendered
                            bill_page.wait_for_timeout(2000)
                            
                            pdf_data = bill_page.pdf(
                                format="A4",
                                print_background=True,
                                prefer_css_page_size=False,
                                margin={"top": "0.4cm", "right": "0.4cm", "bottom": "0.4cm", "left": "0.4cm"}
                            )
                            log(f"✓ {ca_number}: PDF generated from bill page ({len(pdf_data)} bytes)")
                        elif is_form_page:
                            log(f"✗ {ca_number}: Still on form page, bill did not load")
                        else:
                            log(f"⚠ {ca_number}: Uncertain content, attempting PDF generation anyway...")
                            try:
                                pdf_data = bill_page.pdf(format="A4", print_background=True)
                                log(f"✓ {ca_number}: PDF generated ({len(pdf_data)} bytes)")
                            except Exception as pdf_err:
                                log(f"✗ PDF generation failed: {str(pdf_err)[:100]}")
                                # Log page text for debugging
                                try:
                                    text_content = bill_page.evaluate("() => document.body.innerText")
                                    log(f"Page text preview: {text_content[:300]}")
                                except:
                                    pass
                    
                    # Close the bill page
                    try:
                        bill_page.close()
                    except:
                        pass
                    
                except Exception as e:
                    log(f"✗ {ca_number}: Error extracting PDF - {str(e)[:160]}")

                browser.close()

        except Exception as e:
            log(f"✗ {ca_number}: Error - {str(e)[:160]}")

        if pdf_data and len(pdf_data) > 500:
            filename = f"KSEB_{ca_number}.pdf"
            # Rename with extracted date
            filename = rename_pdf_with_date(filename, pdf_data, "KSEB")
            downloads[session_id]["files"][filename] = pdf_data
            log(f"✓ {ca_number}: Downloaded ({len(pdf_data)} bytes) - {filename}")
        else:
            log(f"✗ {ca_number}: Could not capture PDF")

        downloads[session_id]["completed"] += 1
        downloads[session_id]["progress"] = int(downloads[session_id]["completed"] * 100 / downloads[session_id]["total"])

    downloads[session_id]["status"] = "completed"


# Create an alias for the active function
download_kerala_kseb = download_kerala_kseb_disabled


# -------------------- Eastern Power Distribution Company of Andhra Pradesh Limited (APEPDCL) --------------------
def download_apepdcl(ca_numbers, session_id):
    """
    Download bills from Eastern Power Distribution Company of Andhra Pradesh Limited with captcha solving
    """
    try:
        from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
        import base64
    except Exception as e:
        downloads[session_id] = {
            "status": "error",
            "logs": [f"Missing dependencies: {str(e)}. Install: pip install playwright"]
        }
        return

    downloads[session_id] = {
        "status": "downloading",
        "progress": 0,
        "completed": 0,
        "total": len(ca_numbers),
        "logs": [],
        "files": {}
    }

    def log(m): _log(session_id, m)

    CAPSOLVER_API_KEY = "CAP-ADCA94D1B80ACF6A5A0E9E57B4E90158"
    BASE_URL = "https://www.apeasternpower.com/viewBillDetailsMain"

    def solve_captcha_with_capsolver(image_base64):
        """Solve captcha using CapSolver API"""
        try:
            log("🔍 Solving captcha with CapSolver...")
            
            # Remove data URL prefix if present
            if "," in image_base64 and image_base64.startswith("data:"):
                image_base64 = image_base64.split(",", 1)[1]
            
            # Validate base64 image
            if not image_base64 or len(image_base64) < 100:
                log(f"✗ Invalid captcha image (too short: {len(image_base64)} chars)")
                return None
            
            # Create task
            create_task_url = "https://api.capsolver.com/createTask"
            task_payload = {
                "clientKey": CAPSOLVER_API_KEY,
                "task": {
                    "type": "ImageToTextTask",
                    "body": image_base64,
                    "module": "common",
                    "score": 0.5,
                    "case": False
                }
            }
            
            log(f"📤 Sending captcha to CapSolver (image size: {len(image_base64)} chars)")
            response = requests.post(create_task_url, json=task_payload, timeout=30)
            
            # Check HTTP status
            if response.status_code != 200:
                log(f"✗ CapSolver HTTP error: {response.status_code}")
                log(f"Response: {response.text[:200]}")
                return None
            
            result = response.json()
            log(f"📥 CapSolver response: {result}")
            
            # Check for API errors
            error_id = result.get("errorId", -1)
            if error_id != 0:
                error_msg = result.get('errorDescription', 'Unknown error')
                error_code = result.get('errorCode', 'N/A')
                log(f"✗ CapSolver error (ID: {error_id}, Code: {error_code}): {error_msg}")
                
                # Provide helpful hints for common errors
                if "insufficient balance" in error_msg.lower() or "balance" in error_msg.lower():
                    log("💡 Hint: Check your CapSolver account balance at https://dashboard.capsolver.com/")
                elif "invalid" in error_msg.lower() and "key" in error_msg.lower():
                    log("💡 Hint: Verify your CapSolver API key is correct")
                
                return None
            
            # Check if solution is already in the response (fast solve)
            if result.get("status") == "ready":
                captcha_text = result.get("solution", {}).get("text", "")
                if captcha_text:
                    log(f"✓ Captcha solved immediately: '{captcha_text}'")
                    return captcha_text
                else:
                    log(f"✗ No text in immediate solution: {result}")
                    return None
            
            # Otherwise, get task ID and poll for result
            task_id = result.get("taskId")
            if not task_id:
                log("✗ No task ID received from CapSolver")
                return None
            
            log(f"⏳ Task ID: {task_id}, waiting for solution...")
            
            # Poll for result
            get_result_url = "https://api.capsolver.com/getTaskResult"
            for attempt in range(30):  # Try for up to 30 seconds
                time.sleep(1)
                result_payload = {
                    "clientKey": CAPSOLVER_API_KEY,
                    "taskId": task_id
                }
                
                response = requests.post(get_result_url, json=result_payload, timeout=30)
                
                if response.status_code != 200:
                    log(f"✗ CapSolver result HTTP error: {response.status_code}")
                    continue
                
                result = response.json()
                status = result.get("status", "")
                
                if status == "ready":
                    captcha_text = result.get("solution", {}).get("text", "")
                    if captcha_text:
                        log(f"✓ Captcha solved: '{captcha_text}'")
                        return captcha_text
                    else:
                        log(f"✗ No text in solution: {result}")
                        return None
                elif status == "processing":
                    if attempt % 5 == 0:
                        log(f"⏳ Still processing... (attempt {attempt}/30)")
                    continue
                elif status == "failed":
                    error_desc = result.get('errorDescription', 'Unknown')
                    log(f"✗ CapSolver task failed: {error_desc}")
                    return None
                else:
                    log(f"✗ Unknown CapSolver status: {status}, full response: {result}")
            
            log("✗ Captcha solving timeout after 30 seconds")
            return None
            
        except requests.exceptions.Timeout:
            log("✗ CapSolver API timeout - network issue or service is slow")
            return None
        except requests.exceptions.RequestException as e:
            log(f"✗ CapSolver network error: {str(e)[:200]}")
            return None
        except Exception as e:
            log(f"✗ Captcha solving error: {str(e)[:200]}")
            import traceback
            log(f"Traceback: {traceback.format_exc()[:300]}")
            return None

    for idx, ca_number in enumerate(ca_numbers):
        ca_number = str(ca_number).strip()
        pdf_data = None
        
        try:
            log(f"Processing CA: {ca_number} (APEPDCL)")
            
            with sync_playwright() as p:
                browser = p.chromium.launch(
                    headless=True,
                    args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-blink-features=AutomationControlled"]
                )
                context = browser.new_context(
                    accept_downloads=True,
                    ignore_https_errors=True,
                    user_agent=("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                                "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"),
                    viewport={"width": 1366, "height": 900}
                )
                context.add_init_script("Object.defineProperty(navigator,'webdriver',{get:()=>undefined})")
                
                page = context.new_page()
                
                # Navigate to the page
                log(f"Loading page for CA: {ca_number}")
                page.goto(BASE_URL, wait_until="domcontentloaded", timeout=60000)
                
                # Wait for page to load
                try:
                    page.wait_for_selector("#ltscno", timeout=10000)
                except:
                    log(f"✗ {ca_number}: Page load timeout")
                    browser.close()
                    continue
                
                # Enter CA number
                log(f"Entering CA number: {ca_number}")
                page.fill("#ltscno", ca_number)
                
                # Get captcha image from canvas
                try:
                    page.wait_for_selector("#captchaCanvas", timeout=5000)
                    
                    # Extract captcha image from canvas as base64
                    image_base64 = page.evaluate("""
                        () => {
                            const canvas = document.getElementById('captchaCanvas');
                            if (canvas) {
                                return canvas.toDataURL('image/png').split(',')[1];
                            }
                            return null;
                        }
                    """)
                    
                    if not image_base64:
                        log(f"✗ {ca_number}: Could not extract captcha from canvas")
                        browser.close()
                        continue
                    
                    log(f"Extracted captcha from canvas (base64 length: {len(image_base64)})")
                    
                    # Solve captcha
                    captcha_text = solve_captcha_with_capsolver(image_base64)
                    
                    if not captcha_text:
                        log(f"✗ {ca_number}: Failed to solve captcha")
                        browser.close()
                        continue
                    
                    # Enter captcha
                    log(f"Entering captcha: {captcha_text}")
                    page.fill("#Billans", captcha_text)
                    
                    # Click Find My Bill button - try multiple selectors
                    log(f"Clicking Find My Bill button")
                    find_bill_selectors = [
                        'button:has-text("Find My Bill")',
                        'button:has-text("find my bill")',
                        'button[onclick*="bill"]',
                        'input[type="submit"]',
                        'input[type="button"][value*="Find"]',
                        'button.btn-primary',
                        'button.submit'
                    ]
                    
                    clicked = False
                    for selector in find_bill_selectors:
                        try:
                            if page.query_selector(selector):
                                page.click(selector, timeout=5000)
                                log(f"✓ Clicked button with selector: {selector}")
                                clicked = True
                                break
                        except:
                            continue
                    
                    if not clicked:
                        log(f"⚠ Could not find Find My Bill button, trying JavaScript click...")
                        try:
                            page.evaluate("""
                                () => {
                                    const buttons = document.querySelectorAll('button, input[type="submit"], input[type="button"]');
                                    for (const btn of buttons) {
                                        const text = (btn.innerText || btn.value || '').toLowerCase();
                                        if (text.includes('find') || text.includes('bill') || text.includes('submit')) {
                                            btn.click();
                                            return true;
                                        }
                                    }
                                    return false;
                                }
                            """)
                            log(f"✓ Clicked button via JavaScript")
                        except Exception as e:
                            log(f"✗ JavaScript click failed: {str(e)[:100]}")
                    
                    # Wait for navigation or response
                    try:
                        page.wait_for_load_state("networkidle", timeout=15000)
                    except:
                        pass
                    
                    # Check if we reached the bill page
                    time.sleep(2)
                    
                    # Check for error messages
                    error_selectors = [
                        'div.error', 'span.error', 'p.error',
                        'div[class*="error"]', 'span[class*="error"]',
                        'div.alert-danger', 'div.alert'
                    ]
                    
                    for selector in error_selectors:
                        error_element = page.query_selector(selector)
                        if error_element:
                            error_text = error_element.inner_text().strip()
                            if error_text:
                                log(f"⚠ Error message on page: {error_text[:200]}")
                                if "captcha" in error_text.lower():
                                    log(f"✗ {ca_number}: Captcha was incorrect")
                                    browser.close()
                                    continue
                                break
                    
                    # New flow: Click history button, find month, download bill
                    try:
                        # Wait for page to update after form submission
                        time.sleep(3)
                        
                        log(f"Looking for history button...")
                        
                        # Set up download listener before any clicks
                        download_info = {"download": None}
                        
                        def handle_download(download):
                            download_info["download"] = download
                            log(f"Download started: {download.suggested_filename}")
                        
                        page.on("download", handle_download)
                        
                        # Step 1: Click the "Consumption and Payment History" button
                        history_button_selectors = [
                            'body > div:nth-child(28) > div:nth-child(1) > div:nth-child(1) > div:nth-child(3) > div:nth-child(10) > div:nth-child(1) > div:nth-child(1) > div:nth-child(1) > div:nth-child(1) > div:nth-child(1) > div:nth-child(1) > div:nth-child(3) > h2:nth-child(2) > div:nth-child(1) > div:nth-child(1) > div:nth-child(1) > button:nth-child(1)',
                            'button:has-text("Consumption and Payment History")',
                            'xpath=//button[@id="historyDivbtn"]',
                            '#historyDivbtn',
                            'button#historyDivbtn',
                            'button:has-text("History")',
                            'button[id*="history"]'
                        ]
                        
                        history_button = None
                        for selector in history_button_selectors:
                            try:
                                history_button = page.query_selector(selector)
                                if history_button:
                                    log(f"✓ Found history button with selector: {selector}")
                                    break
                            except:
                                continue
                        
                        if not history_button:
                            log(f"✗ History button not found, trying JavaScript...")
                            try:
                                history_button_found = page.evaluate("""
                                    () => {
                                        const btn = document.getElementById('historyDivbtn');
                                        if (btn) {
                                            btn.click();
                                            return true;
                                        }
                                        return false;
                                    }
                                """)
                                if history_button_found:
                                    log(f"✓ Clicked history button via JavaScript")
                                else:
                                    log(f"✗ History button not found via JavaScript either")
                            except Exception as e:
                                log(f"✗ Error clicking history button: {str(e)[:100]}")
                        else:
                            # Click the history button
                            try:
                                history_button.click(timeout=5000)
                                log(f"✓ Clicked history button")
                            except:
                                log(f"⚠ Click timeout, trying JavaScript...")
                                page.evaluate("(el) => el.click()", history_button)
                                log(f"✓ Clicked history button via JavaScript")
                        
                        # Wait for history page to load
                        time.sleep(3)
                        
                        log(f"History page loaded, looking for latest bill...")
                        log(f"Current URL: {page.url}")
                        
                        # Step 2: Find and click the download button for the latest bill (first row)
                        # Using the exact selector from the screenshot
                        download_button_selectors = [
                            'tbody tr:nth-child(1) td:nth-child(6) span:nth-child(1) a:nth-child(1)',  # Exact selector from inspector
                            '//tbody/tr[1]/td[6]/span[1]/a[1]',  # XPath from inspector
                            '(//a[@class="btn btn-success"])[2]',  # Index XPath
                            'table tbody tr:first-child td:nth-child(6) a.btn-success',
                            'table tbody tr:first-child a.btn-success',
                            'table tbody tr:first-child a[href*="download"]',
                            'table tbody tr:first-child a[href*="bill"]',
                            'tbody tr:first-child td:nth-child(6) a',
                        ]
                        
                        download_button = None
                        used_selector = None
                        for selector in download_button_selectors:
                            try:
                                download_button = page.query_selector(selector)
                                if download_button:
                                    used_selector = selector
                                    log(f"✓ Found download button with selector: {selector}")
                                    break
                            except:
                                continue
                        
                        # If specific selectors don't work, try to find any download link in the first row
                        if not download_button:
                            log(f"Trying to find download button in first row via JavaScript...")
                            try:
                                download_button_found = page.evaluate("""
                                    () => {
                                        const firstRow = document.querySelector('table tbody tr:first-child');
                                        if (firstRow) {
                                            // Look for download icon or link
                                            const downloadLink = firstRow.querySelector('a[href*="download"], a[href*="bill"], a[href*="pdf"], button.btn-success, a.btn-success');
                                            if (downloadLink) {
                                                downloadLink.click();
                                                return true;
                                            }
                                            // Try to find by icon
                                            const icons = firstRow.querySelectorAll('a');
                                            for (const link of icons) {
                                                const icon = link.querySelector('i, span.glyphicon');
                                                if (icon && (icon.className.includes('download') || icon.className.includes('arrow-down'))) {
                                                    link.click();
                                                    return true;
                                                }
                                            }
                                        }
                                        return false;
                                    }
                                """)
                                if download_button_found:
                                    log(f"✓ Clicked download button via JavaScript")
                                else:
                                    log(f"✗ Download button not found in first row")
                            except Exception as e:
                                log(f"✗ Error finding download button: {str(e)[:100]}")
                        else:
                            # Click the download button
                            log(f"Clicking download button (selector: {used_selector})...")
                            try:
                                download_button.click(timeout=5000)
                                log(f"✓ Clicked download button")
                            except:
                                log(f"⚠ Click timeout, trying JavaScript...")
                                page.evaluate("(el) => el.click()", download_button)
                                log(f"✓ Clicked download button via JavaScript")
                        
                        # Wait for download to start
                        time.sleep(4)
                        
                        if download_info["download"]:
                            download = download_info["download"]
                            log(f"✓ Download captured: {download.suggested_filename}")
                            
                            # Save download to temp path and read
                            import tempfile
                            import os
                            with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
                                temp_path = tmp.name
                            
                            download.save_as(temp_path)
                            log(f"Download saved to: {temp_path}")
                            
                            # Read the PDF data
                            with open(temp_path, "rb") as f:
                                pdf_data = f.read()
                            
                            # Clean up temp file
                            try:
                                os.unlink(temp_path)
                            except:
                                pass
                            
                            log(f"✓ PDF downloaded successfully ({len(pdf_data)} bytes)")
                        else:
                            log(f"⚠ No download captured, trying to fetch PDF from link...")
                            # Try to get the href and fetch directly
                            if download_button:
                                try:
                                    href = download_button.get_attribute("href")
                                    if href:
                                        log(f"Download link href: {href}")
                                        from urllib.parse import urljoin
                                        full_url = urljoin(page.url, href)
                                        log(f"Fetching PDF from: {full_url}")
                                        response = context.request.get(full_url, timeout=30000)
                                        if response.ok:
                                            body = response.body()
                                            if body and len(body) > 500 and body[:4] == b'%PDF':
                                                pdf_data = body
                                                log(f"✓ PDF fetched from link ({len(pdf_data)} bytes)")
                                except Exception as e:
                                    log(f"⚠ Error fetching from link: {str(e)[:100]}")
                        
                        # Fallback: Try alternative methods if download didn't work
                        if not pdf_data:
                            log(f"Trying alternative methods to capture PDF...")
                            
                            # Check if there's an e-Bill element (old flow)
                            ebill_selectors = [
                                "div.col-md-9.col-xs-9.col-lg-9 p strong",
                                "strong:has-text('e-Bill')",
                                "a:has-text('e-Bill')",
                                "button:has-text('e-Bill')"
                            ]
                            
                            ebill_element = None
                            for selector in ebill_selectors:
                                try:
                                    ebill_element = page.query_selector(selector)
                                    if ebill_element:
                                        log(f"Found e-Bill element with selector: {selector}")
                                        break
                                except:
                                    continue
                            
                            if ebill_element:
                                log(f"Trying e-Bill element click...")
                                try:
                                    ebill_element.click(timeout=5000)
                                except:
                                    page.evaluate("(el) => el.click()", ebill_element)
                                
                                time.sleep(4)
                                
                                if download_info["download"]:
                                    download = download_info["download"]
                                    log(f"✓ Download captured from e-Bill: {download.suggested_filename}")
                                    
                                    import tempfile
                                    import os
                                    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
                                        temp_path = tmp.name
                                    
                                    download.save_as(temp_path)
                                    with open(temp_path, "rb") as f:
                                        pdf_data = f.read()
                                    
                                    try:
                                        os.unlink(temp_path)
                                    except:
                                        pass
                                    
                                    log(f"✓ PDF downloaded from e-Bill ({len(pdf_data)} bytes)")
                            
                            # Try to find View Bill link that opens in new window
                            if not pdf_data:
                                log(f"Trying to find View Bill link...")
                                
                                view_bill_selectors = [
                                    "span.ViewEbill a[target='_blank']",
                                    "a[target='_blank']:has-text('View')",
                                    "a[href*='viewEbill']",
                                    "a[href*='bill']",
                                    "a:has-text('View Bill')",
                                    "a:has-text('view bill')"
                                ]
                                
                                view_bill_link = None
                                for selector in view_bill_selectors:
                                    try:
                                        view_bill_link = page.query_selector(selector)
                                        if view_bill_link:
                                            log(f"Found View Bill link with selector: {selector}")
                                            break
                                    except:
                                        continue
                            
                            if not view_bill_link:
                                log(f"⚠ View Bill link not found, checking if bill is displayed on current page...")
                                # Check if bill details are on the current page
                                bill_content = page.query_selector('div[class*="bill"], table[class*="bill"], div[id*="bill"]')
                                if bill_content:
                                    log(f"Bill content found on current page, generating PDF...")
                                    try:
                                        pdf_data = page.pdf(
                                            format="A4",
                                            print_background=True,
                                            margin={"top": "0.5cm", "right": "0.5cm", "bottom": "0.5cm", "left": "0.5cm"}
                                        )
                                        log(f"✓ PDF generated from current page ({len(pdf_data)} bytes)")
                                    except Exception as e:
                                        log(f"✗ PDF generation failed: {str(e)[:100]}")
                            
                            if view_bill_link:
                                log(f"Found View Bill link")
                                
                                # Get the href before clicking
                                bill_url = view_bill_link.get_attribute("href")
                                log(f"View Bill URL: {bill_url}")
                                
                                # Try to capture PDF from new window
                                new_page = None
                                try:
                                    log(f"Clicking View Bill link and waiting for new page...")
                                    with context.expect_page(timeout=15000) as popup:
                                        view_bill_link.click()
                                    new_page = popup.value
                                    log(f"✓ New window opened successfully")
                                except PWTimeout:
                                    log(f"⚠ Timeout waiting for new page, clicking anyway...")
                                    try:
                                        view_bill_link.click()
                                    except:
                                        page.evaluate("(el) => el.click()", view_bill_link)
                                    time.sleep(4)
                                    # Check if any new pages were opened
                                    if len(context.pages) > 1:
                                        new_page = context.pages[-1]
                                        log(f"✓ Found new page in context")
                                except Exception as e:
                                    log(f"⚠ Error opening new page: {str(e)[:100]}")
                                    try:
                                        view_bill_link.click()
                                    except:
                                        page.evaluate("(el) => el.click()", view_bill_link)
                                    time.sleep(4)
                                    if len(context.pages) > 1:
                                        new_page = context.pages[-1]
                        
                                
                                # Determine target page
                                if new_page:
                                    target_page = new_page
                                    log(f"Using new window for PDF capture")
                                else:
                                    target_page = page
                                    log(f"Using current page for PDF capture")
                                
                                # Wait for page to load
                                try:
                                    log(f"Waiting for page to load...")
                                    target_page.wait_for_load_state("domcontentloaded", timeout=10000)
                                    time.sleep(2)
                                    target_page.wait_for_load_state("networkidle", timeout=10000)
                                except:
                                    log(f"⚠ Page load timeout, continuing anyway...")
                                    time.sleep(3)
                                
                                log(f"Target page URL: {target_page.url}")
                                log(f"Target page title: {target_page.title()}")
                                
                                # Method 1: Direct PDF URL fetch
                                if bill_url and ("pdf" in bill_url.lower() or "viewEbill" in bill_url):
                                    try:
                                        log(f"Trying to fetch PDF directly from bill URL...")
                                        from urllib.parse import urljoin
                                        full_url = urljoin(page.url, bill_url)
                                        log(f"Full bill URL: {full_url}")
                                        response = context.request.get(full_url, timeout=30000)
                                        if response.ok:
                                            body = response.body()
                                            if body and len(body) > 500 and body[:4] == b'%PDF':
                                                pdf_data = body
                                                log(f"✓ PDF fetched directly from bill URL ({len(pdf_data)} bytes)")
                                    except Exception as e:
                                        log(f"⚠ Error fetching from bill URL: {str(e)[:100]}")
                                
                                # Method 2: Check if target page URL is PDF
                                if not pdf_data and ("pdf" in target_page.url.lower() or target_page.url.endswith(".pdf")):
                                    try:
                                        log(f"Target page appears to be PDF, fetching...")
                                        response = context.request.get(target_page.url, timeout=30000)
                                        if response.ok:
                                            body = response.body()
                                            if body and len(body) > 500 and body[:4] == b'%PDF':
                                                pdf_data = body
                                                log(f"✓ PDF fetched from page URL ({len(pdf_data)} bytes)")
                                    except Exception as e:
                                        log(f"⚠ Error fetching PDF from page URL: {str(e)[:100]}")
                                
                                # Method 3: Look for PDF embed/iframe/object in the page
                                if not pdf_data:
                                    try:
                                        log(f"Looking for PDF elements in page...")
                                        time.sleep(2)  # Give time for PDF to load
                                        
                                        # Try multiple selectors
                                        selectors = [
                                            'embed[type="application/pdf"]',
                                            'object[type="application/pdf"]',
                                            'iframe[src*=".pdf"]',
                                            'embed[src*=".pdf"]',
                                            'object[data*=".pdf"]',
                                            'embed',
                                            'object',
                                            'iframe'
                                        ]
                                        
                                        for selector in selectors:
                                            pdf_element = target_page.query_selector(selector)
                                            if pdf_element:
                                                pdf_src = pdf_element.get_attribute("src") or pdf_element.get_attribute("data")
                                                if pdf_src:
                                                    log(f"Found element '{selector}' with src: {pdf_src[:100]}")
                                                    from urllib.parse import urljoin
                                                    pdf_url = urljoin(target_page.url, pdf_src)
                                                    log(f"Fetching PDF from: {pdf_url}")
                                                    response = context.request.get(pdf_url, timeout=30000)
                                                    if response.ok:
                                                        body = response.body()
                                                        if body and len(body) > 500:
                                                            if body[:4] == b'%PDF':
                                                                pdf_data = body
                                                                log(f"✓ PDF fetched from {selector} ({len(pdf_data)} bytes)")
                                                                break
                                                            else:
                                                                log(f"⚠ Content from {selector} is not PDF (starts with: {body[:20]})")
                                        
                                        if not pdf_data:
                                            log(f"⚠ No valid PDF elements found")
                                    except Exception as e:
                                        log(f"⚠ Error finding PDF element: {str(e)[:100]}")
                                
                                # Method 4: Print page as PDF (last resort)
                                if not pdf_data:
                                    try:
                                        log(f"Generating PDF from page content as last resort...")
                                        pdf_data = target_page.pdf(
                                            format="A4",
                                            print_background=True,
                                            margin={"top": "0.5cm", "right": "0.5cm", "bottom": "0.5cm", "left": "0.5cm"}
                                        )
                                        log(f"✓ PDF generated from page ({len(pdf_data)} bytes)")
                                    except Exception as e:
                                        log(f"✗ PDF generation failed: {str(e)[:100]}")
                                
                                if new_page:
                                    try:
                                        new_page.close()
                                    except:
                                        pass
                    
                    except Exception as e:
                        log(f"✗ {ca_number}: Error finding View Bill button - {str(e)[:100]}")
                
                except Exception as e:
                    log(f"✗ {ca_number}: Captcha handling error - {str(e)[:100]}")
                
                browser.close()
        
        except Exception as e:
            log(f"✗ {ca_number}: {str(e)[:160]}")
        
        if pdf_data and len(pdf_data) > 500:
            filename = f"APEPDCL_{ca_number}.pdf"
            # Rename with extracted date
            filename = rename_pdf_with_date(filename, pdf_data, "APEPDCL")
            downloads[session_id]["files"][filename] = pdf_data
            log(f"✓ {ca_number}: Downloaded ({len(pdf_data)} bytes) - {filename}")
        else:
            log(f"✗ {ca_number}: Could not capture PDF")
        
        downloads[session_id]["completed"] += 1
        downloads[session_id]["progress"] = int(downloads[session_id]["completed"] * 100 / downloads[session_id]["total"])
        
        # Small delay between requests
        if idx < len(ca_numbers) - 1:
            time.sleep(2)
    
    downloads[session_id]["status"] = "completed"


# -------------------- Central Power Distribution Company of Andhra Pradesh (APCPDCL) --------------------
def download_apcpdcl(ca_numbers, session_id, bill_months=None):
    """
    Download bills from Central Power Distribution Company of Andhra Pradesh (APCPDCL)
    URL: https://www.apcpdcl.in/ConsumerDashboard/BillandPayHistory?consumernames=MD%20Abdul%20Jaleel&uscno={CA_NUMBER}
    
    Args:
        ca_numbers: List of CA numbers
        session_id: Session ID for tracking
        bill_months: List of specific months to download (e.g., ["DEC-2025", "NOV-2025"]). If None, downloads the most recent.
    """
    try:
        from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
    except Exception:
        downloads[session_id] = {
            "status": "error",
            "logs": ["Playwright not installed. Run: pip install playwright && playwright install chromium"]
        }
        return

    # Handle both single month (string) and multiple months (list) for backward compatibility
    if isinstance(bill_months, str):
        bill_months = [bill_months]
    if not bill_months:
        bill_months = [None]  # None means download most recent

    total_requests = len(ca_numbers) * len(bill_months)
    downloads[session_id] = {
        "status": "downloading",
        "progress": 0,
        "completed": 0,
        "total": total_requests,
        "logs": [],
        "files": {}
    }

    def log(m): _log(session_id, m)

    for ca_number in ca_numbers:
        ca_number = str(ca_number).strip()
        for bill_month in bill_months:
            pdf_data = None
            
            try:
                log(f"Processing CA: {ca_number} (APCPDCL)")
                if bill_month:
                    log(f"Target month: {bill_month}")
                
                with sync_playwright() as p:
                    browser = p.chromium.launch(
                        headless=True,
                        args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-blink-features=AutomationControlled"]
                    )
                    context = browser.new_context(
                        accept_downloads=True,
                        ignore_https_errors=True,
                        user_agent=("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                                    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"),
                        viewport={"width": 1366, "height": 900}
                    )
                    context.add_init_script("Object.defineProperty(navigator,'webdriver',{get:()=>undefined})")
                    
                    page = context.new_page()
                    
                    # Navigate to the bill history page with CA number
                    url = f"https://www.apcpdcl.in/ConsumerDashboard/BillandPayHistory?consumernames=MD%20Abdul%20Jaleel&uscno={ca_number}"
                    log(f"Loading bill history page for CA: {ca_number}")
                    page.goto(url, wait_until="domcontentloaded", timeout=60000)
                    
                    # Wait for page to load
                    try:
                        page.wait_for_load_state("networkidle", timeout=15000)
                    except:
                        pass
                    
                    # Wait a bit more for dynamic content
                    time.sleep(3)
                    
                    # Check if we have bill history table
                    try:
                        # Look for the bill history table
                        bill_table = page.query_selector('table')
                        if not bill_table:
                            log(f"✗ {ca_number}: No bill history table found")
                            browser.close()
                            continue
                        
                        log(f"✓ Found bill history table for CA: {ca_number}")
                        
                        # Find all rows in the bill history table
                        table_rows = page.query_selector_all('table tr')
                        if len(table_rows) <= 1:  # Only header row
                            log(f"✗ {ca_number}: No bill data found in table")
                            browser.close()
                            continue
                        
                        # Look for the specific month or the most recent one
                        target_button = None
                        target_row_index = None
                        found_months = []
                        
                        for row_index, row in enumerate(table_rows[1:], 1):  # Skip header row, start from 1
                            try:
                                # Get all cells in the row
                                cells = row.query_selector_all('td')
                                if len(cells) < 4:  # Need at least month, date, amount, download columns
                                    continue
                                
                                # Extract month from the row (usually in first or second column)
                                month_text = ""
                                for i in range(min(3, len(cells))):  # Check first 3 columns for month
                                    cell_text = cells[i].inner_text().strip()
                                    if any(month in cell_text.upper() for month in ['JAN', 'FEB', 'MAR', 'APR', 'MAY', 'JUN', 
                                                                                   'JUL', 'AUG', 'SEP', 'OCT', 'NOV', 'DEC']):
                                        month_text = cell_text
                                        break
                                
                                if not month_text:
                                    continue
                                
                                found_months.append(month_text)
                                
                                # Look for "Current Bill" button in this row using multiple methods
                                current_bill_buttons = []
                                
                                # Method 1: Try the specific CSS selector pattern (adjusted for row)
                                try:
                                    specific_selector = f'body > div:nth-child(3) > div:nth-child(5) > div:nth-child(1) > table:nth-child(2) > tbody:nth-child(2) > tr:nth-child({row_index + 1}) > td:nth-child(5) > button:nth-child(1)'
                                    specific_button = page.query_selector(specific_selector)
                                    if specific_button:
                                        current_bill_buttons.append(specific_button)
                                        log(f"✓ Found button using specific CSS selector for row {row_index + 1}")
                                except Exception as e:
                                    log(f"⚠ Specific selector failed for row {row_index + 1}: {str(e)[:50]}")
                                
                                # Method 2: Look within the row for buttons
                                if not current_bill_buttons:
                                    current_bill_buttons = row.query_selector_all('input[value="Current Bill"], button:has-text("Current Bill")')
                                
                                # Method 3: Try alternative selectors within the row
                                if not current_bill_buttons:
                                    current_bill_buttons = row.query_selector_all('input[type="button"], button')
                                    current_bill_buttons = [btn for btn in current_bill_buttons 
                                                          if btn.inner_text() and 'current' in btn.inner_text().lower()]
                                
                                # Method 4: Look for any button in the 5th column (download column)
                                if not current_bill_buttons and len(cells) >= 5:
                                    download_cell = cells[4]  # 5th column (0-indexed)
                                    current_bill_buttons = download_cell.query_selector_all('button, input[type="button"]')
                                
                                if current_bill_buttons:
                                    button = current_bill_buttons[0]
                                    
                                    # Check if this is the month we want
                                    if bill_month:
                                        if bill_month.upper() in month_text.upper():
                                            target_button = button
                                            target_row_index = row_index
                                            log(f"✓ Found target month {bill_month} with Current Bill button in row {row_index + 1}")
                                            break
                                    else:
                                        # If no specific month requested, take the first available (most recent)
                                        if not target_button:
                                            target_button = button
                                            target_row_index = row_index
                                            log(f"✓ Found Current Bill button for month: {month_text} in row {row_index + 1}")
                                            break
                            
                            except Exception as e:
                                log(f"⚠ Error processing table row {row_index + 1}: {str(e)[:100]}")
                                continue
                        
                        if found_months:
                            log(f"Available months: {', '.join(found_months[:5])}{'...' if len(found_months) > 5 else ''}")
                        
                        if not target_button:
                            if bill_month:
                                log(f"✗ {ca_number} ({bill_month}): No Current Bill button found for month {bill_month}")
                            else:
                                log(f"✗ {ca_number}: No Current Bill buttons found")
                            
                            # Last resort: Try the exact CSS selector provided
                            log(f"🔄 Trying exact CSS selector as fallback...")
                            try:
                                exact_button = page.query_selector('body > div:nth-child(3) > div:nth-child(5) > div:nth-child(1) > table:nth-child(2) > tbody:nth-child(2) > tr:nth-child(1) > td:nth-child(5) > button:nth-child(1)')
                                if exact_button and exact_button.is_visible():
                                    target_button = exact_button
                                    log(f"✓ Found button using exact CSS selector (first row)")
                                else:
                                    # Try a few more rows with the same pattern
                                    for row_num in range(2, 6):  # Try rows 2-5
                                        selector = f'body > div:nth-child(3) > div:nth-child(5) > div:nth-child(1) > table:nth-child(2) > tbody:nth-child(2) > tr:nth-child({row_num}) > td:nth-child(5) > button:nth-child(1)'
                                        button = page.query_selector(selector)
                                        if button and button.is_visible():
                                            target_button = button
                                            log(f"✓ Found button using exact CSS selector (row {row_num})")
                                            break
                            except Exception as e:
                                log(f"⚠ Exact CSS selector also failed: {str(e)[:100]}")
                            
                            if not target_button:
                                browser.close()
                                downloads[session_id]["completed"] += 1
                                downloads[session_id]["progress"] = int(downloads[session_id]["completed"] * 100 / total_requests)
                                continue
                        
                        # Set up download listener before clicking
                        download_info = {"download": None}
                        
                        def handle_download(download):
                            download_info["download"] = download
                            log(f"Download started: {download.suggested_filename}")
                        
                        page.on("download", handle_download)
                        
                        # Click the Current Bill button
                        try:
                            button_text = target_button.inner_text() or target_button.get_attribute('value') or 'Current Bill'
                            log(f"Clicking Current Bill button: {button_text}")
                            
                            # Scroll the button into view first
                            try:
                                target_button.scroll_into_view_if_needed()
                                time.sleep(1)
                            except:
                                pass
                            
                            # Set up listeners for new pages/popups BEFORE clicking
                            new_page_info = {"page": None, "ready": False}
                            
                            def handle_new_page(new_page):
                                new_page_info["page"] = new_page
                                log(f"✓ New page/popup detected: {new_page.url}")
                            
                            context.on("page", handle_new_page)
                            
                            # Click the button and wait for popup
                            click_success = False
                            
                            try:
                                # Method 1: Regular click with popup expectation
                                try:
                                    with context.expect_page(timeout=15000) as popup_info:
                                        target_button.click(timeout=5000)
                                        click_success = True
                                        log(f"✓ Button clicked successfully (regular click)")
                                    
                                    # Get the popup page
                                    popup_page = popup_info.value
                                    new_page_info["page"] = popup_page
                                    log(f"✓ Popup captured: {popup_page.url}")
                                    
                                except Exception as e:
                                    log(f"⚠ Regular click with popup expectation failed: {str(e)[:100]}")
                                    
                                    # Method 2: Force click if regular click failed
                                    try:
                                        target_button.click(force=True, timeout=5000)
                                        click_success = True
                                        log(f"✓ Button clicked successfully (force click)")
                                    except Exception as e2:
                                        log(f"⚠ Force click failed: {str(e2)[:100]}")
                                        
                                        # Method 3: JavaScript click if both failed
                                        try:
                                            page.evaluate("(element) => element.click()", target_button)
                                            click_success = True
                                            log(f"✓ Button clicked successfully (JavaScript click)")
                                        except Exception as e3:
                                            log(f"⚠ JavaScript click failed: {str(e3)[:100]}")
                            
                            except Exception as e:
                                log(f"⚠ All click methods failed: {str(e)[:100]}")
                            
                            if not click_success:
                                log(f"✗ Could not click the Current Bill button")
                                raise Exception("Could not click the Current Bill button")
                            
                            # Wait for popup or new page to appear
                            log(f"⏳ Waiting for bill popup/new page...")
                            for i in range(30):  # Wait up to 30 seconds
                                if new_page_info["page"]:
                                    break
                                
                                # Check if pages list has grown
                                current_pages = context.pages
                                if len(current_pages) > 1:
                                    new_page_info["page"] = current_pages[-1]  # Get the latest page
                                    log(f"✓ Found new page in context: {new_page_info['page'].url}")
                                    break
                                
                                time.sleep(1)
                            
                            # Check for direct download first
                            if download_info["download"]:
                                download = download_info["download"]
                                pdf_data = download.read_all_bytes()
                                log(f"✓ Direct download captured for CA: {ca_number} ({len(pdf_data)} bytes)")
                            
                            # If no direct download, try to get PDF from popup/new page
                            elif new_page_info["page"]:
                                popup_page = new_page_info["page"]
                                log(f"✓ Processing popup page: {popup_page.url}")
                                
                                try:
                                    # Wait for the popup page to fully load
                                    popup_page.wait_for_load_state("networkidle", timeout=15000)
                                    log(f"✓ Popup page loaded completely")
                                    
                                    # Generate PDF from the popup
                                    pdf_data = popup_page.pdf(
                                        format="A4",
                                        print_background=True,
                                        margin={"top": "0.5cm", "right": "0.5cm", "bottom": "0.5cm", "left": "0.5cm"},
                                        wait_for_fonts=True
                                    )
                                    log(f"✓ Generated PDF from popup for CA: {ca_number} ({len(pdf_data)} bytes)")
                                    
                                    # Close the popup
                                    try:
                                        popup_page.close()
                                    except:
                                        pass
                                    
                                except Exception as e:
                                    log(f"✗ Error processing popup: {str(e)[:100]}")
                            
                            else:
                                log(f"⚠ {ca_number}: No popup detected and no direct download")
                        
                        except Exception as e:
                            log(f"✗ {ca_number}: Error in bill download process - {str(e)[:100]}")
                    
                    except Exception as e:
                        log(f"✗ {ca_number}: Error processing bill history - {str(e)[:100]}")
                    
                    browser.close()
                    
            except Exception as e:
                log(f"✗ {ca_number} ({bill_month or 'latest'}): Error - {str(e)[:160]}")

            if pdf_data and len(pdf_data) > 500:
                # Create filename with month if specified
                if bill_month:
                    filename = f"APCPDCL_{ca_number}_{bill_month}.pdf"
                else:
                    filename = f"APCPDCL_{ca_number}.pdf"
                
                # Rename with extracted date
                filename = rename_pdf_with_date(filename, pdf_data, "APCPDCL")
                downloads[session_id]["files"][filename] = pdf_data
                log(f"✓ {ca_number} ({bill_month or 'latest'}): Downloaded ({len(pdf_data)} bytes) - {filename}")
            else:
                log(f"✗ {ca_number} ({bill_month or 'latest'}): Could not capture PDF")

            downloads[session_id]["completed"] += 1
            downloads[session_id]["progress"] = int(downloads[session_id]["completed"] * 100 / total_requests)

    downloads[session_id]["status"] = "completed"


# -------------------- Southern Power Distribution Company of Andhra Pradesh (APSPDCL) --------------------
def download_apspdcl(ca_numbers, session_id):
    """
    Download bills from Southern Power Distribution Company of Andhra Pradesh (APSPDCL)
    URL: https://www.apspdcl.in/ConsumerDashboard/lastmonthbill.jsp?serviceno={CA_NUMBER}
    """
    try:
        from playwright.sync_api import sync_playwright
    except Exception:
        downloads[session_id] = {
            "status": "error",
            "logs": ["Playwright not installed. Run: pip install playwright && playwright install chromium"]
        }
        return

    downloads[session_id] = {
        "status": "downloading",
        "progress": 0,
        "completed": 0,
        "total": len(ca_numbers),
        "logs": [],
        "files": {}
    }

    def log(m): _log(session_id, m)

    for ca_number in ca_numbers:
        ca_number = str(ca_number).strip()
        
        if not ca_number:
            log(f"✗ Skipping empty CA number")
            downloads[session_id]["completed"] += 1
            downloads[session_id]["progress"] = int(downloads[session_id]["completed"] * 100 / downloads[session_id]["total"])
            continue
        
        pdf_data = None
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(
                    headless=True,
                    args=["--no-sandbox", "--disable-dev-shm-usage"]
                )
                context = browser.new_context(
                    viewport={"width": 1366, "height": 900}
                )
                page = context.new_page()
                
                # Navigate directly to bill page with CA number
                url = f"https://www.apspdcl.in/ConsumerDashboard/lastmonthbill.jsp?serviceno={ca_number}"
                log(f"Loading APSPDCL bill page for CA: {ca_number}")
                page.goto(url, wait_until="domcontentloaded", timeout=60000)
                
                # Wait for page to load
                page.wait_for_timeout(5000)
                
                try:
                    page.wait_for_load_state("networkidle", timeout=10000)
                except:
                    pass
                
                log(f"Bill page loaded for CA: {ca_number}")
                

                
                # Try to find and click the Print Bill button with multiple selectors
                try:
                    log(f"Looking for Print Bill button...")
                    
                    # Try multiple possible selectors
                    button_selectors = [
                        '.invoice-btn-btn',
                        'button.invoice-btn-btn',
                        'a.invoice-btn-btn',
                        'button:has-text("Print")',
                        'a:has-text("Print")',
                        'button:has-text("Download")',
                        'a:has-text("Download")',
                        '[onclick*="print"]',
                        '[onclick*="Print"]'
                    ]
                    
                    button_found = False
                    found_selector = None
                    for selector in button_selectors:
                        try:
                            elements = page.query_selector_all(selector)
                            if elements:
                                log(f"Found {len(elements)} element(s) with selector: {selector}")
                                # Try to find a visible one
                                for elem in elements:
                                    if elem.is_visible():
                                        log(f"✓ Visible button found with selector: {selector}")
                                        found_selector = selector
                                        button_found = True
                                        break
                                if button_found:
                                    break
                        except:
                            continue
                    
                    if not button_found:
                        log(f"Print button not found with any selector, checking page content...")
                        # Log page text to see what's available
                        page_text = page.evaluate("() => document.body.innerText")
                        log(f"Page text preview: {page_text[:300]}")
                        
                        # Try to generate PDF directly from the page
                        log(f"Generating PDF from bill page...")
                        pdf_data = page.pdf(format="A4", print_background=True)
                        log(f"✓ {ca_number}: PDF generated from page ({len(pdf_data)} bytes)")
                    else:
                        log(f"Attempting to click button with selector: {found_selector}")
                    
                        # Try to capture download or new page
                        try:
                            # Method 1: Try regular click with download capture
                            with page.expect_download(timeout=5000) as download_info:
                                try:
                                    page.click(found_selector, timeout=10000)
                                    log(f"Button clicked, waiting for download...")
                                except:
                                    # Try JavaScript click
                                    log(f"Regular click failed, trying JavaScript click...")
                                    page.evaluate(f'document.querySelector("{found_selector}").click()')
                            
                            download = download_info.value
                            log(f"Download captured: {download.suggested_filename}")
                            
                            # Save download to memory
                            import pathlib
                            download_path = download.path()
                            if download_path:
                                pdf_data = pathlib.Path(download_path).read_bytes()
                                log(f"✓ {ca_number}: PDF downloaded ({len(pdf_data)} bytes)")
                            else:
                                log(f"✗ {ca_number}: Download path is None")
                        
                        except Exception as download_err:
                            log(f"Download not captured: {str(download_err)[:100]}")
                            log(f"Trying to click and check for new page...")
                            
                            # Method 2: Click and check for new page
                            try:
                                page.click(found_selector, timeout=10000)
                                log(f"Button clicked")
                            except:
                                # JavaScript click as fallback
                                log(f"Using JavaScript click...")
                                page.evaluate(f'document.querySelector("{found_selector}").click()')
                            
                            page.wait_for_timeout(3000)
                            
                            # Check all pages
                            all_pages = context.pages
                            log(f"Total pages: {len(all_pages)}")
                            
                            if len(all_pages) > 1:
                                # New page opened
                                pdf_page = all_pages[-1]
                                log(f"New page opened: {pdf_page.url}")
                                pdf_page.wait_for_load_state("domcontentloaded", timeout=30000)
                                pdf_page.wait_for_timeout(3000)
                                
                                # Check if it's a PDF
                                if pdf_page.url.endswith('.pdf') or 'pdf' in pdf_page.url.lower():
                                    log(f"PDF URL detected, downloading...")
                                    response = context.request.get(pdf_page.url, timeout=30000)
                                    if response.ok:
                                        pdf_data = response.body()
                                        log(f"✓ {ca_number}: PDF from new page ({len(pdf_data)} bytes)")
                                else:
                                    # Generate PDF from page
                                    log(f"Generating PDF from page...")
                                    pdf_data = pdf_page.pdf(format="A4", print_background=True)
                                    log(f"✓ {ca_number}: PDF generated ({len(pdf_data)} bytes)")
                                
                                pdf_page.close()
                            else:
                                # Same page - might have navigated
                                log(f"Checking current page URL: {page.url}")
                                page.wait_for_timeout(3000)
                                
                                if page.url.endswith('.pdf') or 'pdf' in page.url.lower():
                                    log(f"Page navigated to PDF, downloading...")
                                    response = context.request.get(page.url, timeout=30000)
                                    if response.ok:
                                        pdf_data = response.body()
                                        log(f"✓ {ca_number}: PDF from URL ({len(pdf_data)} bytes)")
                                else:
                                    # Generate PDF from current page
                                    log(f"Generating PDF from current page...")
                                    pdf_data = page.pdf(format="A4", print_background=True)
                                    log(f"✓ {ca_number}: PDF generated ({len(pdf_data)} bytes)")
                    
                except Exception as e:
                    log(f"✗ {ca_number}: Error with Print Bill button - {str(e)[:200]}")
                
                browser.close()

        except Exception as e:
            log(f"✗ {ca_number}: Error - {str(e)[:200]}")

        if pdf_data and len(pdf_data) > 500:
            filename = f"APSPDCL_{ca_number}.pdf"
            # Rename with extracted date
            filename = rename_pdf_with_date(filename, pdf_data, "APSPDCL")
            downloads[session_id]["files"][filename] = pdf_data
            log(f"✓ {ca_number}: Downloaded ({len(pdf_data)} bytes) - {filename}")
        else:
            log(f"✗ {ca_number}: Could not capture PDF")

        downloads[session_id]["completed"] += 1
        downloads[session_id]["progress"] = int(downloads[session_id]["completed"] * 100 / downloads[session_id]["total"])

    downloads[session_id]["status"] = "completed"


# -------------------- BESCOM (Bangalore Electricity Supply Company) --------------------
def download_bescom(credentials, session_id, fetch_history=False, bill_month=None, capsolver_api_key=None):
    """
    Download bills from BESCOM portal using the provided standalone script
    
    Args:
        credentials: List of dicts with keys: username, password, ca_number (optional)
        session_id: Session ID for tracking progress
        fetch_history: Whether to download all available bills
        bill_month: Specific bill month to download (e.g., "NOV-2025")
        capsolver_api_key: CapSolver API key for captcha solving
    """
    try:
        from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError
        import base64
        import traceback
        from pathlib import Path
        from datetime import datetime
        
        # Initialize session
        total_accounts = len(credentials)
        downloads[session_id] = {
            "status": "downloading",
            "progress": 0,
            "completed": 0,
            "total": total_accounts,
            "logs": [],
            "files": {}
        }
        
        _log(session_id, f"🚀 Starting BESCOM download for {total_accounts} account(s)")
        
        # Default CapSolver API key if not provided
        if not capsolver_api_key:
            capsolver_api_key = "CAP-ADCA94D1B80ACF6A5A0E9E57B4E90158"
        
        def solve_captcha(page, captcha_element_xpath, captcha_input_xpath, max_retries=3):
            """Solve image captcha using CapSolver API"""
            for attempt in range(max_retries):
                try:
                    _log(session_id, f"🔍 Captcha attempt {attempt + 1}/{max_retries}")
                    
                    # Get captcha element
                    captcha_element = page.locator(captcha_element_xpath)
                    if not captcha_element.is_visible():
                        _log(session_id, "❌ Captcha element not visible")
                        continue
                    
                    # Screenshot captcha
                    image_bytes = captcha_element.screenshot()
                    
                    # Solve captcha using CapSolver
                    captcha_text = ocr_captcha(image_bytes, capsolver_api_key, session_id)
                    if not captcha_text:
                        continue
                    
                    # BESCOM captchas are always in uppercase, so convert to uppercase
                    captcha_text = captcha_text.upper().strip()
                    
                    # Log the exact captcha text being used
                    _log(session_id, f"🔤 Captcha text to fill: '{captcha_text}' (length: {len(captcha_text)})")
                    
                    # Clear the captcha input field first
                    captcha_input = page.locator(captcha_input_xpath)
                    _log(session_id, f"🧹 Clearing captcha input field")
                    captcha_input.clear()
                    
                    # Wait a moment for the field to be cleared
                    time.sleep(1)
                    
                    # Fill captcha with exact text
                    _log(session_id, f"✏️ Filling captcha field with: '{captcha_text}'")
                    captcha_input.fill(captcha_text)
                    
                    # Verify what was actually filled
                    filled_value = captcha_input.input_value()
                    _log(session_id, f"✅ Captcha field now contains: '{filled_value}'")
                    
                    if filled_value != captcha_text:
                        _log(session_id, f"⚠️ Mismatch! Expected: '{captcha_text}', Got: '{filled_value}'")
                    
                    return True
                    
                except Exception as e:
                    _log(session_id, f"❌ Captcha attempt {attempt + 1} failed: {str(e)}")
                    if attempt < max_retries - 1:
                        time.sleep(2)
            
            raise Exception("Failed to solve captcha after all attempts")
        
        def ocr_captcha(image_bytes, api_key, session_id):
            """Solve captcha using CapSolver API"""
            if not api_key:
                _log(session_id, "❌ CapSolver API key not provided")
                return ""
            
            try:
                _log(session_id, "🔍 Solving captcha with CapSolver...")
                
                # Convert image bytes to base64
                image_base64 = base64.b64encode(image_bytes).decode('utf-8')
                
                if not image_base64 or len(image_base64) < 100:
                    _log(session_id, f"❌ Invalid captcha image (too short: {len(image_base64)} chars)")
                    return ""
                
                # Create task
                create_task_url = "https://api.capsolver.com/createTask"
                task_payload = {
                    "clientKey": api_key,
                    "task": {
                        "type": "ImageToTextTask",
                        "body": image_base64,
                        "module": "common",
                        "score": 0.5,
                        "case": False  # Let CapSolver return natural case, we'll convert to uppercase manually
                    }
                }
                
                response = requests.post(create_task_url, json=task_payload, timeout=30)
                
                if response.status_code != 200:
                    _log(session_id, f"❌ CapSolver HTTP error: {response.status_code}")
                    return ""
                
                result = response.json()
                error_id = result.get("errorId", -1)
                
                if error_id != 0:
                    error_msg = result.get('errorDescription', 'Unknown error')
                    _log(session_id, f"❌ CapSolver error: {error_msg}")
                    return ""
                
                # Check if solution is already available
                if result.get("status") == "ready":
                    captcha_text = result.get("solution", {}).get("text", "")
                    if captcha_text:
                        _log(session_id, f"✅ Captcha solved immediately: '{captcha_text}'")
                        return captcha_text
                
                # Get task ID and poll for result
                task_id = result.get("taskId")
                if not task_id:
                    _log(session_id, "❌ No task ID received from CapSolver")
                    return ""
                
                # Poll for result
                get_result_url = "https://api.capsolver.com/getTaskResult"
                for attempt in range(30):  # Try for up to 30 seconds
                    time.sleep(1)
                    result_payload = {
                        "clientKey": api_key,
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
                            _log(session_id, f"✅ Captcha solved: '{captcha_text}'")
                            return captcha_text
                    elif status == "processing":
                        continue
                    elif status == "failed":
                        error_desc = result.get('errorDescription', 'Unknown')
                        _log(session_id, f"❌ CapSolver task failed: {error_desc}")
                        return ""
                
                _log(session_id, "❌ Captcha solving timeout after 30 seconds")
                return ""
                
            except Exception as e:
                _log(session_id, f"❌ Captcha solving error: {str(e)[:200]}")
                return ""
        
        # Process each account
        with sync_playwright() as p:
            for account_idx, account in enumerate(credentials):
                try:
                    username = account.get('username', '')
                    password = account.get('password', '')
                    target_ca_number = account.get('ca_number')
                    
                    if not username or not password:
                        _log(session_id, f"❌ Account {account_idx + 1}: Missing username or password")
                        continue
                    
                    _log(session_id, f"🔄 Processing Account {account_idx + 1}/{total_accounts}: {username}")
                    if target_ca_number:
                        _log(session_id, f"🎯 Target CA Number: {target_ca_number}")
                    
                    # Launch browser
                    browser = p.chromium.launch(
                        headless=True,  # Run in headless mode for production
                        timeout=120000,
                        args=[
                            "--ignore-ssl-errors=yes",
                            "--ignore-certificate-errors",
                        ]
                    )
                    context = browser.new_context(ignore_https_errors=True)
                    page = context.new_page()
                    
                    # Setup dialog handler for alerts
                    alert_message = None
                    def handle_dialog(dialog):
                        nonlocal alert_message
                        alert_message = dialog.message()
                        dialog.dismiss()
                    
                    page.on("dialog", handle_dialog)
                    
                    # Login
                    login_url = "https://bescom.co.in/bescom/login"
                    _log(session_id, "🌐 Navigating to login page")
                    page.goto(login_url, timeout=120000)
                    page.wait_for_load_state("networkidle")
                    
                    _log(session_id, "📝 Filling login credentials")
                    page.locator('input[formcontrolname="userId"]').fill(username)
                    page.locator('input[formcontrolname="password"]').fill(password)
                    
                    # Solve captcha
                    _log(session_id, "🔍 Attempting to solve captcha")
                    solve_captcha(page, "//canvas[@id='captcha']", "//input[@id='cpatchaInput']")
                    
                    # Submit login
                    _log(session_id, "🚀 Submitting login form")
                    login_button = page.locator('button[type="submit"]')
                    
                    # Take a screenshot before clicking login
                    try:
                        page.screenshot(path=f"bescom_before_login_{account_idx}.png")
                        _log(session_id, f"📸 Screenshot saved: bescom_before_login_{account_idx}.png")
                    except:
                        pass
                    
                    login_button.click()
                    
                    # Wait for login to complete
                    _log(session_id, "⏳ Waiting for login response...")
                    page.wait_for_load_state("networkidle")
                    time.sleep(5)  # Additional wait for page to stabilize
                    
                    # Take a screenshot after login attempt
                    try:
                        page.screenshot(path=f"bescom_after_login_{account_idx}.png")
                        _log(session_id, f"📸 Screenshot saved: bescom_after_login_{account_idx}.png")
                    except:
                        pass
                    
                    # Check current URL to see if we were redirected
                    current_url = page.url
                    _log(session_id, f"🌐 Current URL after login: {current_url}")
                    
                    # Check for any error messages or alerts
                    try:
                        # Look for common error message selectors
                        error_selectors = [
                            ".alert-danger",
                            ".error-message", 
                            ".invalid-feedback",
                            "[class*='error']",
                            ".text-danger"
                        ]
                        
                        for selector in error_selectors:
                            error_elements = page.locator(selector).all()
                            for element in error_elements:
                                if element.is_visible():
                                    error_text = element.text_content()
                                    if error_text and error_text.strip():
                                        _log(session_id, f"❌ Error message found: {error_text.strip()}")
                    except:
                        pass
                    
                    # Check for login form still being present (indicates failed login)
                    login_form_still_present = page.locator('input[formcontrolname="userId"]').count() > 0
                    if login_form_still_present:
                        _log(session_id, "⚠️ Login form still present - login may have failed")
                        
                        # Try to get any validation messages
                        try:
                            form_errors = page.locator("form .ng-invalid, form .error, .form-error").all()
                            for error in form_errors:
                                if error.is_visible():
                                    error_text = error.text_content()
                                    if error_text:
                                        _log(session_id, f"📝 Form validation error: {error_text}")
                        except:
                            pass
                    else:
                        _log(session_id, "✅ Login form no longer present - login appears successful")
                    
                    # Check for login errors
                    error_element = page.locator("form.ng-submitted")
                    if error_element.is_visible():
                        error_text = error_element.text_content()
                        if "Invalid UserName and Password" in error_text:
                            _log(session_id, f"❌ Account {account_idx + 1}: Invalid username or password")
                            browser.close()
                            continue
                        elif "captcha" in error_text.lower():
                            _log(session_id, f"❌ Account {account_idx + 1}: Captcha validation failed")
                            browser.close()
                            continue
                        else:
                            _log(session_id, f"❌ Account {account_idx + 1}: Login error: {error_text}")
                    
                    _log(session_id, "✅ Login successful")
                    
                    # Wait for dashboard to load
                    _log(session_id, "⏳ Waiting for dashboard")
                    
                    # Try multiple selectors for the dashboard elements
                    dashboard_selectors = [
                        ".multiselect-dropdown",
                        "select[name='billDates']",
                        ".dropdown-btn",
                        "[class*='multiselect']",
                        "[class*='dropdown']",
                        "form",
                        ".container"
                    ]
                    
                    dashboard_loaded = False
                    for selector in dashboard_selectors:
                        try:
                            _log(session_id, f"🔍 Trying selector: {selector}")
                            page.wait_for_selector(selector, state="visible", timeout=15000)
                            _log(session_id, f"✅ Found dashboard element: {selector}")
                            dashboard_loaded = True
                            break
                        except Exception as e:
                            _log(session_id, f"⚠️ Selector {selector} not found: {str(e)[:100]}")
                            continue
                    
                    if not dashboard_loaded:
                        _log(session_id, "❌ Dashboard elements not found, trying to continue anyway...")
                        # Take a screenshot for debugging
                        try:
                            page.screenshot(path=f"bescom_debug_{account_idx}.png")
                            _log(session_id, f"📸 Debug screenshot saved: bescom_debug_{account_idx}.png")
                        except:
                            pass
                    
                    page.wait_for_load_state("networkidle")
                    time.sleep(5)
                    
                    # Get available consumer IDs - try multiple approaches
                    _log(session_id, "📋 Fetching available consumer IDs")
                    
                    bill_ids = []
                    
                    # Method 1: Try original selector
                    try:
                        bill_ids_locator = page.locator(".dropdown-list .multiselect-item-checkbox input[type='checkbox']")
                        bill_ids = [
                            option.get_attribute("aria-label")
                            for option in bill_ids_locator.all()
                            if not option.get_attribute("disabled")
                        ]
                        if bill_ids:
                            _log(session_id, f"📋 Method 1 - Found consumer IDs: {bill_ids}")
                    except Exception as e:
                        _log(session_id, f"⚠️ Method 1 failed: {str(e)[:100]}")
                    
                    # Method 2: Try alternative selectors if Method 1 failed
                    if not bill_ids:
                        alternative_selectors = [
                            "input[type='checkbox'][aria-label]",
                            ".multiselect-item input",
                            "select option",
                            "[class*='consumer'] option",
                            "[class*='account'] option"
                        ]
                        
                        for alt_selector in alternative_selectors:
                            try:
                                _log(session_id, f"🔍 Trying alternative selector: {alt_selector}")
                                elements = page.locator(alt_selector).all()
                                if elements:
                                    for element in elements:
                                        label = element.get_attribute("aria-label") or element.get_attribute("value") or element.text_content()
                                        if label and label.strip():
                                            bill_ids.append(label.strip())
                                    if bill_ids:
                                        _log(session_id, f"📋 Method 2 - Found consumer IDs with {alt_selector}: {bill_ids}")
                                        break
                            except Exception as e:
                                _log(session_id, f"⚠️ Alternative selector {alt_selector} failed: {str(e)[:50]}")
                                continue
                    
                    # Method 3: If still no IDs found, try to find any dropdown or select elements
                    if not bill_ids:
                        try:
                            _log(session_id, "🔍 Method 3 - Looking for any dropdown elements...")
                            # Look for select elements
                            selects = page.locator("select").all()
                            for select in selects:
                                options = select.locator("option").all()
                                for option in options:
                                    value = option.get_attribute("value") or option.text_content()
                                    if value and value.strip() and value != "":
                                        bill_ids.append(value.strip())
                            
                            if bill_ids:
                                _log(session_id, f"📋 Method 3 - Found options: {bill_ids}")
                        except Exception as e:
                            _log(session_id, f"⚠️ Method 3 failed: {str(e)[:100]}")
                    
                    # If we still have no consumer IDs, log page content for debugging
                    if not bill_ids:
                        _log(session_id, "❌ No consumer IDs found. Logging page content for debugging...")
                        try:
                            page_content = page.content()
                            # Log first 500 chars of page content
                            content_snippet = page_content[:500].replace('\n', ' ').replace('\r', ' ')
                            _log(session_id, f"📄 Page content snippet: {content_snippet}")
                            
                            # Look for any elements that might contain account info
                            all_text = page.locator("body").text_content()
                            if "consumer" in all_text.lower() or "account" in all_text.lower():
                                _log(session_id, "🔍 Found consumer/account text in page")
                            
                        except Exception as e:
                            _log(session_id, f"❌ Could not get page content: {str(e)[:100]}")
                        
                        # Continue with target CA number if provided
                        if target_ca_number:
                            _log(session_id, f"🎯 No dropdown found, but will try to use target CA: {target_ca_number}")
                            bill_ids = [target_ca_number]
                        else:
                            _log(session_id, "❌ No consumer IDs found and no target CA specified. Skipping account.")
                            browser.close()
                            continue
                    
                    _log(session_id, f"📋 Found consumer IDs: {bill_ids}")
                    
                    # Filter consumer IDs if target CA number is specified
                    if target_ca_number:
                        _log(session_id, f"🎯 Looking for specific CA number: {target_ca_number}")
                        matching_ids = [bid for bid in bill_ids if target_ca_number in str(bid)]
                        if not matching_ids:
                            _log(session_id, f"⚠️ CA number '{target_ca_number}' not found in available consumer IDs")
                            browser.close()
                            continue
                        bill_ids = matching_ids
                        _log(session_id, f"✅ Found matching CA number(s): {bill_ids}")
                    
                    # Process each consumer ID
                    for bill_id in bill_ids:
                        _log(session_id, f"🔄 Processing consumer ID: {bill_id}")
                        
                        # Try to select consumer ID from dropdown - multiple methods
                        selection_successful = False
                        
                        # Method 1: Try original dropdown selection
                        try:
                            selected = page.query_selector("span.selected-item span")
                            if selected:
                                is_selected = selected.text_content().strip().startswith(str(bill_id))
                                if not is_selected:
                                    multiselect_dropdown = page.locator(".multiselect-dropdown span.dropdown-btn")
                                    if multiselect_dropdown.count() > 0:
                                        multiselect_dropdown.scroll_into_view_if_needed()
                                        multiselect_dropdown.click()
                                        
                                        multiselect_element = page.locator(f"li:has(input[type='checkbox'][aria-label='{str(bill_id)}'])")
                                        if multiselect_element.count() > 0:
                                            multiselect_element.scroll_into_view_if_needed()
                                            multiselect_element.click()
                                            
                                            page.wait_for_load_state("networkidle")
                                            page.wait_for_selector("span.selected-item", state="attached")
                                            page.wait_for_load_state("networkidle")
                                            selection_successful = True
                                            _log(session_id, f"✅ Method 1 - Selected consumer ID: {bill_id}")
                                else:
                                    selection_successful = True
                                    _log(session_id, f"✅ Consumer ID already selected: {bill_id}")
                        except Exception as e:
                            _log(session_id, f"⚠️ Method 1 selection failed: {str(e)[:100]}")
                        
                        # Method 2: Try direct select element
                        if not selection_successful:
                            try:
                                _log(session_id, "🔍 Method 2 - Trying direct select element...")
                                select_elements = page.locator("select").all()
                                for select_elem in select_elements:
                                    options = select_elem.locator("option").all()
                                    for option in options:
                                        option_value = option.get_attribute("value") or option.text_content()
                                        if option_value and str(bill_id) in str(option_value):
                                            select_elem.select_option(option.get_attribute("value") or option_value)
                                            _log(session_id, f"✅ Method 2 - Selected from select: {bill_id}")
                                            selection_successful = True
                                            break
                                    if selection_successful:
                                        break
                            except Exception as e:
                                _log(session_id, f"⚠️ Method 2 selection failed: {str(e)[:100]}")
                        
                        # Method 3: Try to find and click any element containing the bill_id
                        if not selection_successful:
                            try:
                                _log(session_id, "🔍 Method 3 - Looking for clickable elements with bill ID...")
                                # Look for any clickable element containing the bill ID
                                clickable_selectors = [
                                    f"*:has-text('{bill_id}')",
                                    f"[value*='{bill_id}']",
                                    f"[aria-label*='{bill_id}']"
                                ]
                                
                                for selector in clickable_selectors:
                                    try:
                                        elements = page.locator(selector).all()
                                        if elements:
                                            elements[0].click()
                                            _log(session_id, f"✅ Method 3 - Clicked element with selector: {selector}")
                                            selection_successful = True
                                            break
                                    except:
                                        continue
                            except Exception as e:
                                _log(session_id, f"⚠️ Method 3 selection failed: {str(e)[:100]}")
                        
                        # If selection still failed, continue anyway if we have a target CA
                        if not selection_successful:
                            if target_ca_number and str(bill_id) == str(target_ca_number):
                                _log(session_id, f"⚠️ Could not select {bill_id} from dropdown, but continuing since it's the target CA")
                                selection_successful = True
                            else:
                                _log(session_id, f"❌ Could not select consumer ID: {bill_id}. Skipping.")
                        # Get available bill dates - try multiple methods
                        bill_date_options = []
                        
                        # Method 1: Try original selector
                        try:
                            bill_date_options = page.query_selector_all('select[name="billDates"] option')
                            if bill_date_options:
                                _log(session_id, f"✅ Method 1 - Found {len(bill_date_options)} bill date options")
                        except Exception as e:
                            _log(session_id, f"⚠️ Method 1 bill dates failed: {str(e)[:100]}")
                        
                        # Method 2: Try alternative selectors
                        if not bill_date_options:
                            alternative_selectors = [
                                'select option',
                                '[name*="bill"] option',
                                '[name*="date"] option',
                                '.bill-date option',
                                '.date-select option'
                            ]
                            
                            for selector in alternative_selectors:
                                try:
                                    options = page.query_selector_all(selector)
                                    if options and len(options) > 1:  # More than just a placeholder
                                        bill_date_options = options
                                        _log(session_id, f"✅ Method 2 - Found bill dates with selector: {selector}")
                                        break
                                except Exception as e:
                                    _log(session_id, f"⚠️ Selector {selector} failed: {str(e)[:50]}")
                                    continue
                        
                        # Method 3: Look for any download buttons or links
                        if not bill_date_options:
                            try:
                                _log(session_id, "🔍 Method 3 - Looking for download buttons/links...")
                                download_elements = page.locator("button:has-text('download'), a:has-text('download'), .download, [class*='download']").all()
                                if download_elements:
                                    _log(session_id, f"✅ Method 3 - Found {len(download_elements)} download elements")
                                    # Create fake options for the download elements
                                    bill_date_options = download_elements
                            except Exception as e:
                                _log(session_id, f"⚠️ Method 3 failed: {str(e)[:100]}")
                        
                        if not bill_date_options:
                            _log(session_id, f"⚠️ No bills available for consumer ID: {bill_id}")
                            continue
                        
                        # Filter bills based on parameters
                        if bill_month:
                            # Search for specific month
                            _log(session_id, f"🔍 Looking for bill month: {bill_month}")
                            bills_to_download = []
                            for option in bill_date_options:
                                bill_text = option.text_content().strip()
                                if bill_month.upper() in bill_text.upper():
                                    bills_to_download.append(option)
                                    _log(session_id, f"✅ Found matching bill: {bill_text}")
                            
                            if not bills_to_download:
                                _log(session_id, f"⚠️ No bill found for month '{bill_month}' for consumer ID: {bill_id}")
                                available_bills = [opt.text_content().strip() for opt in bill_date_options]
                                _log(session_id, f"📋 Available bills: {available_bills}")
                                continue
                        elif fetch_history:
                            bills_to_download = bill_date_options
                        else:
                            bills_to_download = [bill_date_options[0]]
                        
                        # Download each bill
                        for option in bills_to_download:
                            try:
                                # Get bill text/identifier
                                if hasattr(option, 'text_content'):
                                    bill_text = option.text_content().strip()
                                elif hasattr(option, 'get_attribute'):
                                    bill_text = option.get_attribute("value") or "Unknown"
                                else:
                                    bill_text = str(option)
                                
                                if not bill_text or bill_text == "Unknown":
                                    bill_text = f"Bill_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
                                
                                _log(session_id, f"📥 Downloading bill for: {bill_text}")
                                
                                # Try to select bill date if it's a select option
                                if hasattr(option, 'get_attribute'):
                                    try:
                                        select_element = page.locator('select[name="billDates"]')
                                        if select_element.count() > 0:
                                            option_value = option.get_attribute("value")
                                            if option_value:
                                                select_element.select_option(option_value)
                                                page.wait_for_load_state("networkidle")
                                                _log(session_id, f"✅ Selected bill date: {option_value}")
                                    except Exception as e:
                                        _log(session_id, f"⚠️ Could not select bill date: {str(e)[:100]}")
                                
                                # Try multiple methods to download the bill
                                download_successful = False
                                file_content = None
                                
                                # Method 1: Try original download button
                                try:
                                    download_button = page.locator(".download-bill-history button")
                                    if download_button.count() > 0:
                                        with page.expect_download(timeout=15000) as download_info:
                                            download_button.click()
                                        
                                        download = download_info.value
                                        temp_path = download.path()
                                        with open(temp_path, 'rb') as f:
                                            file_content = f.read()
                                        download_successful = True
                                        _log(session_id, f"✅ Method 1 - Downloaded via button")
                                except Exception as e:
                                    _log(session_id, f"⚠️ Method 1 download failed: {str(e)[:100]}")
                                
                                # Method 2: Try alternative download selectors
                                if not download_successful:
                                    download_selectors = [
                                        "button:has-text('download')",
                                        "a:has-text('download')",
                                        ".download-btn",
                                        ".btn-download",
                                        "[class*='download']",
                                        "button[onclick*='download']",
                                        "a[href*='download']"
                                    ]
                                    
                                    for selector in download_selectors:
                                        try:
                                            download_element = page.locator(selector)
                                            if download_element.count() > 0:
                                                with page.expect_download(timeout=15000) as download_info:
                                                    download_element.first.click()
                                                
                                                download = download_info.value
                                                temp_path = download.path()
                                                with open(temp_path, 'rb') as f:
                                                    file_content = f.read()
                                                download_successful = True
                                                _log(session_id, f"✅ Method 2 - Downloaded via {selector}")
                                                break
                                        except Exception as e:
                                            _log(session_id, f"⚠️ Selector {selector} failed: {str(e)[:50]}")
                                            continue
                                
                                # Method 3: Try clicking the option itself if it's clickable
                                if not download_successful and hasattr(option, 'click'):
                                    try:
                                        with page.expect_download(timeout=15000) as download_info:
                                            option.click()
                                        
                                        download = download_info.value
                                        temp_path = download.path()
                                        with open(temp_path, 'rb') as f:
                                            file_content = f.read()
                                        download_successful = True
                                        _log(session_id, f"✅ Method 3 - Downloaded by clicking option")
                                    except Exception as e:
                                        _log(session_id, f"⚠️ Method 3 failed: {str(e)[:100]}")
                                
                                # Save file if download was successful
                                if download_successful and file_content:
                                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                                    filename = f"{bill_id}_{bill_text.replace('/', '_')}_{timestamp}.pdf"
                                    downloads[session_id]["files"][filename] = file_content
                                    _log(session_id, f"✅ Saved bill: {filename} ({len(file_content)} bytes)")
                                else:
                                    _log(session_id, f"❌ Could not download bill for: {bill_text}")
                                
                                page.wait_for_load_state("networkidle")
                                
                            except Exception as e:
                                _log(session_id, f"❌ Error downloading bill {bill_text}: {str(e)[:150]}")
                                continue
                            
                            page.wait_for_load_state("networkidle")
                    
                    browser.close()
                    _log(session_id, f"✅ Account {account_idx + 1} ({username}): Bills downloaded successfully!")
                    
                except Exception as e:
                    _log(session_id, f"❌ Account {account_idx + 1}: Error - {str(e)}")
                    _log(session_id, f"🔍 Traceback: {traceback.format_exc()[:300]}")
                    try:
                        browser.close()
                    except:
                        pass
                    continue
                
                # Update progress
                downloads[session_id]["completed"] += 1
                downloads[session_id]["progress"] = int(downloads[session_id]["completed"] * 100 / downloads[session_id]["total"])
        
        downloads[session_id]["status"] = "completed"
        _log(session_id, f"🎉 All accounts processed! Total files: {len(downloads[session_id]['files'])}")
        
    except Exception as e:
        downloads[session_id]["status"] = "error"
        _log(session_id, f"❌ Fatal error: {str(e)}")
        _log(session_id, f"🔍 Traceback: {traceback.format_exc()[:500]}")


# -------------------- CESC Mysore (Karnataka) --------------------
def download_cescmysore(credentials, session_id, fetch_history=False, bill_month=None, capsolver_api_key=None):
    """Download bills from CESC Mysore portal using standalone script"""
    try:
        import subprocess
        import tempfile
        import os
        
        # Initialize session
        total_accounts = len(credentials)
        downloads[session_id] = {
            "status": "downloading",
            "progress": 0,
            "completed": 0,
            "total": total_accounts,
            "logs": [],
            "files": {}
        }
        
        _log(session_id, f"🚀 Starting CESC Mysore download for {total_accounts} account(s)")
        
        # Create temporary directory for downloads
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create a temporary script file with the credentials
            script_content = f'''
import sys
sys.path.append('.')
from cescmysore_downloader import CESCMysoreBillDownloader

# Configuration
ACCOUNTS = {credentials}
CAPSOLVER_API_KEY = "{capsolver_api_key or 'CAP-ADCA94D1B80ACF6A5A0E9E57B4E90158'}"
DOWNLOAD_FOLDER = r"{temp_dir}"
FETCH_HISTORY = {fetch_history}
BILL_MONTH = "{bill_month or ''}"
HEADLESS = True

# Process each account
for idx, cred in enumerate(ACCOUNTS, 1):
    username = cred['username']
    password = cred['password'] 
    ca_number = cred.get('ca_number')
    
    downloader = CESCMysoreBillDownloader(
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
            bill_month=BILL_MONTH if BILL_MONTH else None
        )
        print(f"SUCCESS: Account {{idx}} ({{username}}) completed")
    except Exception as e:
        print(f"ERROR: Account {{idx}} ({{username}}) failed: {{str(e)}}")
'''
            
            # Write and execute the script
            script_path = os.path.join(temp_dir, "run_cescmysore.py")
            with open(script_path, 'w') as f:
                f.write(script_content)
            
            # Run the script
            result = subprocess.run([sys.executable, script_path], 
                                  capture_output=True, text=True, timeout=1800)
            
            # Process results
            if result.stdout:
                for line in result.stdout.split('\n'):
                    if line.strip():
                        _log(session_id, line.strip())
            
            if result.stderr:
                for line in result.stderr.split('\n'):
                    if line.strip():
                        _log(session_id, f"⚠️ {line.strip()}")
            
            # Collect downloaded files
            for filename in os.listdir(temp_dir):
                if filename.endswith('.pdf'):
                    filepath = os.path.join(temp_dir, filename)
                    with open(filepath, 'rb') as f:
                        downloads[session_id]["files"][filename] = f.read()
                    _log(session_id, f"✅ Collected: {filename}")
        
        downloads[session_id]["completed"] = total_accounts
        downloads[session_id]["progress"] = 100
        downloads[session_id]["status"] = "completed"
        _log(session_id, f"🎉 CESC Mysore download completed! Files: {len(downloads[session_id]['files'])}")
        
    except Exception as e:
        downloads[session_id]["status"] = "error"
        _log(session_id, f"❌ CESC Mysore error: {str(e)}")


# -------------------- GESCOM (Karnataka) --------------------
def download_gescom(credentials, session_id, fetch_history=False, bill_month=None, capsolver_api_key=None):
    """Download bills from GESCOM portal using standalone script"""
    try:
        import subprocess
        import tempfile
        import os
        
        # Initialize session
        total_accounts = len(credentials)
        downloads[session_id] = {
            "status": "downloading",
            "progress": 0,
            "completed": 0,
            "total": total_accounts,
            "logs": [],
            "files": {}
        }
        
        _log(session_id, f"🚀 Starting GESCOM download for {total_accounts} account(s)")
        
        # Create temporary directory for downloads
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create a temporary script file with the credentials
            script_content = f'''
import sys
sys.path.append('.')
from gescom_downloader import GESCOMBillDownloader

# Configuration
ACCOUNTS = {credentials}
CAPSOLVER_API_KEY = "{capsolver_api_key or 'CAP-ADCA94D1B80ACF6A5A0E9E57B4E90158'}"
DOWNLOAD_FOLDER = r"{temp_dir}"
FETCH_HISTORY = {fetch_history}
BILL_MONTH = "{bill_month or ''}"
HEADLESS = True

# Process each account
for idx, cred in enumerate(ACCOUNTS, 1):
    username = cred['username']
    password = cred['password'] 
    ca_number = cred.get('ca_number')
    
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
            bill_month=BILL_MONTH if BILL_MONTH else None
        )
        print(f"SUCCESS: Account {{idx}} ({{username}}) completed")
    except Exception as e:
        print(f"ERROR: Account {{idx}} ({{username}}) failed: {{str(e)}}")
'''
            
            # Write and execute the script
            script_path = os.path.join(temp_dir, "run_gescom.py")
            with open(script_path, 'w') as f:
                f.write(script_content)
            
            # Run the script
            result = subprocess.run([sys.executable, script_path], 
                                  capture_output=True, text=True, timeout=1800)
            
            # Process results
            if result.stdout:
                for line in result.stdout.split('\n'):
                    if line.strip():
                        _log(session_id, line.strip())
            
            if result.stderr:
                for line in result.stderr.split('\n'):
                    if line.strip():
                        _log(session_id, f"⚠️ {line.strip()}")
            
            # Collect downloaded files
            for filename in os.listdir(temp_dir):
                if filename.endswith('.pdf'):
                    filepath = os.path.join(temp_dir, filename)
                    with open(filepath, 'rb') as f:
                        downloads[session_id]["files"][filename] = f.read()
                    _log(session_id, f"✅ Collected: {filename}")
        
        downloads[session_id]["completed"] = total_accounts
        downloads[session_id]["progress"] = 100
        downloads[session_id]["status"] = "completed"
        _log(session_id, f"🎉 GESCOM download completed! Files: {len(downloads[session_id]['files'])}")
        
    except Exception as e:
        downloads[session_id]["status"] = "error"
        _log(session_id, f"❌ GESCOM error: {str(e)}")


# -------------------- HESCOM (Karnataka) --------------------
def download_hescom(credentials, session_id, fetch_history=False, bill_month=None, capsolver_api_key=None):
    """Download bills from HESCOM portal using standalone script"""
    try:
        import subprocess
        import tempfile
        import os
        
        # Initialize session
        total_accounts = len(credentials)
        downloads[session_id] = {
            "status": "downloading",
            "progress": 0,
            "completed": 0,
            "total": total_accounts,
            "logs": [],
            "files": {}
        }
        
        _log(session_id, f"🚀 Starting HESCOM download for {total_accounts} account(s)")
        
        # Create temporary directory for downloads
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create a temporary script file with the credentials
            script_content = f'''
import sys
sys.path.append('.')
from hescom_downloader import HESCOMBillDownloader

# Configuration
ACCOUNTS = {credentials}
CAPSOLVER_API_KEY = "{capsolver_api_key or 'CAP-ADCA94D1B80ACF6A5A0E9E57B4E90158'}"
DOWNLOAD_FOLDER = r"{temp_dir}"
FETCH_HISTORY = {fetch_history}
BILL_MONTH = "{bill_month or ''}"
HEADLESS = True

# Process each account
for idx, cred in enumerate(ACCOUNTS, 1):
    username = cred['username']
    password = cred['password'] 
    ca_number = cred.get('ca_number')
    
    downloader = HESCOMBillDownloader(
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
            bill_month=BILL_MONTH if BILL_MONTH else None
        )
        print(f"SUCCESS: Account {{idx}} ({{username}}) completed")
    except Exception as e:
        print(f"ERROR: Account {{idx}} ({{username}}) failed: {{str(e)}}")
'''
            
            # Write and execute the script
            script_path = os.path.join(temp_dir, "run_hescom.py")
            with open(script_path, 'w') as f:
                f.write(script_content)
            
            # Run the script
            result = subprocess.run([sys.executable, script_path], 
                                  capture_output=True, text=True, timeout=1800)
            
            # Process results
            if result.stdout:
                for line in result.stdout.split('\n'):
                    if line.strip():
                        _log(session_id, line.strip())
            
            if result.stderr:
                for line in result.stderr.split('\n'):
                    if line.strip():
                        _log(session_id, f"⚠️ {line.strip()}")
            
            # Collect downloaded files
            for filename in os.listdir(temp_dir):
                if filename.endswith('.pdf'):
                    filepath = os.path.join(temp_dir, filename)
                    with open(filepath, 'rb') as f:
                        downloads[session_id]["files"][filename] = f.read()
                    _log(session_id, f"✅ Collected: {filename}")
        
        downloads[session_id]["completed"] = total_accounts
        downloads[session_id]["progress"] = 100
        downloads[session_id]["status"] = "completed"
        _log(session_id, f"🎉 HESCOM download completed! Files: {len(downloads[session_id]['files'])}")
        
    except Exception as e:
        downloads[session_id]["status"] = "error"
        _log(session_id, f"❌ HESCOM error: {str(e)}")


# -------------------- MESCOM (Karnataka) --------------------
def download_mescom(credentials, session_id, fetch_history=False, bill_month=None):
    """Download bills from MESCOM portal using standalone script (no captcha required)"""
    try:
        import subprocess
        import tempfile
        import os
        
        # Initialize session
        total_accounts = len(credentials)
        downloads[session_id] = {
            "status": "downloading",
            "progress": 0,
            "completed": 0,
            "total": total_accounts,
            "logs": [],
            "files": {}
        }
        
        _log(session_id, f"🚀 Starting MESCOM download for {total_accounts} account(s)")
        
        # Create temporary directory for downloads
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create a temporary script file with the credentials
            script_content = f'''
import sys
sys.path.append('.')
from mescom_downloader import MESCOMBillDownloader

# Configuration
ACCOUNTS = {credentials}
DOWNLOAD_FOLDER = r"{temp_dir}"
FETCH_HISTORY = {fetch_history}
BILL_MONTH = "{bill_month or ''}"
HEADLESS = True

# Process each account
for idx, cred in enumerate(ACCOUNTS, 1):
    username = cred['username']
    password = cred['password'] 
    ca_number = cred.get('ca_number')
    
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
            bill_month=BILL_MONTH if BILL_MONTH else None
        )
        print(f"SUCCESS: Account {{idx}} ({{username}}) completed")
    except Exception as e:
        print(f"ERROR: Account {{idx}} ({{username}}) failed: {{str(e)}}")
'''
            
            # Write and execute the script
            script_path = os.path.join(temp_dir, "run_mescom.py")
            with open(script_path, 'w') as f:
                f.write(script_content)
            
            # Run the script
            result = subprocess.run([sys.executable, script_path], 
                                  capture_output=True, text=True, timeout=1800)
            
            # Process results
            if result.stdout:
                for line in result.stdout.split('\n'):
                    if line.strip():
                        _log(session_id, line.strip())
            
            if result.stderr:
                for line in result.stderr.split('\n'):
                    if line.strip():
                        _log(session_id, f"⚠️ {line.strip()}")
            
            # Collect downloaded files
            for filename in os.listdir(temp_dir):
                if filename.endswith('.pdf'):
                    filepath = os.path.join(temp_dir, filename)
                    with open(filepath, 'rb') as f:
                        downloads[session_id]["files"][filename] = f.read()
                    _log(session_id, f"✅ Collected: {filename}")
        
        downloads[session_id]["completed"] = total_accounts
        downloads[session_id]["progress"] = 100
        downloads[session_id]["status"] = "completed"
        _log(session_id, f"🎉 MESCOM download completed! Files: {len(downloads[session_id]['files'])}")
        
    except Exception as e:
        downloads[session_id]["status"] = "error"
        _log(session_id, f"❌ MESCOM error: {str(e)}")


# -------------------- New Delhi Municipal Council (NDMC) --------------------
def download_ndmc(ca_numbers, months, session_id):
    """
    Download bills from New Delhi Municipal Council (NDMC)
    URL: https://ewbilling.ndmc.gov.in/
    """
    try:
        from playwright.sync_api import sync_playwright
    except Exception:
        downloads[session_id] = {
            "status": "error",
            "logs": ["Playwright not installed. Run: pip install playwright && playwright install chromium"]
        }
        return

    downloads[session_id] = {
        "status": "downloading",
        "progress": 0,
        "completed": 0,
        "total": len(ca_numbers) * len(months),
        "logs": [],
        "files": {}
    }

    def log(m): _log(session_id, m)

    for ca_number in ca_numbers:
        ca_number = str(ca_number).strip()
        if not ca_number:
            continue

        for month_str in months:
            try:
                with sync_playwright() as p:
                    browser = p.chromium.launch(
                        headless=True,
                        args=["--no-sandbox", "--disable-dev-shm-usage"]
                    )
                    context = browser.new_context(
                        accept_downloads=True,
                        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
                    )
                    page = context.new_page()

                    log(f"Loading NDMC page for CA: {ca_number}")
                    page.goto("https://ewbilling.ndmc.gov.in/", wait_until="domcontentloaded", timeout=60000)
                    page.wait_for_timeout(3000)

                    # Enter CA number
                    try:
                        log(f"Entering CA number: {ca_number}")
                        page.wait_for_selector('#consumerNo', timeout=10000)
                        page.fill('#consumerNo', ca_number)
                        log(f"CA number entered")
                        page.wait_for_timeout(1000)
                    except Exception as e:
                        log(f"✗ {ca_number}: Failed to enter CA number - {str(e)[:100]}")
                        browser.close()
                        continue

                    # Click terms checkbox
                    try:
                        log(f"Clicking terms checkbox")
                        page.wait_for_selector('#tnc', timeout=10000)
                        page.click('#tnc')
                        log(f"Checkbox clicked")
                        page.wait_for_timeout(1000)
                    except Exception as e:
                        log(f"✗ {ca_number}: Failed to click checkbox - {str(e)[:100]}")
                        browser.close()
                        continue

                    # Click Make Payment button
                    try:
                        log(f"Clicking Make Payment button")
                        page.wait_for_selector('#mPay', timeout=10000)
                        page.click('#mPay')
                        log(f"Make Payment clicked, waiting for page load...")
                        page.wait_for_timeout(5000)
                        
                        # Wait for navigation
                        try:
                            page.wait_for_load_state("networkidle", timeout=15000)
                        except:
                            page.wait_for_timeout(3000)
                    except Exception as e:
                        log(f"✗ {ca_number}: Failed to click Make Payment - {str(e)[:100]}")
                        browser.close()
                        continue

                    # Click View Bill button
                    try:
                        log(f"Clicking View Bill button")
                        view_bill_selector = 'body > section:nth-child(5) > div:nth-child(1) > div:nth-child(2) > div:nth-child(2) > div:nth-child(1) > div:nth-child(1) > table:nth-child(1) > tbody:nth-child(1) > tr:nth-child(5) > td:nth-child(1) > a:nth-child(2) > label:nth-child(1)'
                        page.wait_for_selector(view_bill_selector, timeout=10000)
                        page.click(view_bill_selector)
                        log(f"View Bill clicked, waiting for bill page...")
                        page.wait_for_timeout(5000)
                    except Exception as e:
                        log(f"✗ {ca_number}: Failed to click View Bill - {str(e)[:100]}")
                        browser.close()
                        continue

                    # Select From Month (Jan)
                    try:
                        log(f"Selecting From Month: Jan")
                        page.wait_for_selector('#fMonth', timeout=10000)
                        page.select_option('#fMonth', 'Jan')
                        log(f"From Month selected")
                        page.wait_for_timeout(1000)
                    except Exception as e:
                        log(f"✗ {ca_number}: Failed to select From Month - {str(e)[:100]}")
                        browser.close()
                        continue

                    # Select To Month (Dec)
                    try:
                        log(f"Selecting To Month: Dec")
                        page.wait_for_selector('#tMonth', timeout=10000)
                        page.select_option('#tMonth', 'Dec')
                        log(f"To Month selected")
                        page.wait_for_timeout(1000)
                    except Exception as e:
                        log(f"✗ {ca_number}: Failed to select To Month - {str(e)[:100]}")
                        browser.close()
                        continue

                    # Click Search button
                    try:
                        log(f"Clicking Search button")
                        page.wait_for_selector('.fa.search-btn', timeout=10000)
                        page.click('.fa.search-btn')
                        log(f"Search clicked, waiting for results...")
                        page.wait_for_timeout(5000)
                    except Exception as e:
                        log(f"✗ {ca_number}: Failed to click Search - {str(e)[:100]}")
                        browser.close()
                        continue

                    # Parse month string (e.g., "JAN-2025" or "012025")
                    try:
                        if '-' in month_str:
                            target_month = month_str.upper()
                        else:
                            # Convert "012025" to "JAN-2025"
                            month_map = {
                                '01': 'JAN', '02': 'FEB', '03': 'MAR', '04': 'APR',
                                '05': 'MAY', '06': 'JUN', '07': 'JUL', '08': 'AUG',
                                '09': 'SEP', '10': 'OCT', '11': 'NOV', '12': 'DEC'
                            }
                            month_num = month_str[:2]
                            year = month_str[2:]
                            target_month = f"{month_map.get(month_num, 'JAN')}-{year}"
                        
                        log(f"Looking for month: {target_month}")
                    except Exception as e:
                        log(f"✗ Failed to parse month: {str(e)[:100]}")
                        target_month = month_str

                    # Find and click Download Bill button for the target month
                    try:
                        # Wait for table to load
                        page.wait_for_timeout(3000)
                        
                        # Find all rows with dates
                        rows = page.query_selector_all('table tbody tr')
                        log(f"Found {len(rows)} rows in bill table")
                        
                        bill_downloaded = False
                        for row in rows:
                            try:
                                date_cell = row.query_selector('td:first-child')
                                if date_cell:
                                    date_text = date_cell.inner_text().strip().upper()
                                    log(f"Checking row with date: {date_text}")
                                    
                                    if target_month in date_text:
                                        log(f"✓ Found matching month: {date_text}")
                                        
                                        # Find Download Bill button in this row
                                        download_btn = row.query_selector('button:has-text("Download Bill"), a:has-text("Download Bill")')
                                        if download_btn:
                                            # Set up download handler
                                            with page.expect_download(timeout=30000) as download_info:
                                                download_btn.click()
                                                log(f"Download Bill clicked for {target_month}")
                                            
                                            download = download_info.value
                                            pdf_path = download.path()
                                            
                                            with open(pdf_path, 'rb') as f:
                                                pdf_data = f.read()
                                            
                                            filename = f"NDMC_{ca_number}_{target_month}.pdf"
                                            # Rename with extracted date
                                            filename = rename_pdf_with_date(filename, pdf_data, "NDMC")
                                            downloads[session_id]["files"][filename] = pdf_data
                                            log(f"✓ {ca_number} ({target_month}): Downloaded ({len(pdf_data)} bytes) - {filename}")
                                            bill_downloaded = True
                                            break
                                        else:
                                            log(f"✗ Download button not found in row")
                            except Exception as row_err:
                                continue
                        
                        if not bill_downloaded:
                            log(f"✗ {ca_number} ({target_month}): Bill not found in results")
                        
                    except Exception as e:
                        log(f"✗ {ca_number} ({target_month}): Error downloading - {str(e)[:150]}")

                    browser.close()

            except Exception as e:
                log(f"✗ {ca_number} ({month_str}): Error - {str(e)[:160]}")

            downloads[session_id]["completed"] += 1
            downloads[session_id]["progress"] = int(downloads[session_id]["completed"] * 100 / downloads[session_id]["total"])

    downloads[session_id]["status"] = "completed"


# -------------------- API --------------------
@app.route('/download', methods=['POST'])
def start_download():
    data = request.json or {}
    board = data.get('board')
    ca_numbers = data.get('ca_numbers', [])
    months = data.get('months', ['092025'])

    # Handle month range functionality
    start_month = data.get('start_month', '')
    end_month = data.get('end_month', '')
    
    # If month range is provided, generate the month list
    if start_month and end_month:
        try:
            if board in ["mp_poorva_kshetra", "uppcl_discom", "apcpdcl"]:
                # These boards use YYYY-MM format
                months = generate_month_range(start_month, end_month, "YYYY-MM")
            else:
                # Other boards use MMYYYY format
                months = generate_month_range(start_month, end_month, "MMYYYY")
        except ValueError as e:
            return jsonify({"error": f"Invalid month range: {str(e)}"}), 400

    msedcl_mode = (data.get('msedcl_mode') or '').upper()
    bill_month = data.get('bill_month', '')  # For backward compatibility
    bill_months = data.get('bill_months', [])  # New: support for multiple months
    if not bill_months and bill_month:
        bill_months = [bill_month]  # Convert single month to list
    
    # If month range was generated, use it for bill_months as well
    if start_month and end_month and board in ["mp_poorva_kshetra", "uppcl_discom", "apcpdcl"]:
        bill_months = months
    
    cookie_header = data.get('cookie', '')
    bu_map = data.get('bu_map', {})

    if board not in ["msedcl", "chandigarh", "goa_discom", "upcl_discom", "uppcl_discom", "mp_poorva_kshetra", "mp_madhya_kshetra", "mp_paschim_kshetra", "kerala_kseb", "tgspdcl", "dakshin_gujarat", "apepdcl", "apcpdcl", "apspdcl", "ndmc", "bescom", "cescmysore", "gescom", "hescom", "mescom"] and not ca_numbers:
        return jsonify({"error": "CA numbers required"}), 400

    session_id = str(uuid.uuid4())
    
    # Initialize session immediately to prevent 404 errors
    downloads[session_id] = {
        "status": "initializing",
        "progress": 0,
        "completed": 0,
        "total": 0,
        "logs": ["Starting download..."],
        "files": {}
    }

    if board == "chandigarh":
        if not months:
            months = ['092025', '102025', '112025', '122025', '012026', '022026']  # Sep 2025 to Feb 2026
        threading.Thread(target=download_chandigarh, args=(ca_numbers, months, session_id)).start()
    elif board == "bses":
        threading.Thread(target=download_bses, args=(ca_numbers, session_id)).start()
    elif board == "jharkhand":
        threading.Thread(target=download_jharkhand, args=(ca_numbers, months, session_id)).start()
    elif board == "north_bihar":
        threading.Thread(target=download_north_bihar, args=(ca_numbers, session_id)).start()
    elif board == "dakshin_haryana":
        threading.Thread(target=download_dakshin_haryana, args=(ca_numbers, session_id)).start()
    elif board == "uttar_haryana":
        threading.Thread(target=download_uttar_haryana, args=(ca_numbers, session_id)).start()
    elif board == "tgspdcl":
        threading.Thread(target=download_tgspdcl, args=(ca_numbers, session_id)).start()
    elif board == "goa_discom":
        login_id = data.get('login_id', '')
        password = data.get('password', '')
        bill_numbers = data.get('bill_numbers', [])
        if not login_id or not password or not bill_numbers:
            return jsonify({"error": "Login ID, password, and bill numbers required"}), 400
        threading.Thread(target=download_goa_discom, args=(login_id, password, bill_numbers, session_id)).start()
    elif board == "mp_poorva_kshetra":
        bill_months = data.get('bill_months', ['2025-09', '2025-10', '2025-11', '2025-12', '2026-01', '2026-02'])  # Sep 2025 to Feb 2026
        if not ca_numbers or not bill_months:
            return jsonify({"error": "CA numbers and bill months required"}), 400
        # For backward compatibility, support single bill_month
        single_bill_month = data.get('bill_month', '')
        if single_bill_month and not bill_months:
            bill_months = [single_bill_month]
        threading.Thread(target=download_mp_poorva_kshetra, args=(ca_numbers, bill_months, session_id)).start()
    elif board == "upcl_discom":
        account_numbers = data.get('account_numbers', [])
        if not account_numbers:
            return jsonify({"error": "Account numbers required"}), 400
        threading.Thread(target=download_upcl_discom, args=(account_numbers, session_id)).start()
    elif board == "uppcl_discom":
        uppcl_board = data.get('uppcl_board', 'mvvnl')
        bill_months = data.get('bill_months', ['2025-09', '2025-10', '2025-11', '2025-12', '2026-01', '2026-02'])  # Sep 2025 to Feb 2026
        if not ca_numbers or not bill_months:
            return jsonify({"error": "CA numbers and bill months required"}), 400
        # For backward compatibility, support single bill_month
        single_bill_month = data.get('bill_month', '')
        if single_bill_month and not bill_months:
            bill_months = [single_bill_month]
        threading.Thread(target=download_uppcl_discom, args=(uppcl_board, ca_numbers, bill_months, session_id)).start()
    elif board == "dakshin_gujarat":
        if not ca_numbers:
            return jsonify({"error": "CA numbers required"}), 400
        threading.Thread(target=download_dakshin_gujarat, args=(ca_numbers, session_id)).start()
    elif board == "mp_madhya_kshetra":
        if not ca_numbers:
            return jsonify({"error": "CA numbers required"}), 400
        threading.Thread(target=download_mp_madhya_kshetra, args=(ca_numbers, session_id)).start()
    elif board == "mp_paschim_kshetra":
        if not ca_numbers:
            return jsonify({"error": "CA numbers required"}), 400
        threading.Thread(target=download_mp_paschim_kshetra, args=(ca_numbers, session_id)).start()
    elif board == "kerala_kseb":
        ca_mobile_pairs = data.get('ca_mobile_pairs', [])
        if not ca_mobile_pairs:
            return jsonify({"error": "CA numbers and mobile numbers required"}), 400
        threading.Thread(target=download_kerala_kseb, args=(ca_mobile_pairs, session_id)).start()
    elif board == "apepdcl":
        if not ca_numbers:
            return jsonify({"error": "CA numbers required"}), 400
        threading.Thread(target=download_apepdcl, args=(ca_numbers, session_id)).start()
    elif board == "apcpdcl":
        if not ca_numbers:
            return jsonify({"error": "CA numbers required"}), 400
        bill_months = data.get('bill_months', ['2025-09', '2025-10', '2025-11', '2025-12', '2026-01', '2026-02'])  # Sep 2025 to Feb 2026
        if not bill_months:
            bill_months = [datetime.now().strftime("%Y-%m")]  # Default to current month
        # For backward compatibility, support single bill_month
        single_bill_month = data.get('bill_month', '')
        if single_bill_month and not bill_months:
            bill_months = [single_bill_month]
        threading.Thread(target=download_apcpdcl, args=(ca_numbers, session_id, bill_months)).start()
    elif board == "apspdcl":
        if not ca_numbers:
            return jsonify({"error": "CA numbers required"}), 400
        threading.Thread(target=download_apspdcl, args=(ca_numbers, session_id)).start()
    elif board == "ndmc":
        if not ca_numbers:
            return jsonify({"error": "CA numbers required"}), 400
        if not months:
            months = ['092025', '102025', '112025', '122025', '012026', '022026']  # Sep 2025 to Feb 2026
        threading.Thread(target=download_ndmc, args=(ca_numbers, months, session_id)).start()
    elif board == "bescom":
        # Parse BESCOM credentials from ca_numbers field
        credentials = []
        capsolver_api_key = data.get('capsolver_api_key', 'CAP-ADCA94D1B80ACF6A5A0E9E57B4E90158')
        fetch_history = data.get('fetch_history', False)
        bill_month = data.get('bill_month', '')
        
        if not ca_numbers:
            return jsonify({"error": "Credentials required for BESCOM"}), 400
        
        # Parse credentials in format: "username,password" or "username,password,ca_number"
        for line in ca_numbers:
            parts = [p.strip() for p in line.split(',')]
            if len(parts) >= 2:
                cred = {
                    'username': parts[0],
                    'password': parts[1],
                    'ca_number': parts[2] if len(parts) > 2 else None
                }
                credentials.append(cred)
        
        if not credentials:
            return jsonify({"error": "Invalid credential format. Use: username,password or username,password,ca_number"}), 400
        
        threading.Thread(
            target=download_bescom,
            args=(credentials, session_id, fetch_history, bill_month, capsolver_api_key)
        ).start()
    elif board == "cescmysore":
        # Parse CESC Mysore credentials from ca_numbers field
        credentials = []
        capsolver_api_key = data.get('capsolver_api_key', 'CAP-ADCA94D1B80ACF6A5A0E9E57B4E90158')
        fetch_history = data.get('fetch_history', False)
        bill_month = data.get('bill_month', '')
        
        if not ca_numbers:
            return jsonify({"error": "Credentials required for CESC Mysore"}), 400
        
        # Parse credentials in format: "username,password" or "username,password,ca_number"
        for line in ca_numbers:
            parts = [p.strip() for p in line.split(',')]
            if len(parts) >= 2:
                cred = {
                    'username': parts[0],
                    'password': parts[1],
                    'ca_number': parts[2] if len(parts) > 2 else None
                }
                credentials.append(cred)
        
        if not credentials:
            return jsonify({"error": "Invalid credential format. Use: username,password or username,password,ca_number"}), 400
        
        threading.Thread(
            target=download_cescmysore,
            args=(credentials, session_id, fetch_history, bill_month, capsolver_api_key)
        ).start()
    elif board == "gescom":
        # Parse GESCOM credentials from ca_numbers field
        credentials = []
        capsolver_api_key = data.get('capsolver_api_key', 'CAP-ADCA94D1B80ACF6A5A0E9E57B4E90158')
        fetch_history = data.get('fetch_history', False)
        bill_month = data.get('bill_month', '')
        
        if not ca_numbers:
            return jsonify({"error": "Credentials required for GESCOM"}), 400
        
        # Parse credentials in format: "username,password" or "username,password,ca_number"
        for line in ca_numbers:
            parts = [p.strip() for p in line.split(',')]
            if len(parts) >= 2:
                cred = {
                    'username': parts[0],
                    'password': parts[1],
                    'ca_number': parts[2] if len(parts) > 2 else None
                }
                credentials.append(cred)
        
        if not credentials:
            return jsonify({"error": "Invalid credential format. Use: username,password or username,password,ca_number"}), 400
        
        threading.Thread(
            target=download_gescom,
            args=(credentials, session_id, fetch_history, bill_month, capsolver_api_key)
        ).start()
    elif board == "hescom":
        # Parse HESCOM credentials from ca_numbers field
        credentials = []
        capsolver_api_key = data.get('capsolver_api_key', 'CAP-ADCA94D1B80ACF6A5A0E9E57B4E90158')
        fetch_history = data.get('fetch_history', False)
        bill_month = data.get('bill_month', '')
        
        if not ca_numbers:
            return jsonify({"error": "Credentials required for HESCOM"}), 400
        
        # Parse credentials in format: "username,password" or "username,password,ca_number"
        for line in ca_numbers:
            parts = [p.strip() for p in line.split(',')]
            if len(parts) >= 2:
                cred = {
                    'username': parts[0],
                    'password': parts[1],
                    'ca_number': parts[2] if len(parts) > 2 else None
                }
                credentials.append(cred)
        
        if not credentials:
            return jsonify({"error": "Invalid credential format. Use: username,password or username,password,ca_number"}), 400
        
        threading.Thread(
            target=download_hescom,
            args=(credentials, session_id, fetch_history, bill_month, capsolver_api_key)
        ).start()
    elif board == "mescom":
        # Parse MESCOM credentials from ca_numbers field
        credentials = []
        fetch_history = data.get('fetch_history', False)
        bill_month = data.get('bill_month', '')
        
        if not ca_numbers:
            return jsonify({"error": "Credentials required for MESCOM"}), 400
        
        # Parse credentials in format: "username,password" or "username,password,ca_number"
        for line in ca_numbers:
            parts = [p.strip() for p in line.split(',')]
            if len(parts) >= 2:
                cred = {
                    'username': parts[0],
                    'password': parts[1],
                    'ca_number': parts[2] if len(parts) > 2 else None
                }
                credentials.append(cred)
        
        if not credentials:
            return jsonify({"error": "Invalid credential format. Use: username,password or username,password,ca_number"}), 400
        
        threading.Thread(
            target=download_mescom,
            args=(credentials, session_id, fetch_history, bill_month)
        ).start()
    elif board == "msedcl":
        if msedcl_mode == "HT2" and not ca_numbers and isinstance(bu_map, dict) and bu_map:
            ca_numbers = list(bu_map.keys())
        if not ca_numbers:
            return jsonify({"error": "CA numbers required for MSEDCL"}), 400
        threading.Thread(
            target=download_msedcl,
            args=(ca_numbers, session_id, msedcl_mode, bill_months, cookie_header, bu_map)
        ).start()
    else:
        return jsonify({"error": "Invalid board"}), 400

    return jsonify({"session_id": session_id, "status": "started"})


@app.route('/status/<session_id>', methods=['GET'])
def get_status(session_id):
    if session_id not in downloads:
        # Log the missing session for debugging
        print(f"DEBUG: Session {session_id} not found. Available sessions: {list(downloads.keys())}")
        return jsonify({
            "error": "Session not found", 
            "session_id": session_id,
            "available_sessions": len(downloads),
            "message": "The download session may have expired or not been initialized properly."
        }), 404
    
    status = downloads[session_id].copy()
    files = status.get("files", {})
    status["file_count"] = len(files)
    status["total_size"] = sum(len(f) for f in files.values())
    status["file_list"] = [{"name": name, "size": len(data)} for name, data in files.items()]
    status.pop("files", None)
    return jsonify(status)


@app.route('/sessions', methods=['GET'])
def list_sessions():
    """Debug endpoint to list all active sessions"""
    sessions = {}
    for session_id, data in downloads.items():
        sessions[session_id] = {
            "status": data.get("status", "unknown"),
            "progress": data.get("progress", 0),
            "completed": data.get("completed", 0),
            "total": data.get("total", 0),
            "file_count": len(data.get("files", {}))
        }
    return jsonify({
        "total_sessions": len(sessions),
        "sessions": sessions
    })


@app.route('/download/<session_id>', methods=['GET'])
def download_files(session_id):
    if session_id not in downloads:
        return jsonify({"error": "Session not found"}), 404
    files = downloads[session_id].get("files", {})
    if not files:
        return jsonify({"error": "No files to download"}), 404
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
        for name, data in files.items():
            zf.writestr(name, data)
    zip_buffer.seek(0)
    return send_file(zip_buffer, mimetype='application/zip', as_attachment=True,
                     download_name=f"bills_{session_id[:8]}.zip")


@app.route('/download/<session_id>/<filename>', methods=['GET'])
def download_single_file(session_id, filename):
    if session_id not in downloads:
        return jsonify({"error": "Session not found"}), 404
    files = downloads[session_id].get("files", {})
    if filename not in files:
        return jsonify({"error": "File not found"}), 404
    file_data = files[filename]
    file_buffer = io.BytesIO(file_data)
    file_buffer.seek(0)
    return send_file(file_buffer, mimetype='application/pdf', as_attachment=True,
                     download_name=filename)


# -------------------- CESC Mysore Registration --------------------
def register_cesc_mysore_single(ca_number, mobile_number, email, password, session_id):
    """Register a single CA number"""
    def log(m): _log(session_id, m)

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-blink-features=AutomationControlled"]
            )
            context = browser.new_context(
                ignore_https_errors=True,
                user_agent=("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                            "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"),
                viewport={"width": 1366, "height": 900}
            )
            context.add_init_script("Object.defineProperty(navigator,'webdriver',{get:()=>undefined})")

            page = context.new_page()
            
            # Step 1: Navigate to signup page
            log(f"🔄 Navigating to signup page for CA: {ca_number}")
            page.goto("https://www.cescmysore.in/cesc/auth/signup", wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(2000)
            
            # Step 2: Enter CA number
            log(f"📝 Entering CA number: {ca_number}")
            page.fill("#form3Example3", ca_number)
            page.wait_for_timeout(1000)
            
            # Step 3: Click Continue button
            log("🔘 Clicking Continue button")
            page.click('button[name="regisContinueBtn"]')
            page.wait_for_timeout(3000)
            
            # Step 4: Check if CA is already registered
            page_content = page.content()
            if "already registered" in page_content.lower():
                log(f"⚠️ CA number {ca_number} is already registered")
                downloads[session_id]["status"] = "completed"
                downloads[session_id]["progress"] = 100
                downloads[session_id]["completed"] = 1
                browser.close()
                return
            
            # Step 5: Check if navigated to registration form
            current_url = page.url
            if "registrationForms" not in current_url:
                log("⏳ Waiting for navigation to registration form")
                page.wait_for_url("**/registrationForms**", timeout=10000)
            
            log("✅ Navigated to registration form")
            page.wait_for_timeout(2000)
            
            # Step 6: Check and fill mobile number
            mobile_input = page.locator('input[placeholder="+91 -"]')
            existing_mobile = mobile_input.input_value()
            
            if existing_mobile and existing_mobile.strip():
                log(f"📱 Mobile number already present: {existing_mobile}")
            else:
                log(f"📱 Entering mobile number: {mobile_number}")
                mobile_input.fill(mobile_number)
                page.wait_for_timeout(1000)
            
            # Step 7: Enter email
            log(f"📧 Entering email: {email}")
            page.fill('input[placeholder="abc@gmail.com"]', email)
            page.wait_for_timeout(1000)
            
            # Step 8: Confirm email
            log("📧 Confirming email")
            page.fill('input[name="regisFormConfirmEmail"]', email)
            page.wait_for_timeout(1000)
            
            # Step 9: Click Save button
            log("💾 Saving personal details")
            page.click('button[name="regisPersonalDetailsSaveBtn"]')
            page.wait_for_timeout(3000)
            
            # Step 10: Enter CA number (User ID)
            log(f"🆔 Entering User ID (CA number): {ca_number}")
            page.fill('input[placeholder="User ID"]', ca_number)
            page.wait_for_timeout(1000)
            
            # Step 11: Enter password
            log("🔒 Entering password")
            page.fill('input[name="regisFormPassword"]', password)
            page.wait_for_timeout(1000)
            
            # Step 12: Confirm password
            log("🔒 Confirming password")
            page.fill('input[name="regisFormConfirmPassword"]', password)
            page.wait_for_timeout(1000)
            
            # Step 13: Click Save and Continue
            log("💾 Saving username and password")
            page.click('button[name="regisUserNameAndPassSaveBtn"]')
            page.wait_for_timeout(5000)  # Increased wait time for page transition
            
            # Step 14: Enter date of birth - with better error handling
            log("📅 Waiting for date of birth field to appear...")
            try:
                # Wait for the date field to be visible
                page.wait_for_selector('input[placeholder="dd-mm-yyyy"]', state="visible", timeout=15000)
                log("📅 Date field found, entering date: 01-01-2001")
                
                # Try multiple methods to fill the date
                try:
                    # Method 1: Direct fill
                    page.fill('input[placeholder="dd-mm-yyyy"]', "01-01-2001")
                except Exception:
                    log("📅 Trying alternative method to enter date...")
                    # Method 2: Click then type
                    date_input = page.locator('input[placeholder="dd-mm-yyyy"]')
                    date_input.click()
                    page.wait_for_timeout(500)
                    date_input.type("01-01-2001", delay=100)
                
                page.wait_for_timeout(1000)
                log("✅ Date of birth entered successfully")
                
            except PWTimeout:
                log("⚠️ Date field not found, trying alternative selectors...")
                # Try alternative selectors
                alternative_selectors = [
                    'input[type="text"][placeholder*="dd"]',
                    'input[name*="dob"]',
                    'input[name*="birth"]',
                    'input[id*="dob"]',
                    'input[id*="birth"]'
                ]
                
                date_filled = False
                for selector in alternative_selectors:
                    try:
                        if page.locator(selector).count() > 0:
                            log(f"📅 Found date field with selector: {selector}")
                            page.fill(selector, "01-01-2001")
                            page.wait_for_timeout(1000)
                            log("✅ Date entered using alternative selector")
                            date_filled = True
                            break
                    except Exception:
                        continue
                
                if not date_filled:
                    log("❌ Could not find date of birth field - taking screenshot for debugging")
                    page.screenshot(path=f"debug_dob_field_{ca_number}.png")
                    raise Exception("Date of birth field not found")
            
            # Step 15: Select security question
            log("❓ Selecting security question")
            try:
                page.wait_for_selector('select[name="regisFormSecurityQuesDropdown"]', state="visible", timeout=10000)
                
                # Try to select by label first
                try:
                    page.select_option('select[name="regisFormSecurityQuesDropdown"]', label="What is your nick name?")
                except Exception:
                    # If label doesn't work, try by value or index
                    log("❓ Trying alternative method to select security question...")
                    try:
                        # Try selecting by visible text using JavaScript
                        page.evaluate("""
                            const select = document.querySelector('select[name="regisFormSecurityQuesDropdown"]');
                            if (select) {
                                for (let i = 0; i < select.options.length; i++) {
                                    if (select.options[i].text.toLowerCase().includes('nick name')) {
                                        select.selectedIndex = i;
                                        select.dispatchEvent(new Event('change', { bubbles: true }));
                                        break;
                                    }
                                }
                            }
                        """)
                    except Exception:
                        # Last resort: select first non-empty option
                        page.select_option('select[name="regisFormSecurityQuesDropdown"]', index=1)
                
                page.wait_for_timeout(1000)
                log("✅ Security question selected")
            except Exception as e:
                log(f"⚠️ Error selecting security question: {str(e)[:100]}")
                page.screenshot(path=f"debug_security_question_{ca_number}.png")
                raise
            
            # Step 16: Enter security answer
            log("✍️ Entering security answer")
            try:
                page.wait_for_selector('input[name="regisFormAnswer"]', state="visible", timeout=10000)
                page.fill('input[name="regisFormAnswer"]', "sun")
                page.wait_for_timeout(1000)
                log("✅ Security answer entered")
            except Exception as e:
                log(f"⚠️ Error entering security answer: {str(e)[:100]}")
                raise
            
            # Step 17: Check the checkbox
            log("☑️ Accepting terms and conditions")
            try:
                # Wait for checkbox to be available
                page.wait_for_selector('input[name="regisFormCheckbox"]', state="visible", timeout=10000)
                
                # Try to check the checkbox
                try:
                    page.check('input[value="something"][name="regisFormCheckbox"]')
                except Exception:
                    # Alternative: try without value attribute
                    page.check('input[name="regisFormCheckbox"]')
                
                page.wait_for_timeout(1000)
                log("✅ Terms and conditions accepted")
            except Exception as e:
                log(f"⚠️ Error checking checkbox: {str(e)[:100]}")
                # Try clicking it with JavaScript as fallback
                try:
                    page.evaluate("document.querySelector('input[name=\"regisFormCheckbox\"]').click()")
                    log("✅ Checkbox clicked using JavaScript")
                except Exception:
                    log("❌ Could not check the checkbox")
                    page.screenshot(path=f"debug_checkbox_{ca_number}.png")
                    raise
            
            # Step 18: Submit the form
            log("🚀 Submitting registration form")
            try:
                page.wait_for_selector('button[name="regisSecurityInfoSubmit"]', state="visible", timeout=10000)
                page.click('button[name="regisSecurityInfoSubmit"]')
                page.wait_for_timeout(5000)
                log("✅ Form submitted")
            except Exception as e:
                log(f"⚠️ Error submitting form: {str(e)[:100]}")
                page.screenshot(path=f"debug_submit_{ca_number}.png")
                raise
            
            # Step 19: Check for success message
            log("⏳ Waiting for confirmation...")
            page.wait_for_timeout(3000)
            
            final_content = page.content()
            if "successfully" in final_content.lower() and "registered" in final_content.lower():
                log(f"🎉 Registration successful for CA: {ca_number}")
                log("✅ Account details have been sent to registered email")
                downloads[session_id]["status"] = "completed"
            elif "already registered" in final_content.lower():
                log(f"⚠️ CA number {ca_number} is already registered")
                downloads[session_id]["status"] = "completed"
            else:
                log("⚠️ Registration completed but success message not confirmed")
                log("📸 Taking screenshot for verification...")
                page.screenshot(path=f"debug_final_{ca_number}.png")
                log(f"💾 Screenshot saved as: debug_final_{ca_number}.png")
                downloads[session_id]["status"] = "completed"
            
            downloads[session_id]["progress"] = 100
            downloads[session_id]["completed"] = 1
            
            browser.close()
            
    except PWTimeout as e:
        log(f"⏱️ Timeout error: {str(e)[:200]}")
        log("💡 The page took too long to respond. This could be due to:")
        log("   - Slow internet connection")
        log("   - CESC website is slow or down")
        log("   - Page structure has changed")
        try:
            page.screenshot(path=f"debug_timeout_{ca_number}.png")
            log(f"📸 Screenshot saved as: debug_timeout_{ca_number}.png")
        except Exception:
            pass
        downloads[session_id]["status"] = "error"
        downloads[session_id]["progress"] = 0
    except Exception as e:
        log(f"❌ Registration failed: {str(e)[:200]}")
        downloads[session_id]["status"] = "error"
        downloads[session_id]["progress"] = 0


# Generic registration function for CESC-like portals
def register_generic_discom(ca_numbers, mobile_number, email, password, session_id, signup_url, discom_name):
    """Generic registration for CESC Mysore and Gulbarga DISCOM (same flow)"""
    try:
        from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
    except Exception:
        downloads[session_id] = {
            "status": "error",
            "logs": ["Playwright not installed. Run: pip install playwright && playwright install chromium"]
        }
        return

    total = len(ca_numbers)
    downloads[session_id] = {
        "status": "registering",
        "progress": 0,
        "completed": 0,
        "total": total,
        "logs": [],
        "files": {},
        "results": {}
    }

    def log(m): _log(session_id, m)

    log(f"🚀 Starting {discom_name} batch registration for {total} CA number(s)")
    
    for idx, ca_number in enumerate(ca_numbers, 1):
        ca_number = ca_number.strip()
        if not ca_number:
            continue
            
        log(f"\n{'='*60}")
        log(f"📋 Processing CA {idx}/{total}: {ca_number}")
        log(f"{'='*60}")
        
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(
                    headless=True,
                    args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-blink-features=AutomationControlled"]
                )
                context = browser.new_context(
                    ignore_https_errors=True,
                    user_agent=("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                                "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"),
                    viewport={"width": 1366, "height": 900}
                )
                context.add_init_script("Object.defineProperty(navigator,'webdriver',{get:()=>undefined})")

                page = context.new_page()
                
                # Step 1: Navigate to signup page
                log(f"🔄 Navigating to {discom_name} signup page")
                page.goto(signup_url, wait_until="domcontentloaded", timeout=60000)
                page.wait_for_timeout(2000)
                
                # Step 2: Enter CA number
                log(f"📝 Entering CA number: {ca_number}")
                page.fill("#form3Example3", ca_number)
                page.wait_for_timeout(1000)
                
                # Step 3: Click Continue button
                log("🔘 Clicking Continue button")
                page.click('button[name="regisContinueBtn"]')
                page.wait_for_timeout(3000)
                
                # Step 4: Check if CA is already registered
                page_content = page.content()
                if "already registered" in page_content.lower():
                    log(f"⚠️ CA {ca_number} is already registered")
                    downloads[session_id]["results"][ca_number] = "already_registered"
                    browser.close()
                    downloads[session_id]["completed"] += 1
                    downloads[session_id]["progress"] = int(downloads[session_id]["completed"] * 100 / total)
                    continue
                
                # Step 5: Check if navigated to registration form
                current_url = page.url
                if "registrationForms" not in current_url:
                    log("⏳ Waiting for navigation to registration form")
                    page.wait_for_url("**/registrationForms**", timeout=10000)
                
                log("✅ Navigated to registration form")
                page.wait_for_timeout(2000)
                
                # Step 6: Check and fill mobile number
                mobile_input = page.locator('input[placeholder="+91 -"]')
                existing_mobile = mobile_input.input_value()
                
                if existing_mobile and existing_mobile.strip():
                    log(f"📱 Mobile number already present: {existing_mobile}")
                else:
                    log(f"📱 Entering mobile number: {mobile_number}")
                    mobile_input.fill(mobile_number)
                    page.wait_for_timeout(1000)
                
                # Step 7: Enter email
                log(f"📧 Entering email: {email}")
                page.fill('input[placeholder="abc@gmail.com"]', email)
                page.wait_for_timeout(1000)
                
                # Step 8: Confirm email
                log("📧 Confirming email")
                page.fill('input[name="regisFormConfirmEmail"]', email)
                page.wait_for_timeout(1000)
                
                # Step 9: Click Save button
                log("💾 Saving personal details")
                page.click('button[name="regisPersonalDetailsSaveBtn"]')
                page.wait_for_timeout(3000)
                
                # Step 10: Enter CA number (User ID)
                log(f"🆔 Entering User ID (CA number): {ca_number}")
                page.fill('input[placeholder="User ID"]', ca_number)
                page.wait_for_timeout(1000)
                
                # Step 11: Enter password
                log("🔒 Entering password")
                page.fill('input[name="regisFormPassword"]', password)
                page.wait_for_timeout(1000)
                
                # Step 12: Confirm password
                log("🔒 Confirming password")
                page.fill('input[name="regisFormConfirmPassword"]', password)
                page.wait_for_timeout(1000)
                
                # Step 13: Click Save and Continue
                log("💾 Saving username and password")
                page.click('button[name="regisUserNameAndPassSaveBtn"]')
                page.wait_for_timeout(3000)
                
                # Step 14: Enter date of birth
                log("📅 Entering date of birth: 01-01-2001")
                try:
                    date_selectors = [
                        'input[placeholder="dd-mm-yyyy"]',
                        'input[name*="dob" i]',
                        'input[name*="birth" i]',
                        'input[type="date"]',
                        'input[id*="dob" i]',
                        'input[id*="birth" i]'
                    ]
                    
                    date_filled = False
                    for selector in date_selectors:
                        try:
                            if page.locator(selector).count() > 0:
                                page.fill(selector, "01-01-2001", timeout=5000)
                                date_filled = True
                                log(f"✅ Date filled using selector: {selector}")
                                break
                        except:
                            continue
                    
                    if not date_filled:
                        page.click('input[placeholder="dd-mm-yyyy"]', timeout=5000)
                        page.keyboard.type("01012001", delay=100)
                        log("✅ Date entered using keyboard")
                    
                except Exception as e:
                    log(f"⚠️ Date field issue, trying alternative method: {str(e)[:100]}")
                    page.evaluate("""
                        const dateInputs = document.querySelectorAll('input[placeholder*="dd"], input[type="date"], input[name*="dob"], input[name*="birth"]');
                        if (dateInputs.length > 0) {
                            dateInputs[0].value = '01-01-2001';
                            dateInputs[0].dispatchEvent(new Event('input', { bubbles: true }));
                            dateInputs[0].dispatchEvent(new Event('change', { bubbles: true }));
                        }
                    """)
                    log("✅ Date set using JavaScript")
                
                page.wait_for_timeout(1000)
                
                # Step 15: Select security question
                log("❓ Selecting security question")
                try:
                    page.select_option('select[name="regisFormSecurityQuesDropdown"]', label="What is your nick name?", timeout=5000)
                except:
                    try:
                        page.select_option('select[name="regisFormSecurityQuesDropdown"]', index=1, timeout=5000)
                        log("✅ Selected security question by index")
                    except Exception as e:
                        log(f"⚠️ Security question selection issue: {str(e)[:100]}")
                        page.evaluate("""
                            const select = document.querySelector('select[name="regisFormSecurityQuesDropdown"]');
                            if (select && select.options.length > 1) {
                                select.selectedIndex = 1;
                                select.dispatchEvent(new Event('change', { bubbles: true }));
                            }
                        """)
                        log("✅ Security question set using JavaScript")
                
                page.wait_for_timeout(1000)
                
                # Step 16: Enter security answer
                log("✍️ Entering security answer")
                page.fill('input[name="regisFormAnswer"]', "sun")
                page.wait_for_timeout(1000)
                
                # Step 17: Check the checkbox
                log("☑️ Accepting terms and conditions")
                page.check('input[value="something"][name="regisFormCheckbox"]')
                page.wait_for_timeout(1000)
                
                # Step 18: Submit the form
                log("🚀 Submitting registration form")
                page.click('button[name="regisSecurityInfoSubmit"]')
                page.wait_for_timeout(5000)
                
                # Step 19: Check for success message
                final_content = page.content()
                if "successfully" in final_content.lower() and "registered" in final_content.lower():
                    log(f"🎉 Registration successful for CA: {ca_number}")
                    log("✅ Account details have been sent to registered email")
                    downloads[session_id]["results"][ca_number] = "success"
                else:
                    log("⚠️ Registration completed but success message not confirmed")
                    downloads[session_id]["results"][ca_number] = "completed"
                
                browser.close()
                
        except Exception as e:
            log(f"❌ Registration failed for CA {ca_number}: {str(e)[:200]}")
            downloads[session_id]["results"][ca_number] = f"error: {str(e)[:100]}"

        downloads[session_id]["completed"] += 1
        downloads[session_id]["progress"] = int(downloads[session_id]["completed"] * 100 / total)
        
        if idx < total:
            log(f"\n⏳ Waiting 3 seconds before next registration...")
            time.sleep(3)

    # Final summary
    log(f"\n{'='*60}")
    log(f"📊 {discom_name.upper()} BATCH REGISTRATION SUMMARY")
    log(f"{'='*60}")
    log(f"Total CA numbers: {total}")
    log(f"Completed: {downloads[session_id]['completed']}")
    
    success_count = sum(1 for r in downloads[session_id]["results"].values() if r == "success")
    already_reg = sum(1 for r in downloads[session_id]["results"].values() if r == "already_registered")
    errors = total - success_count - already_reg
    
    log(f"✅ Successfully registered: {success_count}")
    log(f"⚠️ Already registered: {already_reg}")
    log(f"❌ Errors: {errors}")
    log(f"{'='*60}")
    
    downloads[session_id]["status"] = "completed"


@app.route('/register/cesc_mysore', methods=['POST'])
def register_cesc():
    data = request.json or {}
    ca_numbers_input = data.get('ca_numbers', '').strip()
    mobile_number = data.get('mobile_number', '').strip()
    email = data.get('email', '').strip()
    password = data.get('password', '').strip()
    
    if not ca_numbers_input or not mobile_number or not email or not password:
        return jsonify({"error": "All fields are required"}), 400
    
    # Parse CA numbers (support comma or newline separated)
    ca_numbers = []
    for line in ca_numbers_input.replace(',', '\n').split('\n'):
        ca = line.strip()
        if ca:
            ca_numbers.append(ca)
    
    if not ca_numbers:
        return jsonify({"error": "At least one CA number is required"}), 400
    
    session_id = str(uuid.uuid4())
    signup_url = "https://www.cescmysore.in/cesc/auth/signup"
    threading.Thread(target=register_generic_discom, args=(ca_numbers, mobile_number, email, password, session_id, signup_url, "CESC Mysore")).start()
    
    return jsonify({
        "session_id": session_id, 
        "status": "started",
        "total_ca_numbers": len(ca_numbers)
    })


@app.route('/register/gulbarga_discom', methods=['POST'])
def register_gulbarga():
    data = request.json or {}
    ca_numbers_input = data.get('ca_numbers', '').strip()
    mobile_number = data.get('mobile_number', '').strip()
    email = data.get('email', '').strip()
    password = data.get('password', '').strip()
    
    if not ca_numbers_input or not mobile_number or not email or not password:
        return jsonify({"error": "All fields are required"}), 400
    
    # Parse CA numbers (support comma or newline separated)
    ca_numbers = []
    for line in ca_numbers_input.replace(',', '\n').split('\n'):
        ca = line.strip()
        if ca:
            ca_numbers.append(ca)
    
    if not ca_numbers:
        return jsonify({"error": "At least one CA number is required"}), 400
    
    session_id = str(uuid.uuid4())
    signup_url = "https://www.gescomglb.org/gescom/auth/signup"
    threading.Thread(target=register_generic_discom, args=(ca_numbers, mobile_number, email, password, session_id, signup_url, "Gulbarga DISCOM")).start()
    
    return jsonify({
        "session_id": session_id, 
        "status": "started",
        "total_ca_numbers": len(ca_numbers)
    })


@app.route('/register/mangalore_discom', methods=['POST'])
def register_mangalore():
    data = request.json or {}
    ca_numbers_input = data.get('ca_numbers', '').strip()
    mobile_number = data.get('mobile_number', '').strip()
    email = data.get('email', '').strip()
    password = data.get('password', '').strip()
    
    if not ca_numbers_input or not mobile_number or not email or not password:
        return jsonify({"error": "All fields are required"}), 400
    
    # Parse CA numbers (support comma or newline separated)
    ca_numbers = []
    for line in ca_numbers_input.replace(',', '\n').split('\n'):
        ca = line.strip()
        if ca:
            ca_numbers.append(ca)
    
    if not ca_numbers:
        return jsonify({"error": "At least one CA number is required"}), 400
    
    session_id = str(uuid.uuid4())
    signup_url = "https://mescom.org.in/mescom/auth/signup"
    threading.Thread(target=register_generic_discom, args=(ca_numbers, mobile_number, email, password, session_id, signup_url, "Mangalore DISCOM (MESCOM)")).start()
    
    return jsonify({
        "session_id": session_id, 
        "status": "started",
        "total_ca_numbers": len(ca_numbers)
    })


@app.route('/register/hubli_discom', methods=['POST'])
def register_hubli():
    data = request.json or {}
    ca_numbers_input = data.get('ca_numbers', '').strip()
    mobile_number = data.get('mobile_number', '').strip()
    email = data.get('email', '').strip()
    password = data.get('password', '').strip()
    
    if not ca_numbers_input or not mobile_number or not email or not password:
        return jsonify({"error": "All fields are required"}), 400
    
    # Parse CA numbers (support comma or newline separated)
    ca_numbers = []
    for line in ca_numbers_input.replace(',', '\n').split('\n'):
        ca = line.strip()
        if ca:
            ca_numbers.append(ca)
    
    if not ca_numbers:
        return jsonify({"error": "At least one CA number is required"}), 400
    
    session_id = str(uuid.uuid4())
    signup_url = "https://www.hescom.co.in/hescom/auth/signup"
    threading.Thread(target=register_generic_discom, args=(ca_numbers, mobile_number, email, password, session_id, signup_url, "Hubli DISCOM (HESCOM)")).start()
    
    return jsonify({
        "session_id": session_id, 
        "status": "started",
        "total_ca_numbers": len(ca_numbers)
    })


def register_bescom_discom(ca_numbers, mobile_number, email, password, session_id):
    """BESCOM-specific registration function with proper error handling"""
    try:
        from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
    except Exception:
        downloads[session_id] = {
            "status": "error",
            "logs": ["Playwright not installed. Run: pip install playwright && playwright install chromium"]
        }
        return

    total = len(ca_numbers)
    downloads[session_id] = {
        "status": "registering",
        "progress": 0,
        "completed": 0,
        "total": total,
        "logs": [],
        "files": {},
        "results": {}
    }

    def log(m): _log(session_id, m)

    log(f"🚀 Starting Bangalore DISCOM (BESCOM) batch registration for {total} CA number(s)")
    
    for idx, ca_number in enumerate(ca_numbers, 1):
        ca_number = ca_number.strip()
        if not ca_number:
            continue
            
        log(f"\n{'='*60}")
        log(f"📋 Processing CA {idx}/{total}: {ca_number}")
        log(f"{'='*60}")
        
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(
                    headless=True,
                    args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-blink-features=AutomationControlled"]
                )
                context = browser.new_context(
                    ignore_https_errors=True,
                    user_agent=("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                                "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"),
                    viewport={"width": 1366, "height": 900}
                )
                context.add_init_script("Object.defineProperty(navigator,'webdriver',{get:()=>undefined})")

                page = context.new_page()
                
                # Step 1: Navigate to signup page
                log(f"🔄 Navigating to BESCOM signup page")
                page.goto("https://www.bescom.co.in/bescom/auth/signup", wait_until="domcontentloaded", timeout=60000)
                page.wait_for_timeout(3000)
                
                # Step 2: Find and enter CA number using BESCOM-specific selectors
                log(f"📝 Entering CA number: {ca_number}")
                ca_input_filled = False
                
                # BESCOM-specific selectors based on the actual page structure
                ca_selectors = [
                    'input[name="regisAgentHeadline"]',  # Exact match from screenshot
                    'input.title',  # Class-based selector from screenshot
                    'input[placeholder="Account ID*"]',  # Placeholder text visible in screenshot
                    'input[type="text"].title',  # Combined type and class
                    'input[type="text"]',  # Generic text input
                    "#form3Example3",  # Fallback to original
                ]
                
                for selector in ca_selectors:
                    try:
                        elements = page.locator(selector)
                        if elements.count() > 0:
                            # Check if this input is visible and enabled
                            element = elements.first
                            if element.is_visible() and element.is_enabled():
                                element.clear()  # Clear any existing value first
                                element.fill(ca_number)
                                ca_input_filled = True
                                log(f"✅ CA number entered using selector: {selector}")
                                break
                    except Exception as e:
                        log(f"⚠️ Failed with selector {selector}: {str(e)[:50]}")
                        continue
                
                if not ca_input_filled:
                    # Try JavaScript fallback
                    try:
                        log("🔄 Trying JavaScript fallback for CA input")
                        page.evaluate(f"""
                            const inputs = document.querySelectorAll('input[type="text"], input[name*="regis"], input.title');
                            for (let input of inputs) {{
                                if (input.offsetParent !== null) {{ // Check if visible
                                    input.value = '{ca_number}';
                                    input.dispatchEvent(new Event('input', {{ bubbles: true }}));
                                    input.dispatchEvent(new Event('change', {{ bubbles: true }}));
                                    break;
                                }}
                            }}
                        """)
                        ca_input_filled = True
                        log("✅ CA number entered using JavaScript fallback")
                    except Exception as e:
                        log(f"❌ JavaScript fallback failed: {str(e)[:50]}")
                
                if not ca_input_filled:
                    log("❌ Could not find CA number input field with any method")
                    raise Exception("CA number input field not found")
                
                page.wait_for_timeout(2000)
                
                # Step 3: Click Continue button
                log("🔘 Clicking Continue button")
                continue_clicked = False
                
                continue_selectors = [
                    'button:has-text("Continue")',
                    'input[value="Continue"]',
                    'button[name="regisContinueBtn"]',
                    '.btn:has-text("Continue")',
                    'button.btn-primary'
                ]
                
                for selector in continue_selectors:
                    try:
                        if page.locator(selector).count() > 0:
                            element = page.locator(selector).first
                            if element.is_visible() and element.is_enabled():
                                element.click()
                                continue_clicked = True
                                log(f"✅ Continue button clicked using selector: {selector}")
                                break
                    except Exception:
                        continue
                
                if not continue_clicked:
                    log("❌ Could not find or click Continue button")
                    raise Exception("Continue button not found")
                
                page.wait_for_timeout(4000)
                
                # Step 4: Check for "already registered" message
                page_content = page.content().lower()
                if "already registered" in page_content or "has been already registered" in page_content:
                    log(f"⚠️ CA {ca_number} is already registered")
                    downloads[session_id]["results"][ca_number] = "already_registered"
                    browser.close()
                    downloads[session_id]["completed"] += 1
                    downloads[session_id]["progress"] = int(downloads[session_id]["completed"] * 100 / total)
                    continue
                
                # Step 5: Check if we're on registration form page
                current_url = page.url
                if "registration" in current_url.lower() or page.locator('input[placeholder="+91 -"]').count() > 0:
                    log("✅ Navigated to registration form")
                    
                    # Step 6: Check and fill mobile number
                    mobile_input = page.locator('input[placeholder="+91 -"]')
                    if mobile_input.count() > 0:
                        existing_mobile = mobile_input.input_value()
                        if existing_mobile and existing_mobile.strip():
                            log(f"📱 Mobile number already present: {existing_mobile}")
                        else:
                            log(f"📱 Entering mobile number: {mobile_number}")
                            mobile_input.fill(mobile_number)
                            page.wait_for_timeout(1000)
                    
                    # Step 7: Enter email
                    log(f"📧 Entering email: {email}")
                    page.fill('input[placeholder="abc@gmail.com"]', email)
                    page.wait_for_timeout(1000)
                    
                    # Step 8: Confirm email
                    log("📧 Confirming email")
                    page.fill('input[name="regisFormConfirmEmail"]', email)
                    page.wait_for_timeout(1000)
                    
                    # Step 9: Click Save button
                    log("💾 Saving personal details")
                    page.click('button[name="regisPersonalDetailsSaveBtn"]')
                    page.wait_for_timeout(3000)
                    
                    # Step 10: Enter CA number (User ID)
                    log(f"🆔 Entering User ID (CA number): {ca_number}")
                    page.fill('input[placeholder="User ID"]', ca_number)
                    page.wait_for_timeout(1000)
                    
                    # Step 11: Enter password
                    log("🔒 Entering password")
                    page.fill('input[name="regisFormPassword"]', password)
                    page.wait_for_timeout(1000)
                    
                    # Step 12: Confirm password
                    log("🔒 Confirming password")
                    page.fill('input[name="regisFormConfirmPassword"]', password)
                    page.wait_for_timeout(1000)
                    
                    # Step 13: Click Save and Continue
                    log("💾 Saving username and password")
                    page.click('button[name="regisUserNameAndPassSaveBtn"]')
                    page.wait_for_timeout(3000)
                    
                    # Step 14: Enter date of birth
                    log("📅 Entering date of birth: 01-01-2001")
                    try:
                        date_selectors = [
                            'input[placeholder="dd-mm-yyyy"]',
                            'input[name*="dob" i]',
                            'input[name*="birth" i]',
                            'input[type="date"]',
                            'input[id*="dob" i]',
                            'input[id*="birth" i]'
                        ]
                        
                        date_filled = False
                        for selector in date_selectors:
                            try:
                                if page.locator(selector).count() > 0:
                                    page.fill(selector, "01-01-2001", timeout=5000)
                                    date_filled = True
                                    log(f"✅ Date filled using selector: {selector}")
                                    break
                            except:
                                continue
                        
                        if not date_filled:
                            page.click('input[placeholder="dd-mm-yyyy"]', timeout=5000)
                            page.keyboard.type("01012001", delay=100)
                            log("✅ Date entered using keyboard")
                        
                    except Exception as e:
                        log(f"⚠️ Date field issue, trying alternative method: {str(e)[:100]}")
                        page.evaluate("""
                            const dateInputs = document.querySelectorAll('input[placeholder*="dd"], input[type="date"], input[name*="dob"], input[name*="birth"]');
                            if (dateInputs.length > 0) {
                                dateInputs[0].value = '01-01-2001';
                                dateInputs[0].dispatchEvent(new Event('input', { bubbles: true }));
                                dateInputs[0].dispatchEvent(new Event('change', { bubbles: true }));
                            }
                        """)
                        log("✅ Date set using JavaScript")
                    
                    page.wait_for_timeout(1000)
                    
                    # Step 15: Select security question
                    log("❓ Selecting security question")
                    try:
                        page.select_option('select[name="regisFormSecurityQuesDropdown"]', label="What is your nick name?", timeout=5000)
                    except:
                        try:
                            page.select_option('select[name="regisFormSecurityQuesDropdown"]', index=1, timeout=5000)
                            log("✅ Selected security question by index")
                        except Exception as e:
                            log(f"⚠️ Security question selection issue: {str(e)[:100]}")
                            page.evaluate("""
                                const select = document.querySelector('select[name="regisFormSecurityQuesDropdown"]');
                                if (select && select.options.length > 1) {
                                    select.selectedIndex = 1;
                                    select.dispatchEvent(new Event('change', { bubbles: true }));
                                }
                            """)
                            log("✅ Security question set using JavaScript")
                    
                    page.wait_for_timeout(1000)
                    
                    # Step 16: Enter security answer
                    log("✍️ Entering security answer")
                    page.fill('input[name="regisFormAnswer"]', "sun")
                    page.wait_for_timeout(1000)
                    
                    # Step 17: Check the checkbox
                    log("☑️ Accepting terms and conditions")
                    page.check('input[value="something"][name="regisFormCheckbox"]')
                    page.wait_for_timeout(1000)
                    
                    # Step 18: Submit the form
                    log("🚀 Submitting registration form")
                    page.click('button[name="regisSecurityInfoSubmit"]')
                    page.wait_for_timeout(5000)
                    
                    # Step 19: Check for success message
                    final_content = page.content()
                    if "successfully" in final_content.lower() and "registered" in final_content.lower():
                        log(f"🎉 Registration successful for CA: {ca_number}")
                        log("✅ Account details have been sent to registered email")
                        downloads[session_id]["results"][ca_number] = "success"
                    else:
                        log("⚠️ Registration completed but success message not confirmed")
                        downloads[session_id]["results"][ca_number] = "completed"
                else:
                    log("❌ Did not navigate to registration form")
                    downloads[session_id]["results"][ca_number] = "navigation_failed"
                
                browser.close()
                
        except Exception as e:
            log(f"❌ Registration failed for CA {ca_number}: {str(e)[:200]}")
            downloads[session_id]["results"][ca_number] = f"error: {str(e)[:100]}"

        downloads[session_id]["completed"] += 1
        downloads[session_id]["progress"] = int(downloads[session_id]["completed"] * 100 / total)
        
        if idx < total:
            log(f"\n⏳ Waiting 3 seconds before next registration...")
            time.sleep(3)

    # Final summary
    log(f"\n{'='*60}")
    log(f"📊 BESCOM BATCH REGISTRATION SUMMARY")
    log(f"{'='*60}")
    log(f"Total CA numbers: {total}")
    log(f"Completed: {downloads[session_id]['completed']}")
    
    success_count = sum(1 for r in downloads[session_id]["results"].values() if r == "success")
    already_reg = sum(1 for r in downloads[session_id]["results"].values() if r == "already_registered")
    errors = total - success_count - already_reg
    
    log(f"✅ Successfully registered: {success_count}")
    log(f"⚠️ Already registered: {already_reg}")
    log(f"❌ Errors: {errors}")
    log(f"{'='*60}")
    
    downloads[session_id]["status"] = "completed"


@app.route('/register/bangalore_discom', methods=['POST'])
def register_bangalore():
    data = request.json or {}
    ca_numbers_input = data.get('ca_numbers', '').strip()
    mobile_number = data.get('mobile_number', '').strip()
    email = data.get('email', '').strip()
    password = data.get('password', '').strip()
    
    if not ca_numbers_input or not mobile_number or not email or not password:
        return jsonify({"error": "All fields are required"}), 400
    
    # Parse CA numbers (support comma or newline separated)
    ca_numbers = []
    for line in ca_numbers_input.replace(',', '\n').split('\n'):
        ca = line.strip()
        if ca:
            ca_numbers.append(ca)
    
    if not ca_numbers:
        return jsonify({"error": "At least one CA number is required"}), 400
    
    session_id = str(uuid.uuid4())
    threading.Thread(target=register_bescom_discom, args=(ca_numbers, mobile_number, email, password, session_id)).start()
    
    return jsonify({
        "session_id": session_id, 
        "status": "started",
        "total_ca_numbers": len(ca_numbers)
    })


@app.route('/boards', methods=['GET'])
def get_boards():
    return jsonify({
        "boards": [
            {"id": "chandigarh", "name": "Chandigarh Power", "icon": "⚡", "has_months": True},
            {"id": "bses", "name": "BSES (Delhi)", "icon": "🏢"},
            {"id": "jharkhand", "name": "Jharkhand (JBVNL)", "icon": "🔌", "has_months": True},
            {"id": "north_bihar", "name": "North Bihar", "icon": "💡"},
            {"id": "dakshin_haryana", "name": "Dakshin Haryana", "icon": "🌐"},
            {"id": "uttar_haryana", "name": "Uttar Haryana", "icon": "🏞️"},
            {"id": "tgspdcl", "name": "Telangana Southern Power", "icon": "⚡"},
            {"id": "dakshin_gujarat", "name": "Dakshin Gujarat (DGVCL)", "icon": "🌊"},
            {"id": "apepdcl", "name": "AP Eastern Power (APEPDCL)", "icon": "⚡"},
            {"id": "apcpdcl", "name": "AP Central Power (APCPDCL)", "icon": "⚡", "has_months": True},
            {"id": "apspdcl", "name": "AP Southern Power (APSPDCL)", "icon": "⚡"},
            {"id": "goa_discom", "name": "Goa DISCOM", "icon": "🏖️"},
            {"id": "mp_poorva_kshetra", "name": "MP Poorva Kshetra", "icon": "🏛️", "has_months": True},
            {"id": "mp_madhya_kshetra", "name": "MP Madhya Kshetra", "icon": "🏛️"},
            {"id": "mp_paschim_kshetra", "name": "MP Paschim Kshetra", "icon": "🏛️"},
            {"id": "kerala_kseb", "name": "Kerala KSEB", "icon": "🌴"},
            {"id": "bescom", "name": "BESCOM (Karnataka)", "icon": "🏭", "has_months": True},
            {"id": "cescmysore", "name": "CESC Mysore (Karnataka)", "icon": "🏢", "has_months": True},
            {"id": "gescom", "name": "GESCOM (Karnataka)", "icon": "⚡", "has_months": True},
            {"id": "hescom", "name": "HESCOM (Karnataka)", "icon": "🔌", "has_months": True},
            {"id": "mescom", "name": "MESCOM (Karnataka)", "icon": "🏢", "has_months": True},
            {"id": "ndmc", "name": "New Delhi Municipal Council", "icon": "🏛️", "has_months": True},
            {"id": "upcl_discom", "name": "UPCL (Uttarakhand)", "icon": "⛰️"},
            {"id": "uppcl_discom", "name": "UPPCL DISCOM (UP)", "icon": "⚡", "has_months": True},
            {"id": "msedcl", "name": "MSEDCL (Maharashtra)", "icon": "🇮🇳"},
        ]
    })


if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)

