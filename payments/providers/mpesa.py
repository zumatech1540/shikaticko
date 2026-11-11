import base64
from datetime import datetime
from decimal import Decimal, InvalidOperation
from zoneinfo import ZoneInfo

import requests

from django.conf import settings


class MpesaError(Exception):
    """Raised when a Daraja API request fails."""
    pass


def get_mpesa_base_url():
    environment = getattr(
        settings,
        "MPESA_ENVIRONMENT",
        "sandbox"
    ).lower()

    if environment == "sandbox":
        return "https://sandbox.safaricom.co.ke"

    if environment == "production":
        return "https://api.safaricom.co.ke"

    raise MpesaError(
        "Invalid M-Pesa environment configuration."
    )


def get_access_token():
    """
    Authenticate ShikaTicko with Safaricom Daraja.
    """

    consumer_key = settings.MPESA_CONSUMER_KEY
    consumer_secret = settings.MPESA_CONSUMER_SECRET

    if not consumer_key or not consumer_secret:
        raise MpesaError(
            "M-Pesa Consumer Key or Consumer Secret is missing."
        )

    url = (
        f"{get_mpesa_base_url()}"
        "/oauth/v1/generate"
    )

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
            timeout=30
        )

        response.raise_for_status()
        data = response.json()

    except requests.RequestException as error:
        raise MpesaError(
            f"Could not authenticate with Daraja: {error}"
        )

    except ValueError:
        raise MpesaError(
            "Daraja returned an invalid authentication response."
        )

    access_token = data.get("access_token")

    if not access_token:
        raise MpesaError(
            "Daraja did not return an access token."
        )

    return access_token


def normalize_mpesa_phone(phone):
    """
    Convert Kenyan phone numbers into 254XXXXXXXXX format.
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


def generate_password():
    """
    Generate the Lipa Na M-Pesa Online password.
    Uses the Store / Head Office shortcode associated
    with the Daraja passkey.
    """

    shortcode = str(
        getattr(settings, "MPESA_SHORTCODE", "")
    ).strip()

    passkey = getattr(
        settings, "MPESA_PASSKEY", ""
    )

    if not shortcode or not passkey:
        raise MpesaError(
            "M-Pesa Shortcode or Passkey is missing."
        )

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



def initiate_stk_push(
    phone,
    amount,
    account_reference,
    transaction_description="ShikaTicko Ticket"
):
    """
    Initiate an M-Pesa STK Push.

    Supports:
        1. CustomerPayBillOnline
        2. CustomerBuyGoodsOnline

    Sandbox testing normally uses the provisioned PayBill
    test configuration.

    Production Buy Goods requires the correct Safaricom-
    provisioned Store/Head Office shortcode, Till number,
    credentials and transaction permissions.

    A successful response means Safaricom accepted the
    STK request, not that payment has been completed.
    """

    # --------------------------------------------------
    # 1. NORMALIZE PHONE NUMBER
    # --------------------------------------------------
    phone = normalize_mpesa_phone(phone)

    if not phone or not phone.isdigit() or len(phone) != 12:
        raise MpesaError(
            "Invalid M-Pesa phone number. "
            "Use a valid Kenyan mobile number."
        )

    # --------------------------------------------------
    # 2. VALIDATE PAYMENT AMOUNT
    # --------------------------------------------------
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

    # --------------------------------------------------
    # 3. LOAD MPESA CONFIGURATION
    # --------------------------------------------------
    environment = str(
        getattr(settings, "MPESA_ENVIRONMENT", "sandbox")
    ).strip().lower()

    shortcode = str(
        getattr(settings, "MPESA_SHORTCODE", "")
    ).strip()

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
            "CustomerPayBillOnline"
        )
    ).strip()

    passkey = str(
        getattr(settings, "MPESA_PASSKEY", "")
    ).strip()

    # --------------------------------------------------
    # 4. VALIDATE CONFIGURATION
    # --------------------------------------------------
    if environment not in ("sandbox", "production"):
        raise MpesaError(
            "Invalid MPESA_ENVIRONMENT. "
            "Use sandbox or production."
        )

    if not shortcode or not shortcode.isdigit():
        raise MpesaError(
            "A valid M-Pesa Business Shortcode is required."
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
                "A valid M-Pesa Buy Goods Till number is required."
            )

        party_b = till_number

    else:
        # PayBill transactions use the configured shortcode.
        party_b = shortcode

    if not callback_url.startswith("https://"):
        raise MpesaError(
            "The M-Pesa callback URL must use HTTPS."
        )

    if not passkey:
        raise MpesaError(
            "M-Pesa Passkey is missing."
        )

    # --------------------------------------------------
    # 5. AUTHENTICATE WITH SAFARICOM
    # --------------------------------------------------
    try:
        access_token = get_access_token()

    except MpesaError:
        raise

    except requests.RequestException as error:
        raise MpesaError(
            f"Could not authenticate with Daraja: {error}"
        )

    if not access_token:
        raise MpesaError(
            "Safaricom did not return a valid access token."
        )

    # --------------------------------------------------
    # 6. GENERATE STK PASSWORD
    # --------------------------------------------------
    try:
        password, timestamp = generate_password()

    except Exception as error:
        raise MpesaError(
            f"Could not generate M-Pesa password: {error}"
        )

    # --------------------------------------------------
    # 7. BUILD STK PUSH REQUEST
    # --------------------------------------------------
    base_url = get_mpesa_base_url().rstrip("/")

    url = (
        f"{base_url}/mpesa/stkpush/v1/processrequest"
    )

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }

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

    # --------------------------------------------------
    # 8. SEND STK PUSH REQUEST
    # --------------------------------------------------
    try:
        response = requests.post(
            url,
            json=payload,
            headers=headers,
            timeout=(15, 45)
        )

        try:
            result = response.json()

        except ValueError:
            raise MpesaError(
                "Safaricom returned an invalid STK Push response."
            )

        if not response.ok:
            error_code = result.get(
                "errorCode",
                str(response.status_code)
            )

            error_message = result.get(
                "errorMessage",
                result.get(
                    "ResponseDescription",
                    "Safaricom rejected the STK Push request."
                )
            )

            raise MpesaError(
                f"Safaricom STK Push failed "
                f"({error_code}): {error_message}"
            )

    except requests.Timeout:
        raise MpesaError(
            "The STK Push request timed out. "
            "Check the payment status before retrying "
            "to avoid duplicate payment prompts."
        )

    except requests.ConnectionError:
        raise MpesaError(
            "Could not connect to Safaricom STK Push. "
            "Please try again later."
        )

    except requests.RequestException as error:
        raise MpesaError(
            f"Could not send STK Push request: {error}"
        )

    # --------------------------------------------------
    # 9. VALIDATE SAFARICOM RESPONSE
    # --------------------------------------------------
    if result.get("ResponseCode") != "0":
        raise MpesaError(
            result.get(
                "errorMessage",
                result.get(
                    "ResponseDescription",
                    "Safaricom did not accept the STK Push request."
                )
            )
        )

    # --------------------------------------------------
    # 10. RETURN SUCCESSFUL INITIATION RESPONSE
    # --------------------------------------------------
    return result
