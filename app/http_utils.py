import time
from urllib.parse import urljoin
import requests

MAX_RETRIES = 3
RETRY_DELAY_SECONDS = 2
CHEMBL_BASE_URL = "https://www.ebi.ac.uk"

def get_with_retry(url, params, timeout=30.0, context_label=""):
    for attempt in range(MAX_RETRIES):
        try:
            response = requests.get(url, params=params, timeout=timeout)
            response.raise_for_status()
            return response
        except requests.exceptions.RequestException as e:
            print(f"Request error on attempt {attempt + 1} for {context_label}: {e}")
            if attempt < MAX_RETRIES - 1:
                time.sleep(RETRY_DELAY_SECONDS)
    print(f"Failed after {MAX_RETRIES} attempts for {context_label}")


def resolve_next_url(next_value: str | None, base_url: str = CHEMBL_BASE_URL) -> str | None:
    """
    ChEMBL's page_meta.next is sometimes a relative path
    (e.g. "/chembl/api/data/drug_indication.json?limit=20&offset=20&mesh_id=D008288")
    rather than a full URL. This resolves it to an absolute URL so it can be
    passed straight into get_with_retry().
    """
    if not next_value:
        return None
    if next_value.startswith("http://") or next_value.startswith("https://"):
        return next_value
    return urljoin(base_url, next_value)
