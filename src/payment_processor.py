import logging
import sys

# Configure logging to simulate a production environment
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("logs/crash.log"),
        logging.StreamHandler(sys.stdout)
    ]
)

def process_payment(user_data):
    """
    Simulates a payment process.
    BUG: It assumes 'credit_card' and 'amount' always exist.
    """
    logging.info(f"Processing payment for user: {user_data.get('username')}...")
    if 'credit_card' not in user_data:
        logging.warning("Missing credit_card")
        return False

    # THE BUG IS HERE: Direct access without checking key existence
    card = user_data['credit_card']
    amount = user_data['amount']

    if amount > 0:
        logging.info(f"Charging ${amount} to card ending in {card[-4:]}")
        return True
    else:
        logging.warning("Amount is zero, skipping.")
        return False

if __name__ == "__main__":
    # Simulating an API payload that lacks the 'credit_card' field
    incomplete_payload = {
        "username": "demo_user",
        "amount": 100
        # 'credit_card' is missing!
    }

    try:
        result = process_payment(incomplete_payload)
        if result:
            logging.info("Payment successful.")
    except Exception as e:
        logging.error(f"Critical Failure: {e}", exc_info=True)