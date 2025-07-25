"""Main entry point for the Telegram bot application."""

from areyouok_telegram.app import create_application

if __name__ == "__main__":
    application = create_application()
    application.run_polling()
