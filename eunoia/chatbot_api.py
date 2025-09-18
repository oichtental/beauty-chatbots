import os
import redis
import openai
import random
import requests
import logging
import re
import urllib.parse
from flask import Flask, request, jsonify
from flask_cors import CORS
from dotenv import load_dotenv
from difflib import SequenceMatcher
from langdetect import detect, LangDetectException
from difflib import get_close_matches

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# Load environment variables
load_dotenv()

# Set API keys
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
WAXBABY_API_KEY = os.getenv("WAXBABY_API_KEY")
EUNOIA_API_KEY = os.getenv("EUNOIA_API_KEY")

# Initialize Redis databases
business_cache = redis.Redis(host="localhost", port=6379, db=3, decode_responses=True)
user_cache = redis.Redis(host="localhost", port=6379, db=4, decode_responses=True)

# Initialize Flask
app = Flask(__name__)
CORS(app)

# Constants
MEMORY_LIMIT = 5
DEFAULT_LANGUAGE = "de"

# Common responses
FALLBACK_GREETINGS = [
    "Can I help you with something else?",
    "Anything else you'd like to know?",
    "What else can I assist you with today? 😊",
    "I'm here if you need anything else!",
    "Let me know if you have any more questions!"
]

# ----- Helper Functions -----

def clean_text(text):
    """Remove special characters and convert to lowercase"""
    return re.sub(r"[^a-zA-Z0-9 ]", "", text).lower()

def is_possible_typo(word1, text, threshold=0.8):
    """Check if words are similar enough to suggest a typo"""
    return SequenceMatcher(None, word1.lower(), text.lower()).ratio() >= threshold

def find_similar_services(user_input, services):
    """Find services with similar names to user input"""
    similar = []
    for service in services:
        name = service if isinstance(service, str) else service.get("name", "")
        service_words = name.lower().split()
        for word in service_words:
            if SequenceMatcher(None, word, user_input.lower()).ratio() > 0.8:
                similar.append(name)
                break
    return similar

def switch_language(user_input):
    """Detect explicit language switch requests"""
    if "sprich deutsch" in user_input.lower():
        return "de"
    elif "speak english" in user_input.lower():
        return "en"
    return None

# Google Maps Link
def generate_google_maps_link(station_name, business_address):
    base_url = "https://www.google.com/maps/dir/"
    from_location = urllib.parse.quote_plus(f"{station_name}, Salzburg")
    to_location = urllib.parse.quote_plus(business_address)
    return f"{base_url}{from_location}/{to_location}"

# Public Transport Helper
def extract_station_name(user_input):
    user_input_lower = user_input.lower()
    station_name_keys = business_cache.keys("transport:station:name:*")
    station_names = [key.split(":")[-1] for key in station_name_keys]

    # Check whole-word matches
    for name in station_names:
        pattern = r'\b' + re.escape(name) + r'\b'
        if re.search(pattern, user_input_lower):
            return name

    # Fuzzy match only if the input is short (to avoid false positives)
    if len(user_input_lower.split()) <= 4:
        from difflib import get_close_matches
        close_matches = get_close_matches(user_input_lower, station_names, n=1, cutoff=0.85)
        if close_matches:
            return close_matches[0]

    return None

# FAQ Random Follow-ups
def get_follow_up_phrase(language):
    """Return a random follow-up phrase based on language"""
    german_phrases = [
        "Möchtest du sonst noch was wissen? 😊",
        "Womit kann ich dir sonst noch helfen?",
        "Ich bin hier, falls du noch weitere Fragen hast!",
        "Sag mir Bescheid, wenn ich dir noch helfen kann!"
    ]
    english_phrases = [
        "Is there anything else you'd like to know? 😊",
        "How else can I assist you?",
        "I'm here if you have more questions!",
        "Let me know if you need anything else!"
    ]

    return random.choice(german_phrases) if language == "de" else random.choice(english_phrases)

# ----- Redis Storage Functions -----

def store_user_interaction(user_id, message):
    """Store user interactions in Redis"""
    key = f"chat_history:{user_id}"
    user_cache.rpush(key, message)
    user_cache.ltrim(key, -MEMORY_LIMIT, -1)

def retrieve_user_context(user_id):
    """Retrieve recent chat history from Redis"""
    key = f"chat_history:{user_id}"
    return user_cache.lrange(key, 0, -1)

def get_user_language(user_id, default_language=DEFAULT_LANGUAGE):
    """Get user's preferred language"""
    return user_cache.get(f"user_language:{user_id}") or default_language

def set_user_language(user_id, language):
    """Set user's preferred language"""
    user_cache.set(f"user_language:{user_id}", language)

# ----- Business Data Functions -----

def fetch_business_data(language):
    """Fetch dynamic business information from Redis"""
    return {
        "services": business_cache.lrange("business:services", 0, -1) or [],
        "contact_info": business_cache.hgetall("business:contact_info"),
        "recommendations": business_cache.hgetall("business:recommendations"),
        "additional_info": business_cache.hgetall("business:additional_info") or {},
        "role_description": business_cache.get(f"business:role_description:{language}") or 
                           business_cache.get("business:role_description:en"),
        "promotions": business_cache.lrange("current_promotions", 0, -1) or [],
        "pricing": business_cache.get("business:pricing"),
        "opening_hours": business_cache.get("business:opening_hours"),
        "non_service_responses": business_cache.lrange("business:non_service_responses", 0, -1) or [],
        "booking": business_cache.get(f"business:booking:{language}") or business_cache.get("business:booking"),
    }

def get_promotions():
    """Format promotions data for display"""
    promotions = business_cache.lrange("current_promotions", 0, -1)
    if not promotions:
        return "There are no promotions at the moment."
    return "\n\n🎉 **Current Promotions:**\n" + "\n".join([f"- {promo}" for promo in promotions])

def get_available_languages():
    """Get list of available languages"""
    return business_cache.lrange("available_languages", 0, -1) or ["de", "en"]


# ---- Public Transport Retrieval ----
def get_transport_info(user_input, user_id):
    station_name = extract_station_name(user_input)
    language = get_user_language(user_id)

    if station_name:
        station_key_short = business_cache.get(f"transport:station:name:{station_name}")
        if station_key_short:
            station_key = f"transport:station:{station_key_short}"
            if business_cache.exists(station_key):
                station_info = business_cache.hgetall(station_key)
                lines = station_info['lines']
                name = station_info['name']
                address = station_info['address']

                # Get business address from Redis
                business_address = business_cache.hget("business:contact_info", "address")
                maps_link = generate_google_maps_link(name, business_address)

                if language == "de":
                    response = (
                        f"Wenn du vom {name} zu uns oder zurück möchtest, "
                        f"kannst du diese öffentlichen Verkehrsmittel benutzen: {lines}.\n"
                        f"Adresse {name}: {address}.\n"
                        f"Hier ist auch ein Google Maps Link für die Route: {maps_link}"
                    )
                else:
                    response = (
                        f"If you want to go from {name} to us or back, "
                        f"you can use these public transport options: {lines}.\n"
                        f"{name} address: {address}.\n"
                        f"Here’s also a Google Maps link for the route: {maps_link}"
                    )
                return response

    # If no station match → return None
    return None

# Verbesserte FAQ-Handling Funktion
def handle_faqs_improved(user_input, user_id):
    if not user_input or len(user_input.strip()) < 3:
        return None

    user_input_clean = clean_text(user_input.lower())
    logging.info(f"Checking FAQ triggers for input: '{user_input_clean}'")

    faq_triggers = business_cache.smembers("faq:triggers")
    if not faq_triggers:
        logging.warning("No FAQ triggers found in Redis")
        return None

    logging.info(f"Available FAQ triggers: {list(faq_triggers)}")

    faq_keywords = {
        'password': ['faq:reset_password', 'faq:how_to_get_new_password', 'faq:how_to_reset_password', 'faq:how_to_change_password'],
        'passwort': ['faq:reset_password', 'faq:how_to_get_new_password', 'faq:how_to_reset_password', 'faq:how_to_change_password'],
        'reset': ['faq:reset_password', 'faq:how_to_reset_password'],
        'change': ['faq:how_to_change_password'],
        'new': ['faq:how_to_get_new_password'],
        'ändern': ['faq:how_to_change_password'],
        'neu': ['faq:how_to_get_new_password'],
        'zurücksetzen': ['faq:reset_password', 'faq:how_to_reset_password']
    }

    for keyword, possible_faqs in faq_keywords.items():
        if keyword in user_input_clean:
            for faq_key in possible_faqs:
                answer = business_cache.get(faq_key)
                if answer:
                    logging.info(f"Found FAQ answer with key: {faq_key} (keyword: {keyword})")
                    return answer

    for trigger in faq_triggers:
        trigger_clean = clean_text(trigger.lower())

        if trigger_clean == user_input_clean:
            return get_faq_answer_by_trigger(trigger)

        if trigger_clean in user_input_clean or user_input_clean in trigger_clean:
            return get_faq_answer_by_trigger(trigger)

        trigger_words = set(trigger_clean.split())
        input_words = set(user_input_clean.split())

        if len(trigger_words) > 0 and len(trigger_words & input_words) / len(trigger_words) >= 0.7:
            return get_faq_answer_by_trigger(trigger)

    trigger_list = list(faq_triggers)
    if trigger_list:
        matches = get_close_matches(user_input_clean,
                                  [clean_text(t.lower()) for t in trigger_list],
                                  n=1, cutoff=0.6)

        if matches:
            best_match = matches[0]
            for trigger in trigger_list:
                if clean_text(trigger.lower()) == best_match:
                    return get_faq_answer_by_trigger(trigger)

    return None

def get_faq_answer_by_trigger(trigger):
    possible_keys = [
        f"faq:{trigger}",
        f"faq:{trigger.replace(' ', '_')}",
        f"faq:{trigger.replace(' ', '_').lower()}",
        f"faq:{trigger.lower()}",
        f"faq:{trigger.replace(' ', '')}"
    ]

    for key in possible_keys:
        answer = business_cache.get(key)
        if answer:
            logging.info(f"Found FAQ answer with key: {key}")
            return answer

    logging.warning(f"No FAQ answer found for trigger: {trigger}")
    return None

# ----- API Functions -----

def fetch_waxbaby_data():
    """Fetch data from WAXBABY API"""
    try:
        response = requests.get(
            "https://www.wax-baby.one/wp-json/eunoia-api/v1/data",
            headers={"Authorization": f"Bearer {WAXBABY_API_KEY}"},
            timeout=5,
        )
        if response.status_code == 200:
            waxbaby_data = response.json()
            contact_info_dict = {item["type"]: item["value"] for item in waxbaby_data.get("contact_info", [])}
            return {
                "services": waxbaby_data.get("services", []),
                "contact_info": contact_info_dict,
            }
    except requests.exceptions.RequestException as e:
        logging.error(f"Error fetching WAXBABY data: {e}")
    return {"services": [], "contact_info": {}}

def fetch_eunoia_data():
    """Fetch data from EUNOIA API"""
    try:
        response = requests.get(
            "https://www.eunoia-beauty.com/wp-json/eunoia-api/v1/data",
            headers={"Authorization": f"Bearer {EUNOIA_API_KEY}"},
            timeout=5,
        )
        if response.status_code == 200:
            eunoia_data = response.json()
            contact_info_dict = {item["type"]: item["value"] for item in eunoia_data.get("contact_info", [])}
            return {
                "services": eunoia_data.get("services", []),
                "contact_info": contact_info_dict,
            }
    except requests.exceptions.RequestException as e:
        logging.error(f"Error fetching EUNOIA data: {e}")
    return {"services": [], "contact_info": {}}

def fetch_waxbaby_services():
    """Fetch services from WAX! Baby API"""
    try:
        response = requests.get(
            "https://www.wax-baby.one/wp-json/waxbaby-api/v1/data",
            headers={"Authorization": f"Bearer {WAXBABY_API_KEY}"},
            timeout=5,
        )
        return response.json() if response.status_code == 200 else {"services": []}
    except requests.exceptions.RequestException as e:
        logging.error(f"Error fetching WAX! Baby data: {e}")
        return {"services": []}

# ----- OpenAI Functions -----

def translate_text(text, target_language):
    """Use OpenAI to translate text"""
    client = openai.OpenAI(api_key=OPENAI_API_KEY)
    response = client.chat.completions.create(
        model="gpt-4",
        messages=[
            {"role": "system", "content": f"Translate the following text to {target_language}. Use informal 'du' form in German."},
            {"role": "user", "content": text}
        ]
    )
    return response.choices[0].message.content.strip()

def generate_gpt_non_service_response(service_name):
    """Generate response for non-available services"""
    prompt = (
        f"Politely inform the user that EUNOIA does not offer {service_name}. "
        f"Be clear that this is an exception to their general services. "
        f"Encourage them to ask about other treatments EUNOIA does offer, in a friendly, playful tone."
        f"Recommend WAX! Baby if they offer this service and ask for help with contact data."
    )

    try:
        client = openai.OpenAI(api_key=OPENAI_API_KEY)
        response = client.chat.completions.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": "You are a friendly and playful chatbot for a beauty studio."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.9,
            max_tokens=80
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        logging.error(f"GPT fallback error: {e}")

        return f"I'm sorry, but EUNOIA does not offer {service_name}. Let me know if you want to hear about other services!"

def generate_dynamic_waxbaby_referral(service, language="en"):
    """Generate a referral to WAX! Baby for services not offered by EUNOIA"""
    prompt = (
        f"You are a friendly, warm, and playful chatbot for EUNOIA. "
        f"The user asked about '{service}', which EUNOIA does not offer. "
        f"Politely inform them of that and enthusiastically recommend WAX! Baby as the perfect place. "
        f"Offer to send their contact info if they'd like. "
        f"Respond in {language}, using informal and relaxed style — in German always use 'du'."
    )
    try:
        client = openai.OpenAI(api_key=OPENAI_API_KEY)
        response = client.chat.completions.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": f"The user asked about: {service}"}
            ],
            temperature=0.8,
            max_tokens=120
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        logging.error(f"Error generating referral response: {e}")
        return (
            f"Wir bieten {service} bei EUNOIA nicht an, aber WAX! Baby hat das! "
            f"Möchtest du ihre Kontaktdaten?"
            if language == "de" else
            f"We don't offer {service} at EUNOIA, but WAX! Baby does! "
            f"Would you like me to share their contact info?"
        )

def get_eunoia_contact_info_response(language):
    """Generate response with EUNOIA contact information directly from Redis"""
    contact_info = business_cache.hgetall("business:contact_info")

    if not contact_info:
        return (
            "Tut mir leid, ich konnte momentan keine Kontaktdaten finden. "
            "Bitte besuche unsere Website für mehr Informationen: https://www.eunoia-beauty.com"
        )

    phone = contact_info.get("phone", "nicht verfügbar")
    email = contact_info.get("email", "nicht verfügbar")
    address = contact_info.get("address", "nicht verfügbar")
    website = contact_info.get("website", "https://www.eunoia-beauty.com")

    if language == "de":
        return (
            f"Hier sind die Kontaktdaten für EUNOIA Urban Beauty:\n\n"
            f"- Webseite: {website}\n"
            f"- E-Mail: {email}\n"
            f"- Telefonnummer: {phone}\n"
            f"- Adresse: {address}\n\n"
            f"Lass mich wissen, wenn ich sonst noch behilflich sein kann!"
        )
    else:
        return (
            f"Here’s the contact information for EUNOIA Urban Beauty:\n\n"
            f"- Website: {website}\n"
            f"- Email: {email}\n"
            f"- Phone: {phone}\n"
            f"- Address: {address}\n\n"
            f"Let me know if I can help you with anything else!"
        )

def get_waxbaby_contact_info_response(language):
    """Generate response with WAX! Baby contact information directly from Redis"""
    contact_info = business_cache.hgetall("business:contact_info:waxbaby")

    if not contact_info:
        return (
            "Tut mir leid, ich konnte momentan keine Kontaktdaten finden. "
            "Bitte besuche unsere Website für mehr Informationen: https://www.wax-baby.one"
        )

    phone = contact_info.get("phone", "nicht verfügbar")
    email = contact_info.get("email", "nicht verfügbar")
    address = contact_info.get("address", "nicht verfügbar")
    website = contact_info.get("website", "https://www.eunoia-beauty.com")

    if language == "de":
        return (
            f"Hier sind die Kontaktdaten für WAX! Baby:\n\n"
            f"- Webseite: {website}\n"
            f"- E-Mail: {email}\n"
            f"- Telefonnummer: {phone}\n"
            f"- Adresse: {address}\n\n"
            f"Lass mich wissen, wenn ich sonst noch behilflich sein kann!"
        )
    else:
        return (
            f"Here’s the contact information for WAX! Baby:\n\n"
            f"- Website: {website}\n"
            f"- Email: {email}\n"
            f"- Phone: {phone}\n"
            f"- Address: {address}\n\n"
            f"Let me know if I can help you with anything else!"
        )

# ----- Main Response Generation Function -----

def generate_dynamic_response(user_input, user_id, user_language, force_language=None, skip_pending=False, skip_language_switch=False):
    """Generate dynamic response based on user input and context"""
    # Handle empty messages
    if user_input.strip() == "":
        return random.choice(FALLBACK_GREETINGS)

    # Debug logging
    logging.info(f"Processing message for user {user_id}, input: '{user_input[:30]}...' (truncated)")
    logging.info(f"Parameters: language={user_language}, force_language={force_language}, skip_pending={skip_pending}, skip_lang_switch={skip_language_switch}")

    # Load user context
    chat_history = retrieve_user_context(user_id)
    user_name = user_cache.get(f"user_name:{user_id}")
    asked_name_flag = user_cache.get(f"asked_for_name:{user_id}")
    language = force_language or user_cache.get(f"user_language:{user_id}") or user_language or DEFAULT_LANGUAGE

    # Load business data
    business_data = fetch_business_data(language)
    waxbaby_data = fetch_waxbaby_data()
    eunoia_data = fetch_eunoia_data()

    # Load non-services lists
    explicit_non_services = business_cache.lrange("business:non_services:explicit", 0, -1)
    redirect_non_services = business_cache.lrange("business:non_services:redirect", 0, -1)

    # Debug logging
    logging.info(f"Explicit non-services list: {explicit_non_services}")
    logging.info(f"Redirect non-services list: {redirect_non_services}")

    # Initialize variables
    pending = None
    intro = None

    # --- Handle name collection ---
    if not user_name and not asked_name_flag:
        user_cache.set(f"asked_for_name:{user_id}", "1")
        user_cache.set(f"pending_message:{user_id}", user_input)
        return "👋 Hey! Ich bin Noia – deine smarte Beauty-Assistentin für alle Fragen rund um EUNOIA, Beauty Treatments und Waxing Services. Wie darf ich dich nennen? 😊"

    if not user_name and asked_name_flag:
        name_input = user_input.strip()
        if re.match(r"^[A-Za-zÄÖÜäöüß]{2,}( [A-Za-zÄÖÜäöüß]{2,})?$", name_input):
            name = name_input.split()[0].capitalize()
        else:
            name = "Lieber Gast" if language == "de" else "Dear Guest"

        user_cache.set(f"user_name:{user_id}", name)
        user_cache.delete(f"asked_for_name:{user_id}")
        pending = user_cache.get(f"pending_message:{user_id}")
        user_cache.delete(f"pending_message:{user_id}")
        user_name = name

    if pending:
        user_input = pending
        user_cache.delete(f"pending_message:{user_id}")
        user_cache.set(f"skip_intro:{user_id}", "1", ex=86400)  # expires after 24h
        intro = (
            f"Schön, dich kennenzulernen, {user_name}! 😊 Lass uns direkt loslegen:\n\n"
            if language == "de"
            else f"Nice to meet you, {user_name}! 😊 Let's dive right in:\n\n"
        )

    # --- Handle Public Transport response ---
    transport_response = get_transport_info(user_input, user_id)
    if transport_response:
        return transport_response

    # --- Handle FAQ responses ---
    faq_response = handle_faqs_improved(user_input, user_id)
    if faq_response:
        logging.info(f"Found FAQ response for: {user_input[:30]}...")
        follow_up = get_follow_up_phrase(language)
        return f"{faq_response}\n\n{follow_up}"

    # --- Check for service similarity ---
    combined_services = [s if isinstance(s, str) else s.get("name", "") for s in business_data.get("services", []) + waxbaby_data.get("services", [])]
    possible_matches = find_similar_services(user_input, combined_services)

    if possible_matches and not any(clean_text(svc) == clean_text(user_input) for svc in combined_services):
        match = possible_matches[0]
        return f"Meintest du vielleicht '{match}'? 😊" if language == "de" else f"Did you mean '{match}'? 😊"

    # --- Handle explicit non-services ---
    for non_service in explicit_non_services:
        if clean_text(non_service) in clean_text(user_input):
            if non_service.lower() in ["men's intimate waxing", "intim waxing männer", "intimwaxing männer"]:
                return (
                    "Das bieten wir nur für vertraute Stammkunden an. Melde dich gerne direkt bei uns! 😊"
                    if language == "de"
                    else "We only offer that for familiar returning clients. Please contact us directly! 😊"
                )
            response_templates = business_data.get("non_service_responses", [])
            if response_templates:
                return random.choice(response_templates).format(service=non_service)
            else:
                return f"Sorry, we don't offer {non_service} at EUNOIA."

    # --- Handle redirect non-services ---
    for redirect_service in redirect_non_services:
        if clean_text(redirect_service) in clean_text(user_input):
            user_cache.set(f"context_last_offer:{user_id}", "waxbaby_contact_info")
            dynamic_referral = generate_dynamic_waxbaby_referral(redirect_service, language)
            return dynamic_referral

    # --- Handle context from previous interactions ---
    last_offer = user_cache.get(f"context_last_offer:{user_id}")

    if last_offer == "service_suggestions" and user_input.lower() in ["yes", "yes please", "sure", "please", "yeah", "ja bitte", "sicher", "bitte", "ja", "yeah"]:
        user_cache.delete(f"context_last_offer:{user_id}")
        return "Great! We offer a variety of waxing and beauty treatments at EUNOIA. Would you like me to list some options or help you with booking?"

    if last_offer == "waxbaby_contact_info" and user_input.lower() in ["yes", "ja", "ja bitte", "bitte", "sure", "please"]:
        user_cache.delete(f"context_last_offer:{user_id}")
        return get_waxbaby_contact_info_response(language)

    if last_offer == "eunoia_contact_info" and user_input.lower() in ["yes", "ja", "ja bitte", "bitte", "sure", "please"]:
        user_cache.delete(f"context_last_offer:{user_id}")
        return get_eunoia_contact_info_response(language)

    # --- Language detection and switching ---
    if not skip_language_switch and len(user_input.strip()) > 5:
        try:
            detected_lang = detect(user_input)
            logging.info(f"Detected language: {detected_lang}")
            stored_lang = get_user_language(user_id, user_language)

            # Suggest language switch if needed
            if (detected_lang in ["de", "en"] and
                stored_lang in ["de", "en"] and
                stored_lang != detected_lang and
                not user_cache.get(f"asked_language_switch:{user_id}")):

                user_cache.set(f"asked_language_switch:{user_id}", "1", ex=3600)
                return (
                    'Ich habe bemerkt, dass du auf Englisch schreibst. Möchtest du lieber auf Englisch weitermachen? 😊 Dann schreib einfach "Speak English".'
                    if detected_lang == "en"
                    else 'I noticed you\'re writing in German. Would you prefer to continue in German? 😊 In that case just type "Sprich Deutsch".'
                )
        except LangDetectException:
            logging.info("Language detection failed")

    # Check for explicit language switch request
    if not force_language and not skip_language_switch:
        new_lang = switch_language(user_input)
        if new_lang:
            original_lang = language
            set_user_language(user_id, new_lang)
            language = new_lang

            confirm_msg = (
                "Sprache auf Deutsch 🇩🇪 gewechselt."
                if new_lang == "de"
                else "Switched to English 🇬🇧. Let's continue:"
            )

            previous_message = user_cache.get(f"previous_message:{user_id}")

            if not previous_message:
                stripped_input = re.sub(
                    r"(?i)(switch to|change to|speak|talk) (english|deutsch|german)|(?i)(englisch|english|deutsch|german)( bitte| please)?",
                    "",
                    user_input
                ).strip()

                if len(stripped_input) > 3 and stripped_input not in ["please", "bitte"]:
                    processed_input = stripped_input
                else:
                    user_cache.delete(f"pending_message:{user_id}")
                    return confirm_msg
            else:
                processed_input = previous_message
                user_cache.delete(f"previous_message:{user_id}")

            # Get response in the new language
            followup_response = generate_dynamic_response(
                processed_input,
                user_id,
                new_lang,
                force_language=new_lang,
                skip_pending=True,
                skip_language_switch=True  # Prevent infinite recursion
            )

            # Return combined response with language switch confirmation
            return f"{confirm_msg}\n\n{followup_response}"

    # Store current message for potential future language switch
    if user_input.strip().lower() not in ["yes", "ja", "no", "nein"]:
        user_cache.set(f"previous_message:{user_id}", user_input)

    # --- Handle pending messages after language switch ---
    if not skip_pending:
        pending = user_cache.get(f"pending_message:{user_id}")
        if pending:
            logging.info(f"Found pending message: {pending[:30]}... (truncated)")
            user_cache.delete(f"pending_message:{user_id}")
            user_cache.set(f"skip_intro:{user_id}", "1", ex=86400)
            user_input = pending
            logging.info(f"Using pending message as input")

            reply = generate_dynamic_response(
                user_input,
                user_id,
                language,
                force_language=language,
                skip_pending=True,
                skip_language_switch=True,
            )

            intro = (
                f"Schön, dich kennenzulernen, {user_name}! 😊 Lass uns direkt loslegen:\n\n"
                if language == "de"
                else f"Nice to meet you, {user_name}! 😊 Let's dive right in:\n\n"
            )

            return f"{intro}{reply}"

    # --- Create system prompt based on language ---
    system_prompt = (
        "Du bist eine freundliche deutschsprachige Beauty-Assistentin für Waxing und Laser... "
        "Sprich den Nutzer immer auf Deutsch an. Nutze dabei eine lockere, sympathische Sprache."
        if language == "de" else
        "You are a friendly English-speaking beauty assistant for waxing and laser... "
        "Always speak to the user in English using a casual, helpful tone."
    )

    # --- Check skip_intro status ---
    skip_intro = user_cache.get(f"skip_intro:{user_id}")
    if skip_intro:
        user_cache.expire(f"skip_intro:{user_id}", 86400)  # Refresh TTL (24h)
        logging.info("Skip intro flag is active")

    # --- Format promotions and build system message ---
    promotions_text = (
        "\n".join(business_data.get("promotions", []))
        if business_data.get("promotions")
        else "No current promotions."
    )

    # Build complete system message
    eunoia_contact_info = eunoia_data.get('contact_info', {})
    waxbaby_contact_info = waxbaby_data.get('contact_info', {})
    system_message = f"""
    {business_data['role_description']}

    You have access to the following data:

    === EUNOIA - Your Primary Reference ===
    (Only refer to this data unless the user asks for services not offered by EUNOIA.)
    Services: {business_data.get('services', 'No services available.')}
    Opening Hours: {business_data.get('opening_hours', 'Not available.')}
    Booking Info: {business_data.get('booking', 'Booking info not available.')}
    Contact Info (phone, email, address): {business_data.get('contact_info', 'No contact info available.')}
    Pricing Page: {business_data.get('pricing', 'N/A')}
    Current Promotions: {promotions_text}
    Additional Information: {business_data.get('additional_info', {}).get('payment_options', 'No payment info available.')}
    Other Helpful Info: {business_data.get('additional_info', {}).get('other_info', 'No additional details available.')}
    Parking Information: {business_data.get('additional_info', {}).get('parking', 'No parking info available.')}
    Gift Cards: {business_data.get('additional_info', {}).get('gift_cards', 'No gift card info available.')}

    === WAX! Baby  -  Only Mention if User Asks for Services EUNOIA Does Not Offer ===
    Services: {waxbaby_data.get('services', 'No services available.')}
    Contact Info: {waxbaby_data.get('contact_info', 'No contact info available.')}
    Website: {waxbaby_contact_info.get('website', 'https://www.wax-baby.one')}
    Booking Page: {waxbaby_contact_info.get('booking', 'https://www.wax-baby.one/')}

    === Important Instructions for the AI ===
    - Never mix contact info between EUNOIA and WAX! Baby.
    - Always respond in {'German' if language == 'de' else 'English'} unless the user explicitly asks otherwise.
    """

    language_instructions = (
        "- Immer in Deutsch antworten, solange der Nutzer nicht explizit Englisch verlangt.\n"
        "- Verwende niemals Englisch automatisch. Bleibe bei Deutsch.\n"
        "- Für deutsche Antworten verwende das informelle 'Du' statt 'Sie'. Halte den Ton freundlich, verspielt und persönlich."
        if language == "de" else
        "- Always respond in English unless the user explicitly asks otherwise.\n"
        "- Do not use German unless requested.\n"
        "- Keep your tone friendly, playful, and personal."
    )

    system_message += f"""
    {language_instructions}
    - Only recommend WAX! Baby when the user requests services that EUNOIA does not offer.
    - If the question cannot be answered, suggest searching on Google.
    - Be friendly, playful, and proactive, and promote current offers if relevant.
    - If you recommend EUNOIA for a service the user asked about, set context to offer EUNOIA contact info on the next user confirmation.

    - Wenn es um Terminbuchung geht:
    - Gib die Optionen nur informativ an (Telefon, E-Mail, Website).
    - Sag niemals „Welche Methode bevorzugst du?" oder „Wie möchtest du buchen?"
    - Erwecke niemals den Eindruck, dass die KI den Termin für die Person buchen kann.
    """

    # --- Prepare conversation history ---
    messages = [{"role": "system", "content": system_message}]
    for msg in chat_history:
        messages.append({"role": "user", "content": msg})
    messages.append({"role": "user", "content": user_input})

    # Store this interaction
    store_user_interaction(user_id, user_input)

    # --- Generate OpenAI response ---
    try:
        client = openai.OpenAI(api_key=OPENAI_API_KEY)
        response = client.chat.completions.create(model="gpt-4", messages=messages)
        gpt_response = response.choices[0].message.content.strip()
    except Exception as e:
        logging.error(f"Error generating OpenAI response: {e}")
        return "I'm sorry, I'm having trouble connecting right now. Please try again in a moment."

    # --- Personalize response with user's name ---
    if user_name:
        if language == "de":
            if any(word in gpt_response.lower() for word in ["danke", "super", "klar"]):
                gpt_response = gpt_response.replace("Danke", f"Danke dir, {user_name}")
        else:
            if any(word in gpt_response.lower() for word in ["thank", "sure", "great"]):
                gpt_response = gpt_response.replace("Thanks", f"Thanks, {user_name}")

    # Randomly use name for variety
    if user_name and random.random() < 0.3:  # 30% chance to add the name
        if language == "de":
            gpt_response = re.sub(r"(^|\n)([A-ZÄÖÜ])", f"\\1{user_name}, \\2", gpt_response, count=1)
        else:
            gpt_response = re.sub(r"(^|\n)([A-Z])", f"\\1{user_name}, \\2", gpt_response, count=1)

    # --- Set context for EUNOIA referrals ---
    if "eunoia" in gpt_response.lower() or "recommend" in gpt_response.lower():
        user_cache.set(f"context_last_offer:{user_id}", "eunoia_contact_info")

    # --- Post-process response ---
    if language == "de":
        gpt_response = gpt_response.replace(
            "Welche Methode bevorzugst du?",
            "Am besten buchst du über eine der folgenden Möglichkeiten:"
        )
        gpt_response = gpt_response.replace(
            "Wie möchtest du buchen?",
            "Du kannst selbst entscheiden, wie du buchen möchtest – hier sind deine Optionen:"
        )
        gpt_response = gpt_response.replace(
            "Ich kann dir bei der Buchung helfen",
            "Ich kann dir Infos geben, aber die Buchung musst du selbst durchführen"
        )
    if intro:
        gpt_response = f"{intro}{gpt_response}"

    if skip_intro:
        gpt_response = re.sub(rf"(?i)^{user_name},?\s*(Hallo|Hi|Hey)[\s,!:-]*", "", gpt_response)
        gpt_response = re.sub(r"(?i)^(Hallo|Hi|Hey)[\s,!:-]*", "", gpt_response)

    # Strip redundant greetings like "Hallo!" or "Hello!" in first sentence
    logging.info(f"Before stripping greeting: {gpt_response}")
    if language == "de":
        gpt_response = re.sub(rf"{user_name},?\s*Hallo!?[\s,:-]*", "", gpt_response, flags=re.IGNORECASE)
        gpt_response = re.sub(r"(^|\n)\s*Hallo!?[\s,:-]*", r"\1", gpt_response, flags=re.IGNORECASE)
    else:
        gpt_response = re.sub(rf"{user_name},?\s*(Hello|Hi|Hey)[\s,!:-]*", "", gpt_response, flags=re.IGNORECASE)
        gpt_response = re.sub(r"(^|\n)\s*(Hello|Hi|Hey)[\s,!:-]*", r"\1", gpt_response, flags=re.IGNORECASE)
    logging.info(f"After stripping greeting: {gpt_response}")

    return gpt_response

# Flask routes
@app.route("/", methods=["GET"])
def index():
    return jsonify({
        "status": "active",
        "chatbot": "EUNOIA Beauty Assistant",
        "endpoints": {
            "chat": "/chat (POST)",
            "health": "/health (GET)",
            "faq": "/faq (GET)"
        }
    })

@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "healthy", "service": "EUNOIA Chatbot"})

@app.route("/chat", methods=["POST"])
def chat():
    data = request.json
    user_message = data.get("message", "")
    user_id = data.get("user_id", "guest")
    user_language = data.get('language', 'de')

    # Generate chatbot response
    response_text = generate_dynamic_response(user_message, user_id, user_language)

    logging.info(f"Received message from user '{user_id}' in language '{user_language}': '{user_message}'")

    return jsonify({"response": response_text})

# Run Flask app
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)
