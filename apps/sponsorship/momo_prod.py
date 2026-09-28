import uuid

import requests
from django.conf import settings

BASE_URL = "https://proxy.momoapi.mtn.com"


def generate_uuid():
    return str(uuid.uuid4())


# Generate headers for MoMo API requests
def momo_headers(subscription_key, token=None, ref_id=None):
    headers = {"Ocp-Apim-Subscription-Key": subscription_key}

    if token:
        headers["Authorization"] = f"Bearer {token}"
        headers["X-Target-Environment"] = "mtnuganda"

    if ref_id:
        headers["X-Reference-Id"] = ref_id

    # If callback is set in settings
    if hasattr(settings, "MOMO_CALLBACK_URL"):
        headers["X-Callback-Url"] = settings.MOMO_CALLBACK_URL

    return headers


# Generate access token
def create_access_token(reference_id, api_key, subscription_key):
    """Generate access token using stored API user credentials."""
    url = f"{BASE_URL}/collection/token/"
    auth = requests.auth.HTTPBasicAuth(reference_id, api_key)
    headers = {"Ocp-Apim-Subscription-Key": subscription_key}
    res = requests.post(url, headers=headers, auth=auth, timeout=30)
    if res.status_code == 200:
        return res.json().get("access_token")
    return None


# Initiate MoMo Collection request
def request_to_pay(access_token, subscription_key, phone, amount, transaction_id):
    """Initiate MTN MoMo Collection request."""
    if not settings.MOMO_PAYMENT_INITIATION_ENABLED:
        return 503, "Mobile Money payment initiation is temporarily paused."

    # Convert phone to MTN accepted format
    if phone.startswith("0"):
        phone = "256" + phone[1:]

    url = f"{BASE_URL}/collection/v1_0/requesttopay"

    headers = momo_headers(subscription_key, access_token, transaction_id)
    headers["X-Callback-Url"] = settings.MOMO_CALLBACK_URL  # REQUIRED

    body = {
        "amount": str(amount),
        "currency": "UGX",
        "externalId": transaction_id,  # better than random
        "payer": {
            "partyIdType": "MSISDN",
            "partyId": phone,  # now correct format
        },
        "payerMessage": "Pendeza Uganda Donation",
        "payeeNote": "Thank you for using our system",
    }

    res = requests.post(url, json=body, headers=headers, timeout=30)
    return res.status_code, res.text
