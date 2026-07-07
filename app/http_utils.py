import time

import requests

MAX_RETRIES = 3
RETRY_DELAY_SECONDS = 2


def get_with_retry(url, params, timeout=30.0, context_label=""):
    for attempt in range(MAX_RETRIES):
        try:
            response = requests.get(url, params=params, timeout=timeout)
            return response
        except requests.exceptions.ConnectionError as e:
            print(f"Connection error on attempt {attempt + 1} for {context_label}: {e}")
            if attempt < MAX_RETRIES - 1:
                time.sleep(RETRY_DELAY_SECONDS)
    print(f"Failed after {MAX_RETRIES} attempts for {context_label}")
