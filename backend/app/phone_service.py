"""OTP SMS via Textplate API (https://api.textplate.in/v1/send-sms).

Flow: app generates a 6-digit OTP -> stores it in Redis (3-min TTL) ->
sends it via Textplate -> verifies against Redis on submit.
Set TEXTPLATE_API_TOKEN + TEXTPLATE_TEMPLATE_ID in backend/.env.
Without them, dev-mode fallback logs the OTP and returns dev_otp.
"""

import os
import random
import re

TEXTPLATE_URL = "https://api.textplate.in/v1/send-sms"
OTP_TTL_MINUTES = 3


def generate_otp() -> str:
    return str(random.randint(100000, 999999))


def _is_placeholder(v: str) -> bool:
    v = (v or "").strip()
    if not v:
        return True
    low = v.lower()
    return (
        low.startswith("your-")
        or "your_" in low
        or "your-textplate" in low
        or "your-twilio" in low
        or low in ("xxx", "test", "changeme")
    )


def _config() -> dict:
    token = os.getenv("TEXTPLATE_API_TOKEN", "").strip() or os.getenv("TEXTPLATE", "").strip()
    return {
        "token": token,
        "template_id": os.getenv("TEXTPLATE_TEMPLATE_ID", "").strip(),
        "expiry": os.getenv("TEXTPLATE_EXPIRY_VALUE", str(OTP_TTL_MINUTES)).strip() or str(OTP_TTL_MINUTES),
        "detail": os.getenv("TEXTPLATE_DETAIL_VALUE", "CarbonX login").strip() or "CarbonX login",
    }


def sms_configured() -> bool:
    cfg = _config()
    return not _is_placeholder(cfg["token"]) and not _is_placeholder(cfg["template_id"])


def _normalize_mobile(phone: str) -> str:
    """Textplate expects +91XXXXXXXXXX (per their API examples)."""
    digits = re.sub(r"\D", "", phone or "")
    if len(digits) > 10:
        digits = digits[-10:]
    return f"+91{digits}" if len(digits) == 10 else digits


def _twilio_configured() -> bool:
    sid = os.getenv("TWILIO_ACCOUNT_SID", "").strip()
    token = os.getenv("TWILIO_AUTH_TOKEN", "").strip()
    return not _is_placeholder(sid) and not _is_placeholder(token)


def _send_twilio_otp(phone: str, otp: str) -> tuple[bool, str]:
    try:
        from twilio.rest import Client
        sid = os.getenv("TWILIO_ACCOUNT_SID", "").strip()
        token = os.getenv("TWILIO_AUTH_TOKEN", "").strip()
        from_num = os.getenv("TWILIO_PHONE_NUMBER", "").strip()
        client = Client(sid, token)

        if not from_num or _is_placeholder(from_num):
            numbers = client.incoming_phone_numbers.list(limit=1)
            if numbers:
                from_num = numbers[0].phone_number

        if not from_num:
            return False, "No active Twilio sender phone number found on account."

        mobile = phone if phone.startswith("+") else f"+91{phone[-10:]}"
        msg = client.messages.create(
            body=f"Your CarbonX verification code is: {otp}. Valid for 3 minutes. Do not share this code.",
            from_=from_num,
            to=mobile,
        )
        print(f"[TWILIO] SMS sent to {mobile}, SID: {msg.sid}")
        return True, "OTP sent to your phone via SMS"
    except Exception as e:
        err_msg = str(e)
        if "unverified" in err_msg.lower():
            friendly_err = f"Twilio Trial: +91 {phone[-10:]} is not verified. Please add it to your Twilio Console (twilio.com/user/account/phone-numbers/verified) to receive live SMS."
        else:
            friendly_err = f"Twilio SMS failed: {err_msg[:120]}"
        print(f"[TWILIO ERROR] {friendly_err}")
        return False, friendly_err


def send_phone_otp(phone: str, otp: str) -> tuple[bool, str]:
    """
    Send OTP via configured provider (Twilio or Textplate).
    Returns (success: bool, message: str).
    """
    clean_digits = re.sub(r"\D", "", phone or "")
    if len(clean_digits) > 10:
        clean_digits = clean_digits[-10:]
    if len(clean_digits) != 10:
        return False, "Enter a valid 10-digit phone number"

    # 1. Prefer Twilio if configured in environment
    if _twilio_configured():
        return _send_twilio_otp(clean_digits, otp)

    # 2. Fall back to Textplate if configured
    if sms_configured():
        cfg = _config()
        mobile = f"+91{clean_digits}"
        print(f"[TEXTPLATE] sending mobileNumber={mobile!r}")
        try:
            import requests

            resp = requests.post(
                TEXTPLATE_URL,
                headers={"Authorization": f"Bearer {cfg['token']}"},
                files={},
                data={
                    "mobileNumber": mobile,
                    "templateId": cfg["template_id"],
                    "otpValue": str(otp),
                    "expiryValue": str(cfg["expiry"]),
                    "detailValue": str(cfg["detail"]),
                },
                timeout=15,
            )
            content_type = resp.headers.get("content-type", "").lower()
            if "text/html" in content_type or "<html" in resp.text.lower() or "imunify360" in resp.text.lower():
                print(f"[SMS ERROR] Textplate gateway blocked by bot-protection (Imunify360). SMS not sent to {mobile}.")
                return False, "Textplate gateway blocked by server firewall (Imunify360)."

            if not (200 <= resp.status_code < 300):
                print(f"[SMS ERROR] Textplate HTTP error {resp.status_code}: {resp.text[:200]}")
                return False, f"Textplate returned HTTP {resp.status_code}"

            try:
                data = resp.json()
                if isinstance(data, dict) and (data.get("status") == "error" or data.get("error")):
                    print(f"[SMS ERROR] Textplate API error: {data}")
                    return False, str(data.get("message") or "Textplate dispatch failed")
            except Exception:
                pass

            print(f"[TEXTPLATE] send to {mobile}: HTTP {resp.status_code} ok=True")
            return True, "OTP sent to your phone via SMS"
        except Exception as e:
            print(f"[SMS ERROR] Textplate send failed for {mobile}: {e}")
            return False, f"Textplate send error: {str(e)[:100]}"

    # 3. No SMS provider configured
    return False, "SMS provider not configured"


# Backwards-compat alias
twilio_ready = _twilio_configured
