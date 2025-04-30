#!/usr/bin/env python3
# import requests - REMOVED
import json
import sys
import logging
import config
import urllib.request # ADDED
import urllib.parse   # ADDED
import urllib.error   # ADDED
from collections import defaultdict
from time import sleep # Keep sleep for potential future retry logic

# --- Constants ---
LOG_FILENAME = "prisma_scan_coverage.log"
# Output files for categorized scan results
SUCCESSFUL_OUTPUT_FILE = "successful_scans.json"
ISSUES_OUTPUT_FILE = "scan_issues.json"
UNSUPPORTED_OUTPUT_FILE = "unsupported_scans.json"
EXCLUDED_OUTPUT_FILE = "excluded_scans.json"

API_ENDPOINT_LOGIN = "login"
API_ENDPOINT_SCAN_RULES = "api/v1/cloud-scan-rules"
API_LIMIT = 50

# --- Authentication ---
def login():
    """Authenticates to the MAIN Prisma Cloud portal API and returns the token."""
    login_api_endpoint = config.url.rstrip("/") + "/" + API_ENDPOINT_LOGIN
    payload_dict = {"username": config.api_key, "password": config.api_secret}
    if hasattr(config, "customer_name") and config.customer_name:
        payload_dict["customerName"] = config.customer_name

    # Encode payload to JSON bytes
    payload_json_bytes = json.dumps(payload_dict).encode('utf-8')

    headers = {
        "Content-Type": "application/json; charset=UTF-8",
        "Accept": "application/json; charset=UTF-8",
        "Content-Length": len(payload_json_bytes) # Required by urllib for POST
    }

    req = urllib.request.Request(login_api_endpoint, data=payload_json_bytes, headers=headers, method='POST')

    try:
        logging.info(f"Attempting login to Main Portal: {login_api_endpoint}...")
        with urllib.request.urlopen(req, timeout=30) as response:
            response_body = response.read()
            response_status = response.getcode()
            logging.debug(f"Login response status: {response_status}")

            if response_status == 200:
                logging.info("Main Portal Login successful.")
                response_data = json.loads(response_body.decode('utf-8'))
                token = response_data.get("token")
                if not token:
                    logging.error("Error: 'token' not found in login response.")
                    sys.exit(1)
                return token.strip('"')
            else:
                # This part might not be reached if urlopen raises HTTPError for non-200
                logging.error(f"Login failed with status code: {response_status}")
                logging.error(f"Response body: {response_body.decode('utf-8', errors='ignore')}")
                sys.exit(1)

    except urllib.error.HTTPError as e:
        # Handle HTTP errors (4xx, 5xx)
        logging.error(f"HTTP Error during main portal login: {e.code} {e.reason}", exc_info=True)
        try:
            error_body = e.read().decode('utf-8', errors='ignore')
            logging.error(f"Response body: {error_body}")
            # Try parsing JSON error message from Prisma
            try:
                error_detail = json.loads(error_body).get("message", error_body)
                logging.error(f"Parsed error detail: {error_detail}")
            except json.JSONDecodeError:
                pass # Keep raw body if not JSON
        except Exception as read_err:
            logging.error(f"Could not read error response body: {read_err}")
        sys.exit(1)
    except urllib.error.URLError as e:
        # Handle non-HTTP errors (e.g., connection refused, DNS errors)
        logging.error(f"URL Error during main portal login: {e.reason}", exc_info=True)
        sys.exit(1)
    except json.JSONDecodeError:
        logging.error("Error: Failed to decode JSON response from login.", exc_info=True)
        sys.exit(1)
    except KeyError:
        logging.error("Error: 'token' key not found in login response JSON.", exc_info=True)
        sys.exit(1)
    except Exception as e:
        # Catch any other unexpected errors during login
        logging.error(f"An unexpected error occurred during login: {e}", exc_info=True)
        sys.exit(1)


# --- API Data Fetching (Generic Paginated Getter) ---
def get_paginated_data(token, base_url, endpoint_path, params=None):
    """Fetches all data from a paginated Prisma Cloud COMPUTE API endpoint."""
    all_data = []
    offset = 0
    base_endpoint_url = base_url.rstrip("/") + "/" + endpoint_path
    headers = {
        "x-redlock-auth": token,
        "Accept": "application/json; charset=UTF-8",
    }
    if params is None:
        params = {}

    logging.info(f"Fetching data from Compute endpoint base: {base_endpoint_url} with initial params: {params}")
    while True:
        current_params = params.copy()
        current_params["offset"] = offset
        current_params["limit"] = API_LIMIT

        # Encode parameters and construct full URL
        query_string = urllib.parse.urlencode(current_params)
        full_url = f"{base_endpoint_url}?{query_string}"
        logging.debug(f"Requesting URL: {full_url}")

        req = urllib.request.Request(full_url, headers=headers, method='GET')

        try:
            with urllib.request.urlopen(req, timeout=60) as response:
                response_body = response.read()
                response_status = response.getcode()
                logging.debug(f"GET {endpoint_path} response status: {response_status}")

                if response_status == 200:
                    data_chunk = json.loads(response_body.decode('utf-8'))

                    if data_chunk is None: data_chunk = []
                    if not isinstance(data_chunk, list):
                         if isinstance(data_chunk, dict) and offset == 0:
                             logging.warning(f"API response from {full_url} is not a list, but a dict: {data_chunk}. Treating as empty list.")
                             data_chunk = []
                         else:
                             logging.error(f"Error: API response from {full_url} is not a list: {type(data_chunk)}")
                             sys.exit(1)
                    if not data_chunk: break

                    all_data.extend(data_chunk)
                    logging.info(f"Retrieved {len(data_chunk)} items from {endpoint_path}, total so far: {len(all_data)}")

                    if len(data_chunk) < API_LIMIT: break
                    offset += len(data_chunk)
                else:
                    # Should be caught by HTTPError, but as a fallback
                    logging.error(f"Received non-200 status {response_status} from {full_url}")
                    logging.error(f"Response body: {response_body.decode('utf-8', errors='ignore')}")
                    sys.exit(1)

        except urllib.error.HTTPError as e:
            logging.error(f"HTTP Error fetching data from {full_url}: {e.code} {e.reason}", exc_info=True)
            error_body = "Could not read error body."
            try:
                error_body = e.read().decode('utf-8', errors='ignore')
                logging.error(f"Response body: {error_body}")
            except Exception as read_err:
                 logging.error(f"Could not read error response body: {read_err}")

            if e.code == 401:
                 logging.error("Received 401 Unauthorized. Check token validity and 'x-redlock-auth' header usage.")
                 sys.exit(1)
            if e.code == 429:
                 logging.warning(f"Rate limit hit (429) for {full_url}. Consider adding delays/retries.")
                 # Implement sleep/retry here if desired, otherwise exit
                 sys.exit(1) # Exit on rate limit for now
            # Exit on other client/server errors
            sys.exit(1)
        except urllib.error.URLError as e:
            logging.error(f"URL Error fetching data from {full_url}: {e.reason}", exc_info=True)
            sys.exit(1)
        except json.JSONDecodeError:
            logging.error(f"Error: Failed to decode JSON from {full_url}.", exc_info=True)
            sys.exit(1)
        except Exception as e:
            logging.error(f"An unexpected error occurred during fetch from {full_url}: {e}", exc_info=True)
            sys.exit(1)

    logging.info(f"Finished fetching {endpoint_path}. Total items: {len(all_data)}")
    return all_data

# --- Function to save data to JSON file ---
def save_to_json(data, filename):
    """Saves the provided data structure to a JSON file."""
    logging.info(f"Attempting to save data to {filename}...")
    try:
        with open(filename, 'w') as f:
            json.dump(data, f, indent=4) # Use indent for readability
        logging.info(f"Successfully saved data to {filename}")
        print(f"Data saved to {filename}") # Also notify user on console
    except IOError as e:
        logging.error(f"Error saving data to {filename}: {e}", exc_info=True)
        print(f"Error saving data to {filename}", file=sys.stderr)
    except TypeError as e:
        logging.error(f"Error serializing data to JSON for {filename}: {e}", exc_info=True)
        print(f"Error serializing data to JSON for {filename}", file=sys.stderr)


# --- Main Execution ---
if __name__ == "__main__":
    # --- Configure Logging ---
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
        filename=LOG_FILENAME,
        filemode="w",
    )
    logging.info("Script started.")

    # Step 1: Login
    auth_token = login()

    # Step 2: Fetch cloud scan rules data
    scan_rule_params = {}
    if hasattr(config, "project_name") and config.project_name:
        scan_rule_params["project"] = config.project_name
        logging.info(f"Filtering scan rules by project: {config.project_name}")
    scan_rules_data = get_paginated_data(
        auth_token, config.compute_url, API_ENDPOINT_SCAN_RULES, scan_rule_params
    )

    # --- Processing Step 3: Process cloud-scan-rules data ---
    total_successful_agentless = 0
    total_excluded_agentless = 0
    total_unsupported_agentless = 0
    total_pending_agentless = 0
    total_scan_issues = 0 # Count based on 'issued' field
    regions_reporting_issues = set()

    # Lists to store regional data for output files
    successful_regions_data = []
    issue_regions_data = []
    unsupported_regions_data = []
    excluded_regions_data = []

    logging.info("Processing cloud-scan-rules data...")
    if scan_rules_data:
        for rule in scan_rules_data:
            account_id = rule.get("credentialId", "N/A")
            account_name = rule.get("credential", {}).get("accountName", "N/A")
            account_state = rule.get("agentlessAccountState")
            if not account_state or "regions" not in account_state:
                continue

            for region_data in account_state.get("regions", []):
                region_name = region_data.get("region", "N/A")
                region_key = f"{account_id}:{region_name}"
                scan_id = region_data.get("scanID")

                # Create context dict to add to output data
                context = {
                    "accountId": account_id,
                    "accountName": account_name,
                    "region": region_name,
                    "scanIdContext": scan_id
                }

                coverage = region_data.get("scanCoverage")
                if coverage:
                    successful_count = coverage.get("successful", 0)
                    excluded_count = coverage.get("excluded", 0)
                    unsupported_count = coverage.get("unsupported", 0)
                    pending_count = coverage.get("pending", 0)
                    issued_count = coverage.get("issued", 0) # Issues count

                    # Add counts to totals
                    total_successful_agentless += successful_count
                    total_excluded_agentless += excluded_count
                    total_unsupported_agentless += unsupported_count
                    total_pending_agentless += pending_count
                    total_scan_issues += issued_count

                    # Append region data to lists based on counts > 0
                    if successful_count > 0:
                        successful_regions_data.append({**context, **region_data})
                    if issued_count > 0:
                        issue_regions_data.append({**context, **region_data})
                        regions_reporting_issues.add(region_key)
                        # Log errors associated with issues, but don't print to console
                        errors = region_data.get("errorsInfo")
                        if errors:
                             for error_info in errors:
                                 logging.warning(f"Regional Scan Issue Detail: Account={account_id}, Region={region_name}, Cause={error_info.get('cause', 'N/A')}, Error={error_info.get('error', 'N/A')}")
                        else:
                             logging.warning(f"Region {region_key} reported issues(issued)={issued_count} but has no errorsInfo details in scan rule data.")

                    if unsupported_count > 0:
                        unsupported_regions_data.append({**context, **region_data})
                    if excluded_count > 0:
                        excluded_regions_data.append({**context, **region_data})

    else:
        logging.warning("No cloud-scan-rules data to process.")

    # Calculate metrics from scan rules
    coverage_denominator = (
        total_successful_agentless
        + total_unsupported_agentless
        + total_scan_issues # Include hosts with issues in denominator
    )
    num_regions_reporting_issues = len(regions_reporting_issues)

    agentless_scan_coverage_percentage = 0.0
    if coverage_denominator > 0:
        agentless_scan_coverage_percentage = (
            total_successful_agentless / coverage_denominator
        ) * 100

    # --- Log Summary Section Header ---
    logging.info("\n--- Agentless Host Scan Health Summary ---")

    # --- Prepare Summary ---
    summary_lines = [
        f"Agentless Host Scan Health (from cloud-scan-rules):",
        f"  - Hosts Scanned Successfully: {total_successful_agentless}",
        f"  - Hosts Excluded from Scan: {total_excluded_agentless}",
        f"  - Hosts Unsupported by Scanner: {total_unsupported_agentless}",
        f"  - Hosts with Scan Issues ('issued' count): {total_scan_issues}",
        f"  - Regions Reporting Scan Issues: {num_regions_reporting_issues}",
        f"  - (Hosts Pending Scan: {total_pending_agentless})",
        f"  - Agentless Host Scan Coverage (Successful / [Successful+Unsupported+Issues]): {agentless_scan_coverage_percentage:.2f}%",
    ]

    # --- Output Final Summary to Terminal AND Log File ---
    print("\n--- Agentless Host Scan Health Summary ---")
    for line in summary_lines:
        print(line)
        logging.info(line)

    # --- Step 4: Save categorized data to files ---
    print("\n--- Saving Detailed Regional Data ---")
    if successful_regions_data:
        save_to_json(successful_regions_data, SUCCESSFUL_OUTPUT_FILE)
    else:
        print(f"No regions with successful scans found to save to {SUCCESSFUL_OUTPUT_FILE}.")
        logging.info(f"No regions with successful scans found to save to {SUCCESSFUL_OUTPUT_FILE}.")

    if issue_regions_data:
        save_to_json(issue_regions_data, ISSUES_OUTPUT_FILE)
    else:
        print(f"No regions reporting issues found to save to {ISSUES_OUTPUT_FILE}.")
        logging.info(f"No regions reporting issues found to save to {ISSUES_OUTPUT_FILE}.")

    if unsupported_regions_data:
        save_to_json(unsupported_regions_data, UNSUPPORTED_OUTPUT_FILE)
    else:
        print(f"No regions with unsupported hosts found to save to {UNSUPPORTED_OUTPUT_FILE}.")
        logging.info(f"No regions with unsupported hosts found to save to {UNSUPPORTED_OUTPUT_FILE}.")

    if excluded_regions_data:
        save_to_json(excluded_regions_data, EXCLUDED_OUTPUT_FILE)
    else:
        print(f"No regions with excluded hosts found to save to {EXCLUDED_OUTPUT_FILE}.")
        logging.info(f"No regions with excluded hosts found to save to {EXCLUDED_OUTPUT_FILE}.")


    # --- Final Logging Info ---
    logging.info(f"Detailed logs available in {LOG_FILENAME}")
    logging.info("Script finished.")
    print(f"\nDetailed logs available in {LOG_FILENAME}")
    print(f"Categorized regional details saved to .json files (if applicable).")
    print("Script finished.")
