from pymongo import MongoClient
import requests
import time
import sys
import os

TOKEN = os.getenv('TOKEN')
MONGO_URI = os.getenv('MONGO_URI')
BASE_URL = f'https://api.telegram.org/bot{TOKEN}'

# MongoDB connection
client = MongoClient(MONGO_URI)
db = client['BingoDB']
users_collection = db['users']


def debug_print(message):
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] DEBUG: {message}")


def get_updates(offset=None):
    url = f"{BASE_URL}/getUpdates"
    params = {'timeout': 30, 'offset': offset}
    try:
        response = requests.get(url, params=params, timeout=35)
        if response.status_code == 200:
            data = response.json()
            return data.get('result', [])
        return []
    except Exception as e:
        debug_print(f"Error in get_updates: {str(e)}")
        return []


def send_message(chat_id, text, reply_markup=None):
    url = f"{BASE_URL}/sendMessage"
    payload = {
        'chat_id': chat_id,
        'text': text,
        'parse_mode': 'Markdown'
    }
    if reply_markup:
        payload['reply_markup'] = reply_markup

    try:
        response = requests.post(url, json=payload, timeout=10)
        return response.json()
    except Exception as e:
        debug_print(f"Error sending message: {str(e)}")
        return None


def create_menu_keyboard():
    keyboard = [
        [{"text": "Play"}, {"text": "Deposit"}],
        [{"text": "Withdraw"}, {"text": "Check Balance"}],
        [{"text": "Invite"}, {"text": "How To Play"}],
        [{"text": "Contact Us"}, {"text": "Join Us"}]
    ]
    return {"keyboard": keyboard, "resize_keyboard": True}


def create_deposit_keyboard():
    keyboard = [
        [{"text": "Bank Of Abyssinia [+10% Bonus]"}],
        [{"text": "Telebirr [+10% Bonus]"}],
        [{"text": "Commercial Bank of Ethiopia [+10% Bonus]"}],
        [{"text": "Back to Main Menu"}]
    ]
    return {"keyboard": keyboard, "resize_keyboard": True}


def create_phone_keyboard():
    keyboard = {
        "keyboard": [
            [{"text": "Share Phone Number", "request_contact": True}]
        ],
        "resize_keyboard": True,
        "one_time_keyboard": True
    }
    return keyboard


def main_menu(chat_id):
    keyboard = create_menu_keyboard()
    send_message(chat_id, "Hello! What do you want to do?\n\nChoose from the menu below:", keyboard)


def handle_deposit(chat_id):
    keyboard = create_deposit_keyboard()
    send_message(chat_id, "Please choose payment method for deposit:", keyboard)


def create_play_inline_keyboard(username):
    keyboard = {
        "inline_keyboard": [
            [{"text": "Play Now 🎮", "url": f"https://bingo-an1t.onrender.com/?username={username}"}]
        ]
    }
    return keyboard


def register_user(chat_id, username, phone_number=None):
    user_data = {
        "chat_id": chat_id,
        "username": username,
        "status": "active",
    }
    if phone_number:
        user_data["phone_number"] = phone_number
    users_collection.update_one({"chat_id": chat_id}, {"$set": user_data}, upsert=True)


def main():
    try:
        requests.get(f"{BASE_URL}/deleteWebhook", timeout=10)
    except:
        pass

    offset = None
    user_states = {}  # Track user deposit process

    # Deposit accounts based on method
    deposit_accounts = {
        "Bank Of Abyssinia [+10% Bonus]": "171629616",
        "Telebirr [+10% Bonus]": "0940844131",
        "Commercial Bank of Ethiopia [+10% Bonus]": "1000302436267"
    }

    try:
        while True:
            updates = get_updates(offset)
            for update in updates:
                offset = update['update_id'] + 1

                if 'message' not in update:
                    continue

                chat_id = update['message']['chat']['id']
                text = update['message'].get('text', '')
                username = update['message']['from'].get('username', 'Unknown')
                user = users_collection.find_one({"chat_id": chat_id})

                # START
                if text == '/start':
                    if user:
                        main_menu(chat_id)
                    else:
                        send_message(chat_id, "Please share your phone number to get started:", create_phone_keyboard())
                    continue

                # PLAY
                if text == 'Play':
                    if user:
                        keyboard = create_play_inline_keyboard(username)
                        send_message(chat_id, "Click below to start playing Bingo! 🎉", keyboard)
                    else:
                        send_message(chat_id, "Please register first by sharing your phone number.", create_phone_keyboard())
                    continue

                # DEPOSIT
                if text == 'Deposit':
                    if not user:
                        send_message(chat_id, "Please share your phone number for deposit:", create_phone_keyboard())
                    else:
                        handle_deposit(chat_id)
                    continue

                # PHONE CONTACT
                if 'contact' in update['message']:
                    phone_number = update['message']['contact']['phone_number']
                    register_user(chat_id, username, phone_number)
                    send_message(chat_id, "Thank you! Your phone number has been registered.")
                    main_menu(chat_id)
                    continue

                # PAYMENT METHOD SELECTED
                if text in deposit_accounts.keys():
                    send_message(chat_id, f"Please send me your ACCOUNT/PHONE NUMBER for deposit.\n\n⚠️ *WARNING*: Enter only a valid number.")
                    user_states[chat_id] = {"state": "awaiting_account_number", "method": text}
                    continue

                # STEP 1: Account number
                if user_states.get(chat_id, {}).get("state") == "awaiting_account_number":
                    account_number = text
                    method = user_states[chat_id]["method"]

                    users_collection.update_one(
                        {"chat_id": chat_id},
                        {"$set": {"deposit_method": method, "account_number": account_number}},
                        upsert=True
                    )

                    # Ask for amount
                    send_message(chat_id, "How much money do you want to deposit? (Enter amount)")
                    user_states[chat_id]["state"] = "awaiting_amount"
                    continue

                # STEP 2: Amount
                if user_states.get(chat_id, {}).get("state") == "awaiting_amount":
                    amount = text
                    method = user_states[chat_id]["method"]

                    users_collection.update_one(
                        {"chat_id": chat_id},
                        {"$set": {"amount": amount}},
                        upsert=True
                    )

                    # Send deposit account number
                    send_message(chat_id,
                                 f"✅ Got it! Please deposit *{amount} ETB* to the official account:\n\n"
                                 f"*{deposit_accounts[method]}*\n\n"
                                 f"Then send the *transfer confirmation message or screenshot* here.")
                    user_states[chat_id]["state"] = "awaiting_transfer_message"
                    continue

                # STEP 3: Transfer confirmation
                if user_states.get(chat_id, {}).get("state") == "awaiting_transfer_message":
                    if "photo" in update["message"]:
                        file_id = update["message"]["photo"][-1]["file_id"]
                        users_collection.update_one(
                            {"chat_id": chat_id},
                            {"$set": {"transfer_confirmation": {"type": "photo", "file_id": file_id}}}
                        )
                        send_message(chat_id, "✅ Transfer confirmation saved. Thank you! 🎉")
                    else:
                        users_collection.update_one(
                            {"chat_id": chat_id},
                            {"$set": {"transfer_confirmation": {"type": "text", "message": text}}}
                        )
                        send_message(chat_id, "✅ Transfer confirmation saved. Thank you! 🎉")

                    user_states.pop(chat_id, None)
                    main_menu(chat_id)
                    continue

                # Back to Menu
                if text == 'Back to Main Menu':
                    main_menu(chat_id)
                    user_states.pop(chat_id, None)
                    continue

                # Other menu
                if text in ['Withdraw', 'Check Balance', 'Invite', 'How To Play', 'Contact Us', 'Join Us']:
                    send_message(chat_id, f"{text} feature is coming soon!")
                    continue

            time.sleep(1)

    except KeyboardInterrupt:
        sys.exit(0)
    except Exception as e:
        debug_print(f"Fatal error: {str(e)}")
        sys.exit(1)


if __name__ == '__main__':
    main()
