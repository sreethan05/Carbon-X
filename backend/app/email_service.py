from fastapi_mail import FastMail
from fastapi_mail import MessageSchema
from fastapi_mail import ConnectionConfig

import random

conf = ConnectionConfig(

    MAIL_USERNAME = "gireddyvarshithreddy@gmail.com",

    MAIL_PASSWORD = "xpfo ccpi qfkg puhb",

    MAIL_FROM = "gireddyvarshithreddyl@gmail.com",

    MAIL_PORT = 587,

    MAIL_SERVER = "smtp.gmail.com",

    MAIL_STARTTLS = True,

    MAIL_SSL_TLS = False,

    USE_CREDENTIALS = True

)

def generate_otp():

    return str(
        random.randint(
            100000,
            999999
        )
    )

async def send_email_otp(
    email,
    otp
):

    html = f"""

    <h2>CarbonSetu Email Verification</h2>

    <h1>{otp}</h1>

    """

    message = MessageSchema(

        subject = "CarbonSetu OTP",

        recipients = [email],

        body = html,

        subtype = "html"

    )

    fm = FastMail(conf)

    await fm.send_message(message)