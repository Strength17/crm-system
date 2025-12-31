import os
import smtplib
from email.message import EmailMessage
from dotenv import load_dotenv
load_dotenv(dotenv_path="C:/MyMVP/.env")


print("SMTP_USER:", os.getenv("SMTP_USER"))
print("SMTP_PASS:", os.getenv("SMTP_PASS")[:10], "...")


def main():
    load_dotenv()

    # Load SendGrid SMTP credentials
    host = os.getenv("SMTP_HOST", "smtp.sendgrid.net")
    port = int(os.getenv("SMTP_PORT", "587"))
    user = os.getenv("SMTP_USER", "apikey")  # SendGrid requires "apikey" as username
    password = os.getenv("SMTP_PASS")        # Your actual SendGrid API key
    from_name = os.getenv("APP_FROM_NAME", "SKY Verify")
    from_email = os.getenv("SMTP_FROM", "awapenn17@gmail.com")  # Verified sender

    # Compose email
    msg = EmailMessage()
    msg["From"] = f"{from_name} <{from_email}>"
    msg["To"] = "felingeh@gmail.com"  # Test recipient
    msg["Subject"] = "Your Confirmation Code"
    msg.set_content("This is a plain text test email from SKY Verify.")
    msg.add_alternative(
        "<p>This is a <strong>test email</strong> from SKY Verify using SendGrid SMTP.</p>",
        subtype="html"
    )

    # Send via SendGrid SMTP
    try:
        with smtplib.SMTP(host, port) as server:
            server.starttls()
            server.login(user, password)
            server.send_message(msg)
        print("✅ Test email sent successfully.")
    except Exception as e:
        print(f"❌ Failed to send email: {e}")

if __name__ == "__main__":
    main()
