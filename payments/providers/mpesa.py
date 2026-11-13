
import base64
import logging
from datetime import datetime
from decimal import Decimal, InvalidOperation
from zoneinfo import ZoneInfo

import requests

from django.conf import settings


logger = logging.getLogger(__name__)


class MpesaError(Exception):
    """Raised when a Daraja API request fails."""
    pass


# ==========================================================
# 1. ENVIRONMENT AND API URLS
# ==========================================================

def get_mpesa_base_url():
    """
    Return the correct Safaricom API base URL.
    """

    environment = str(
        getattr(settings, "MPESA_ENVIRONMENT", "sandbox")
    ).strip().lower()

    if environment == "sandbox":
        return "https://sandbox.safaricom.co.ke"

    if environment == "production":
        return "https://api.safaricom.co.ke"

    raise MpesaError(
        "Invalid M-Pesa environment. "
        "Use sandbox or production."
    )


def get_access_token():
    """
    Authenticate ShikaTicko with Safaricom Daraja OAuth.
    """

    consumer_key = str(
        getattr(settings, "MPESA_CONSUMER_KEY", "")
    ).strip()

    consumer_secret = str(
        getattr(settings, "MPESA_CONSUMER_SECRET", "")
    ).strip()

    if not consumer_key or not consumer_secret:
        raise MpesaError(
            "M-Pesa Consumer Key or Consumer Secret is missing."
        )

    url = f"{get_mpesa_base_url()}/oauth/v1/generate"

    try:
        response = requests.get(
            url,
            params={
                "grant_type": "client_credentials"
            },
            auth=(
                consumer_key,
                consumer_secret
            ),
            timeout=(15, 30)
        )

        try:
            data = response.json()
        except ValueError:
            raise MpesaError(
                "Safaricom returned an invalid OAuth response."
            )

        if not response.ok:
            message = data.get(
                "errorMessage",
                "Safaricom OAuth authentication failed."
            )

            raise MpesaError(
                f"Daraja OAuth error "
                f"({response.status_code}): {message}"
            )

    except requests.Timeout:
        raise MpesaError(
            "Connection to Safaricom OAuth timed out."
        )

    except requests.ConnectionError:
        raise MpesaError(
            "Could not connect to Safaricom OAuth."
        )

    except requests.RequestException as error:
        raise MpesaError(
            f"OAuth request failed: {error}"
        )

    access_token = data.get("access_token")

    if not access_token:
        raise MpesaError(
            "Safaricom did not return an access token."
        )

    return access_token


# ==========================================================
# 2. PHONE NUMBER NORMALIZATION
# ==========================================================

def normalize_mpesa_phone(phone):
    """
    Convert Kenyan phone numbers to 254XXXXXXXXX.
    """

    phone = str(phone).strip()

    phone = (
        phone.replace(" ", "")
        .replace("-", "")
        .replace("+", "")
        .replace("(", "")
        .replace(")", "")
    )

    if phone.startswith("0") and len(phone) == 10:
        phone = "254" + phone[1:]

    elif len(phone) == 9 and phone.startswith(("7", "1")):
        phone = "254" + phone

    if (
        len(phone) != 12
        or not phone.startswith("254")
        or not phone.isdigit()
    ):
        raise MpesaError(
            "Enter a valid Kenyan M-Pesa phone number."
        )

    return phone


# ==========================================================
# 3. PRODUCTION SHORTCODE AND PASSWORD
# ==========================================================

def get_mpesa_credentials():
    """
    Read the configured shortcode and passkey.
    """

    shortcode = str(
        getattr(settings, "MPESA_SHORTCODE", "")
    ).strip()

    passkey = str(
        getattr(settings, "MPESA_PASSKEY", "")
    ).strip()

    if not shortcode or not shortcode.isdigit():
        raise MpesaError(
            "A valid M-Pesa Business Shortcode is required."
        )

    if not passkey:
        raise MpesaError(
            "M-Pesa Passkey is missing."
        )

    return shortcode, passkey


def generate_password():
    """
    Generate the Lipa Na M-Pesa Online password.

    Uses the Safaricom-issued Business Shortcode,
    production passkey and Nairobi timestamp.
    """

    shortcode, passkey = get_mpesa_credentials()

    timestamp = datetime.now(
        ZoneInfo("Africa/Nairobi")
    ).strftime("%Y%m%d%H%M%S")

    password_string = (
        shortcode + passkey + timestamp
    )

    password = base64.b64encode(
        password_string.encode("utf-8")
    ).decode("utf-8")

    return password, timestamp


# ==========================================================
# 4. COMMON DAR AJA RESPONSE HANDLING
# ==========================================================

def _send_daraja_request(url, payload, access_token):
    """
    Send an authenticated JSON POST request to Daraja.
    """

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

    try:
        response = requests.post(
            url,
            json=payload,
            headers=headers,
            timeout=(15, 45)
        )

        try:
            data = response.json()
        except ValueError:
            raise MpesaError(
                "Safaricom returned an invalid response."
            )

        if not response.ok:
            error_code = data.get(
                "errorCode",
                response.status_code
            )

            error_message = data.get(
                "errorMessage",
                data.get(
                    "ResponseDescription",
                    "Safaricom rejected the request."
                )
            )

            raise MpesaError(
                f"Daraja error ({error_code}): "
                f"{error_message}"
            )

        return data

    except requests.Timeout:
        raise MpesaError(
            "Safaricom request timed out. "
            "Check payment status before retrying."
        )

    except requests.ConnectionError:
        raise MpesaError(
            "Could not connect to Safaricom. "
            "Please try again later."
        )

    except requests.RequestException as error:
        raise MpesaError(
            f"Daraja request failed: {error}"
        )


# ==========================================================
# 5. INITIATE STK PUSH
# ==========================================================

def initiate_stk_push(
    phone,
    amount,
    account_reference,
    transaction_description="ShikaTicko Ticket"
):
    """
    Initiate an M-Pesa STK Push.

    Supports:
        CustomerPayBillOnline
        CustomerBuyGoodsOnline

    Production Buy Goods configuration:
        BusinessShortCode = Safaricom-issued shortcode
        PartyB = registered Buy Goods Till number

    IMPORTANT:
        A successful STK response means the request was
        accepted, not that the customer has paid.
    """

    # ------------------------------------------------------
    # NORMALIZE PHONE
    # ------------------------------------------------------

    phone = normalize_mpesa_phone(phone)

    # ------------------------------------------------------
    # VALIDATE AMOUNT
    # ------------------------------------------------------

    try:
        decimal_amount = Decimal(str(amount))

    except (InvalidOperation, TypeError, ValueError):
        raise MpesaError(
            "The payment amount must be a valid number."
        )

    if (
        not decimal_amount.is_finite()
        or decimal_amount < 1
        or decimal_amount != decimal_amount.to_integral_value()
    ):
        raise MpesaError(
            "M-Pesa payments must be whole KES amounts "
            "of at least KES 1."
        )

    amount = int(decimal_amount)

    # ------------------------------------------------------
    # LOAD CONFIGURATION
    # ------------------------------------------------------

    environment = str(
        getattr(settings, "MPESA_ENVIRONMENT", "sandbox")
    ).strip().lower()

    shortcode, passkey = get_mpesa_credentials()

    till_number = str(
        getattr(settings, "MPESA_TILL_NUMBER", "")
    ).strip()

    callback_url = str(
        getattr(settings, "MPESA_CALLBACK_URL", "")
    ).strip()

    transaction_type = str(
        getattr(
            settings,
            "MPESA_TRANSACTION_TYPE",
            "CustomerBuyGoodsOnline"
        )
    ).strip()

    # ------------------------------------------------------
    # VALIDATE CONFIGURATION
    # ------------------------------------------------------

    if environment not in ("sandbox", "production"):
        raise MpesaError(
            "MPESA_ENVIRONMENT must be sandbox or production."
        )

    if transaction_type not in (
        "CustomerPayBillOnline",
        "CustomerBuyGoodsOnline"
    ):
        raise MpesaError(
            "Invalid M-Pesa transaction type."
        )

    if transaction_type == "CustomerBuyGoodsOnline":

        if not till_number or not till_number.isdigit():
            raise MpesaError(
                "A valid registered Buy Goods Till number "
                "is required."
            )

        party_b = till_number

    else:
        party_b = shortcode

    if not callback_url.startswith("https://"):
        raise MpesaError(
            "M-Pesa callback URL must use HTTPS."
        )

    # ------------------------------------------------------
    # AUTHENTICATE
    # ------------------------------------------------------

    access_token = get_access_token()

    # ------------------------------------------------------
    # GENERATE PASSWORD
    # ------------------------------------------------------

    password, timestamp = generate_password()

    # ------------------------------------------------------
    # STK PUSH ENDPOINT
    # ------------------------------------------------------

    url = (
        f"{get_mpesa_base_url()}"
        "/mpesa/stkpush/v1/processrequest"
    )

    # ------------------------------------------------------
    # STK PUSH PAYLOAD
    # ------------------------------------------------------

    payload = {
        "BusinessShortCode": shortcode,
        "Password": password,
        "Timestamp": timestamp,
        "TransactionType": transaction_type,
        "Amount": amount,
        "PartyA": phone,
        "PartyB": party_b,
        "PhoneNumber": phone,
        "CallBackURL": callback_url,
        "AccountReference": str(account_reference)[:12],
        "TransactionDesc": str(transaction_description)[:13],
    }

    # ------------------------------------------------------
    # SEND REQUEST
    # ------------------------------------------------------

    result = _send_daraja_request(
        url,
        payload,
        access_token
    )

    # ------------------------------------------------------
    # VALIDATE RESPONSE
    # ------------------------------------------------------

    if str(result.get("ResponseCode")) != "0":
        raise MpesaError(
            result.get(
                "ResponseDescription",
                result.get(
                    "errorMessage",
                    "Safaricom did not accept the STK Push."
                )
            )
        )

    logger.info(
        "STK Push accepted. Account reference: %s",
        account_reference
    )

    # Return the complete response for payment processing.
    return result


# ==========================================================
# 6. QUERY STK PUSH PAYMENT STATUS
# ==========================================================

def query_stk_push(checkout_request_id):
    """
    Query the status of an STK Push transaction.

    checkout_request_id:
        CheckoutRequestID returned by initiate_stk_push().

    The returned ResultCode must be interpreted by the
    payment processing code. Do not mark an order paid
    merely because the query request was accepted.
    """

    checkout_request_id = str(
        checkout_request_id
    ).strip()

    if not checkout_request_id:
        raise MpesaError(
            "CheckoutRequestID is required."
        )

    shortcode, passkey = get_mpesa_credentials()

    access_token = get_access_token()

    password, timestamp = generate_password()

    url = (
        f"{get_mpesa_base_url()}"
        "/mpesa/stkpushquery/v1/query"
    )

    payload = {
        "BusinessShortCode": shortcode,
        "Password": password,
        "Timestamp": timestamp,
        "CheckoutRequestID": checkout_request_id,
    }

    result = _send_daraja_request(
        url,
        payload,
        access_token
    )

    if str(result.get("ResponseCode")) != "0":
        raise MpesaError(
            result.get(
                "ResponseDescription",
                "Safaricom could not process the payment query."
            )
        )

    return result
