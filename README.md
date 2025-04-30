# agentless-reporting

# Prisma Cloud Agentless Scan Health Report

**Purpose:**
This Python 3 script queries the Prisma Cloud Compute API (`/cloud-scan-rules`) to report on agentless host scan health. It calculates summary statistics and saves detailed regional data categorized by scan status (Successful, Issues, Unsupported, Excluded) into separate JSON files.

**Prerequisites:**
*   Python 3 (Uses only standard libraries like `urllib`, `json`, `logging`, `sys`, `collections`. No external libraries like `requests` or `pandas` are needed, so no `pip install` is required).
*   A `config.py` file in the same directory with your Prisma Cloud API URL (`url`), Compute Console URL (`compute_url`), credentials (`api_key`, `api_secret`).

**Configuration:**
1.  Create a file named `config.py` in the same directory as the script.
2.  Add the following content, replacing placeholder values with your actual details:
    ```python
    # config.py

    # URL for the main Prisma Cloud portal/API gateway (USE THIS FOR LOGIN)
    # Example: url = "https://api.us.prismacloud.io"
    url = "YOUR_PRISMA_PORTAL_URL"

    # URL for the Compute Console (obtained from Prisma Cloud UI or /meta_info)
    # Example: compute_url = "https://us-east1.cloud.twistlock.com/us-12345/"
    # Ensure it has a trailing slash /
    compute_url = "YOUR_COMPUTE_CONSOLE_URL/"

    # Use Access Key ID and Secret Key OR Username/Password
    api_key = "YOUR_ACCESS_KEY_ID_OR_USERNAME"
    api_secret = "YOUR_SECRET_KEY_OR_PASSWORD"

    ```
3.  If running in an environment requiring an HTTPS proxy, set the `HTTPS_PROXY` environment variable before executing the script (e.g., `export HTTPS_PROXY="http://proxy.example.com:8080"`). The script uses standard Python libraries that automatically detect this variable.

**How to Run:**
chmod +x agentless-scan-status.py
./agentless-scan-status.py



```bash
python3 prisma_scan_coverage.py


--- Agentless Host Scan Health Summary ---
Agentless Host Scan Health (from cloud-scan-rules):
  - Hosts Scanned Successfully: 20
  - Hosts Excluded from Scan: 16
  - Hosts Unsupported by Scanner: 2
  - Hosts with Scan Issues ('issued' count): 1
  - Regions Reporting Scan Issues: 1
  - (Hosts Pending Scan: 0)
  - Agentless Host Scan Coverage (Successful / [Successful+Unsupported+Issues]): 86.96%

--- Saving Detailed Regional Data ---
Data saved to successful_scans.json
Data saved to scan_issues.json
Data saved to unsupported_scans.json
Data saved to excluded_scans.json

Detailed logs available in prisma_scan_coverage.log
Categorized regional details saved to .json files (if applicable).
Script finished.
