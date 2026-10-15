
import os
import re
import csv
import json
import html
import logging
import base64
import time
import requests
from dotenv import load_dotenv

# CONFIGURATION
load_dotenv()

GOOGLE_TRANSLATE_API_KEY = os.getenv("GOOGLE_TRANSLATE_API_KEY")

API_URL = (
    "https://inmobiliariotu360.bancolombia.com/"
    "_v/segment/graphql/v1"
)

OUTPUT_FILE = "./csv_files/property_details.csv"
BATCH_SIZE = 35

BASE_URL = (
    "https://inmobiliariotu360.bancolombia.com"
)

os.makedirs(
    os.path.dirname(OUTPUT_FILE),
    exist_ok=True
)

os.makedirs("./scraper_logs", exist_ok=True)

logging.basicConfig(
    filename="./scraper_logs/TU360details.log",
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

logger = logging.getLogger(__name__)

logger.info("=" * 70)
logger.info("TU360 commercial unit scraper started")
logger.info("Output file: %s", OUTPUT_FILE)
logger.info("Batch size: %s", BATCH_SIZE)
logger.info(
    "Google Translate API key configured: %s",
    bool(GOOGLE_TRANSLATE_API_KEY)
)


# TRANSLATION

TRANSLATE_URL = "https://translate-pa.googleapis.com/v1/translateHtml"

_translation_cache = {}


def translate_text(text, source="es", target="en"):

    if not text or not isinstance(text, str):
        logger.debug(
            "Translation skipped: input is empty or not a string. Type=%s",
            type(text).__name__,
        )
        return text

    text = text.strip()

    if not text:
        logger.debug("Translation skipped: input contains only whitespace.")
        return text

    # Avoid translating the same text multiple times
    cache_key = (text, source, target)

    if cache_key in _translation_cache:
        logger.debug("Translation cache hit.")
        return _translation_cache[cache_key]

    if not GOOGLE_TRANSLATE_API_KEY:
        logger.error("Translation failed: API key is missing.")
        raise ValueError(
            "GOOGLE_TRANSLATE_API_KEY is missing from .env"
        )

    headers = {
        "Content-Type": "application/json+protobuf",
        "x-goog-api-key": GOOGLE_TRANSLATE_API_KEY,
    }

    # Request format observed in Chrome DevTools
    payload = [
        [[text], source, target],
        "te_lib"
    ]

    # Retry temporary request failures up to 3 times
    for attempt in range(3):
        try:
            logger.debug(
                "Translation request started: source=%s, target=%s, attempt=%s/3",
                source, target, attempt + 1,
            )

            response = requests.post(
                TRANSLATE_URL,
                headers=headers,
                json=payload,
                timeout=20,
            )

            logger.debug(
                "Translation HTTP status: %s",
                response.status_code
            )

            response.raise_for_status()
            result = response.json()
            break

        except requests.RequestException as error:

            if attempt < 2:
                wait_seconds = 2 * (attempt + 1)

                logger.warning(
                    "Translation attempt %s failed. Retrying in %s seconds: %s",
                    attempt + 1,
                    wait_seconds,
                    error,
                )

                time.sleep(wait_seconds)

            else:
                logger.error(
                    "Translation failed after 3 attempts. Using original text: %s",
                    error,
                )

                return text

    # Extract the translated text
    if not result or not result[0]:
        logger.warning(
            "Google returned an empty translation. Using original text."
        )

        return text

    translated = result[0][0]

    # Some responses may contain multiple text segments
    if isinstance(translated, list):
        translated = "".join(
            str(part) for part in translated
        )

    if not isinstance(translated, str):
        logger.warning(
            "Unexpected translation format. Using original text."
        )

        return text

    _translation_cache[cache_key] = translated

    logger.debug("Translation successful.")

    return translated


# AMENITY FIELDS

INTERIOR_FIELDS = [
    "Alarma contra incendio",
    "Aire acondicionado",
    "Balcón",
    "Baño Social",
    "Citófono",
    "Cocina",
    "Cuarto de servicio",
    "Cuarto útil",
    "Estudio /Oficina",
    "Gas",
    "Terraza",
    "Zona de lavandería",
    "Amoblado",
]

EXTERIOR_FIELDS = [
    "Ascensor",
    "Cancha de fútbol",
    "Cancha múltiple",
    "Coworking",
    "Escalera de emergencia",
    "Gimnasio",
    "Parque infantil",
    "Parqueadero visitantes",
    "Piscina",
    "Portería 24/7",
    "Salón de juegos",
    "Salón social",
    "Sauna",
    "Senderos ecológicos",
    "Turco",
    "Vigilancia",
    "Zona de mascotas",
    "Zonas comunes en general",
]


# API REQUEST

def get_properties(from_value, to_value):

    logger.info(
        "Fetching API batch: from=%s, to=%s",
        from_value,
        to_value,
    )

    variables = {
        "skusFilter": "ALL",
        "simulationBehavior": "default",
        "installmentCriteria": "MAX_WITHOUT_INTEREST",
        "productOriginVtex": False,
        "map": "category-1,ciudad",
        "query": "venta/medellin",
        "orderBy": "OrderByTopSaleDESC",
        "from": from_value,
        "to": to_value,
        "selectedFacets": [
            {"key": "category-1", "value": "venta"},
            {"key": "ciudad", "value": "medellin"},
        ],
        "operator": "and",
        "fuzzy": "0",
        "searchState": None,
        "facetsBehavior": "Static",
        "categoryTreeBehavior": "default",
        "withFacets": False,
    }

    variables_base64 = base64.b64encode(
        json.dumps(variables).encode("utf-8")
    ).decode("utf-8")

    params = {
        "workspace": "master",
        "maxAge": "short",
        "appsEtag": "remove",
        "domain": "store",
        "locale": "es-CO",
        "__bindingId": "f91c6084-ca4b-4afa-9b2d-7d09efca9e7c",
        "operationName": "productSearchV3",
        "variables": "{}",
        "extensions": json.dumps({
            "persistedQuery": {
                "version": 1,
                "sha256Hash": (
                    "a96c5ed03ef513568c34b63a4bf8da055"
                    "ea6296293ee02eadb56e2e895eaffbc"
                ),
                "sender": "vtex.store-resources@0.x",
                "provider": "vtex.search-graphql@0.x",
            },
            "variables": variables_base64,
        }),
    }

    try:
        response = requests.get(
            API_URL,
            params=params,
            timeout=30,
        )

        logger.info(
            "API HTTP status: %s",
            response.status_code
        )

        response.raise_for_status()
        data = response.json()

    except requests.RequestException:
        logger.exception(
            "API request failed for batch %s-%s",
            from_value,
            to_value,
        )
        raise

    except ValueError:
        logger.exception(
            "API returned invalid JSON for batch %s-%s",
            from_value,
            to_value,
        )
        raise

    if data.get("errors"):
        logger.error(
            "TU360 API returned GraphQL errors: %s",
            data["errors"],
        )

        raise RuntimeError(
            f"TU360 API returned errors: {data['errors']}"
        )

    try:
        product_search = data["data"]["productSearch"]
        products = product_search["products"]
        total_records = product_search["recordsFiltered"]

    except (KeyError, TypeError):
        logger.exception(
            "Unexpected API response structure for batch %s-%s",
            from_value,
            to_value,
        )
        raise

    logger.info(
        "API batch successful: received=%s, total_records=%s",
        len(products),
        total_records,
    )

    if not products:
        logger.warning(
            "No products returned for batch %s-%s",
            from_value,
            to_value,
        )

    return products, total_records


# SPECIFICATIONS

def get_specifications(property_data):

    specifications = {}

    for item in property_data.get("properties", []):
        name = item.get("name")
        values = item.get("values", [])

        if name:
            specifications[name] = values

    logger.debug(
        "Specifications extracted: product_id=%s, fields=%s",
        property_data.get("productId"),
        list(specifications.keys()),
    )

    return specifications


def get_specification_value(specifications, name):

    value = specifications.get(name)

    if isinstance(value, list):
        return value[0] if value else None

    return value


def get_specification_int(specifications, name):

    value = get_specification_value(
        specifications,
        name
    )

    if value is None or value == "":
        return None
    
    # Handle values such as "5+".
    value = str(value).strip()

    if value.endswith("+"):
        value = value[:-1].strip()

    try:
        return int(float(str(value).strip()))

    except (ValueError, TypeError):
        logger.debug(
            "Could not convert specification to integer: field=%s, value=%s",
            name,
            value,
        )
        return None


def get_flagged_items(specifications, fields):

    items = []

    for field in fields:
        value = get_specification_value(
            specifications,
            field
        )

        if (
            isinstance(value, str)
            and value.strip().upper() == "SI"
        ):
            items.append(translate_text(field))

    return items


def get_interior_details(specifications):

    return json.dumps(
        {
            "Interior": get_flagged_items(
                specifications,
                INTERIOR_FIELDS
            )
        },
        ensure_ascii=False
    )


def get_exterior_details(specifications):

    return json.dumps(
        {
            "Exterior": get_flagged_items(
                specifications,
                EXTERIOR_FIELDS
            )
        },
        ensure_ascii=False
    )


# IMAGES AND PRICES

def get_images(property_data):
    """Return all unique image URLs from every item in the property."""

    images = []

    for item in property_data.get("items", []):

        for image in item.get("images", []) or []:

            if isinstance(image, dict):
                image_url = image.get("imageUrl")

            elif isinstance(image, str):
                image_url = image

            else:
                image_url = None

            if image_url:
                images.append(image_url)

    unique_images = list(dict.fromkeys(images))

    logger.debug(
        "Property images extracted: product_id=%s, count=%s",
        property_data.get("productId"),
        len(unique_images),
    )

    return unique_images


def get_main_project_images(property_data):
    """Return images attached directly to the parent project, if supplied."""

    images = []

    for image in property_data.get("images", []) or []:

        if isinstance(image, dict):
            image_url = image.get("imageUrl")

        elif isinstance(image, str):
            image_url = image

        else:
            image_url = None

        if image_url:
            images.append(image_url)

    unique_images = list(dict.fromkeys(images))

    logger.debug(
        "Main project images extracted: product_id=%s, count=%s",
        property_data.get("productId"),
        len(unique_images),
    )

    return unique_images


def get_prices(property_data):

    prices = []

    for item in property_data.get("items", []):

        for seller in item.get("sellers", []):

            offer = seller.get("commertialOffer", {})
            price = offer.get("Price")

            if price is not None:
                prices.append(price)

    unique_prices = list(dict.fromkeys(prices))

    logger.debug(
        "Prices extracted: product_id=%s, prices=%s",
        property_data.get("productId"),
        unique_prices,
    )

    return unique_prices


# PROJECT CONFIGURATIONS

def get_item_variations(item):
    """Turn one item's variation list into an easy-to-read dictionary."""

    variations = {}

    for variation in item.get("variations", []):

        name = variation.get("name", "").strip()
        values = variation.get("values", [])

        if name and values:
            variations[name] = ", ".join(
                str(value).strip()
                for value in values
                if value is not None
            )

    return variations


def get_variation_value(variations, *field_names):
    """Find a variation by name without worrying about capital letters."""

    normalized = {
        name.strip().casefold(): value
        for name, value in variations.items()
    }

    for field_name in field_names:

        value = normalized.get(
            field_name.strip().casefold()
        )

        if value is not None and str(value).strip():
            return str(value).strip()

    return None


def parse_number(value):
    """Convert values like '43,7' or '48' to a number."""

    if value is None:
        return None

    value = str(value).strip().replace(",", ".")

    if not value:
        return None

    # Only read the first number; range fields are not exact area fields.
    match = re.search(
        r"-?\d+(?:\.\d+)?",
        value
    )

    if not match:
        return None

    try:
        return float(match.group())

    except (ValueError, TypeError):
        return None


def get_item_price(item):
    """Get the lowest valid price listed for this specific configuration."""

    prices = []

    for seller in item.get("sellers", []):

        offer = seller.get("commertialOffer", {})
        price = parse_number(offer.get("Price"))

        if price is not None and price > 0:
            prices.append(price)

    item_price = min(prices) if prices else None

    logger.debug(
        "Item price extracted: item_id=%s, price=%s",
        item.get("itemId"),
        item_price,
    )

    return item_price


def get_project_configurations(property_data):
    """Read each apartment type from the project's items list."""

    configurations = []

    logger.info(
        "Extracting project configurations: product_id=%s, items=%s",
        property_data.get("productId"),
        len(property_data.get("items", [])),
    )

    for item in property_data.get("items", []):

        variations = get_item_variations(item)

        item_name = (
            item.get("nameComplete")
            or item.get("name")
            or item.get("itemId")
            or "Unnamed configuration"
        )

        built_area_m2 = parse_number(
            get_variation_value(
                variations,
                "Área Construida",
                "Area Construida",
                "Área",
                "Area"
            )
        )

        private_area_m2 = parse_number(
            get_variation_value(
                variations,
                "Área Privada",
                "Area Privada"
            )
        )

        bedrooms = parse_number(
            get_variation_value(
                variations,
                "Habitaciones",
                "Alcobas",
                "Dormitorios"
            )
        )

        bathrooms = parse_number(
            get_variation_value(
                variations,
                "Baños",
                "Banos"
            )
        )

        parking_spaces = parse_number(
            get_variation_value(
                variations,
                "Parqueaderos",
                "Parqueadero"
            )
        )

        configuration_type = get_variation_value(
            variations,
            "Tipos de Inmueble",
            "Tipo de Inmueble",
            "Tipo"
        )

        item_images = []

        for image in item.get("images", []) or []:

            if isinstance(image, dict):
                image_url = image.get("imageUrl")

            elif isinstance(image, str):
                image_url = image

            else:
                image_url = None

            if image_url:
                item_images.append(image_url)

        item_images = list(dict.fromkeys(item_images))

        configurations.append({
            "item_id": item.get("itemId"),
            "item_name": item_name,
            "configuration_type": configuration_type,
            "variations": variations,
            "images": item_images,
            "built_area_m2": built_area_m2,
            "private_area_m2": private_area_m2,
            "built_area_sq_ft": convert_m2_to_sqft(built_area_m2),
            "private_area_sq_ft": convert_m2_to_sqft(private_area_m2),
            "bedrooms": bedrooms,
            "bathrooms": bathrooms,
            "parking_spaces": parking_spaces,
            "price_cop": get_item_price(item),
        })

        logger.info(
            "Project item extracted: item_id=%s, name=%s, "
            "built_area_m2=%s, private_area_m2=%s, "
            "bedrooms=%s, bathrooms=%s, price_cop=%s, images=%s",
            item.get("itemId"),
            item_name,
            built_area_m2,
            private_area_m2,
            bedrooms,
            bathrooms,
            configurations[-1]["price_cop"],
            len(item_images),
        )

        if built_area_m2 is None:
            logger.warning(
                "Project item has no built area: product_id=%s, "
                "item_id=%s, variations=%s",
                property_data.get("productId"),
                item.get("itemId"),
                variations,
            )

        if configurations[-1]["price_cop"] is None:
            logger.warning(
                "Project item has no valid price: product_id=%s, item_id=%s",
                property_data.get("productId"),
                item.get("itemId"),
            )

    logger.info(
        "Project configurations completed: product_id=%s, count=%s",
        property_data.get("productId"),
        len(configurations),
    )

    return configurations


def get_commercial_units(configurations, cop_usd_rate):
    """
    Store the different project configurations in the commercial_units field.

    The field name is kept to match the existing database schema.
    These entries can represent residential apartment configurations too.
    """

    commercial_units = []

    # A single item does not need a configuration array.
    if len(configurations) <= 1:
        logger.info(
            "Commercial units not created: configuration count=%s",
            len(configurations),
        )
        return None

    for config in configurations:

        # Use the configuration type when available.
        # Otherwise, use the item name.
        unit_type = (
            config.get("configuration_type")
            or config.get("item_name")
        )

        if unit_type:
            unit_type = translate_text(str(unit_type))

        # Convert the configuration's price to USD.
        price_usd = convert_price_to_usd(
            config.get("price_cop"),
            cop_usd_rate
        )

        unit = {
            "sq ft built": (
                str(config["built_area_sq_ft"])
                if config.get("built_area_sq_ft") is not None
                else None
            ),
            "private sq ft": (
                str(config["private_area_sq_ft"])
                if config.get("private_area_sq_ft") is not None
                else None
            ),
            "Property type": unit_type,
            "Room /Amb": (
                str(int(config["bedrooms"]))
                if config.get("bedrooms") is not None
                else None
            ),
            "Bathrooms": (
                str(int(config["bathrooms"]))
                if config.get("bathrooms") is not None
                else None
            ),
            "Price": (
                str(price_usd)
                if price_usd is not None
                else None
            ),
        }

        commercial_units.append(unit)

    logger.info(
        "Commercial units created: count=%s",
        len(commercial_units),
    )

    return commercial_units if commercial_units else None


def format_number(value, decimals=2):
    """Make numbers readable in the property details text."""

    if value is None:
        return "Not available"

    return f"{value:,.{decimals}f}".rstrip("0").rstrip(".")


def append_project_details(
    property_details_list,
    configurations,
    cop_usd_rate
):
    """Add apartment types to the existing property_details list."""

    # These are the variation names already shown in the main details below.
    standard_fields = {
        "tipos de inmueble",
        "tipo de inmueble",
        "tipo",
        "área construida",
        "area construida",
        "área",
        "area",
        "área privada",
        "area privada",
        "habitaciones",
        "alcobas",
        "dormitorios",
        "baños",
        "banos",
        "parqueaderos",
        "parqueadero",
    }

    for config in configurations:

        label = (
            config["configuration_type"]
            or config["item_name"]
        )

        if (
            config["item_name"]
            and config["item_name"] != label
        ):
            label = f"{label} - {config['item_name']}"

        details = [
            f"Item ID: {config['item_id'] or 'Not available'}",
            (
                f"Built area: "
                f"{format_number(config['built_area_m2'])} m²"
            ),
            (
                f"Private area: "
                f"{format_number(config['private_area_m2'])} m²"
            ),
            (
                f"Built area: "
                f"{format_number(config['built_area_sq_ft'])} sq ft"
            ),
            (
                f"Private area: "
                f"{format_number(config['private_area_sq_ft'])} sq ft"
            ),
            (
                f"Bedrooms: "
                f"{format_number(config['bedrooms'], 0)}"
            ),
            (
                f"Bathrooms: "
                f"{format_number(config['bathrooms'], 0)}"
            ),
            (
                f"Parking spaces: "
                f"{format_number(config['parking_spaces'], 0)}"
            ),
            (
                f"Price (COP): "
                f"{format_number(config['price_cop'], 0)}"
            ),
        ]

        if (
            config["price_cop"] is not None
            and cop_usd_rate
        ):
            details.append(
                f"Price (USD): "
                f"{format_number(config['price_cop'] * cop_usd_rate)}"
            )

        # Keep every other variation too, including SI/NO amenity values.
        for field_name, field_value in config["variations"].items():

            if field_name.strip().casefold() in standard_fields:
                continue

            if field_value:
                details.append(
                    f"{field_name}: {field_value}"
                )

        property_details_list.append({
            "label": str(label),
            "value": "; ".join(details),
        })

        # Keep images in the same property_details key-value structure.
        if config.get("images"):
            property_details_list.append({
                "label": f"{label} Images",
                "value": config["images"],
            })

    logger.info(
        "Project details appended: configurations=%s, detail_entries=%s",
        len(configurations),
        len(property_details_list),
    )


# CURRENCY CONVERSION

def get_cop_usd_rate():

    logger.info("Fetching USD/COP exchange rate.")

    try:
        response = requests.get(
            "https://api.frankfurter.dev/v2/rates?base=usd",
            timeout=15,
        )

        logger.info(
            "Exchange-rate API HTTP status: %s",
            response.status_code,
        )

        response.raise_for_status()
        data = response.json()

    except requests.RequestException:
        logger.exception("Failed to retrieve USD/COP exchange rate.")
        raise

    except ValueError:
        logger.exception("Exchange-rate API returned invalid JSON.")
        raise

    rate_data = next(
        (
            item for item in data
            if item["quote"] == "COP"
        ),
        None
    )

    if not rate_data or not rate_data.get("rate"):
        logger.error("USD/COP exchange rate was not found in the response.")

        raise ValueError(
            "Could not retrieve the USD to COP exchange rate."
        )

    usd_cop_rate = float(rate_data["rate"])
    cop_usd_rate = 1 / usd_cop_rate

    logger.info(
        "Exchange rate loaded: USD/COP=%s, COP/USD=%s, date=%s",
        usd_cop_rate,
        cop_usd_rate,
        rate_data["date"],
    )

    print(
        f"USD to COP rate: {usd_cop_rate} "
        f"(date: {rate_data['date']})"
    )

    return cop_usd_rate


def convert_price_to_usd(price, cop_usd_rate):

    if price is None:
        return None

    if isinstance(price, list):
        return [
            round(float(item) * cop_usd_rate, 3)
            if item is not None else None
            for item in price
        ]

    try:
        return round(
            float(price) * cop_usd_rate,
            3
        )

    except (ValueError, TypeError):
        return None

# AREA

def get_area(description=None, specifications=None):

    # 1. Try extracting the exact area from API specifications first.
    if specifications:
        preferred_fields = [
            "Área Construida",
            "Área Privada",
            "Área",
        ]

        for preferred_field in preferred_fields:
            for field_name, values in specifications.items():

                if field_name.strip().lower() != preferred_field.lower():
                    continue

                # Get the first value if values is a list.
                if isinstance(values, list):
                    values = values[0] if values else None

                # Handle API values that are dictionaries.
                if isinstance(values, dict):
                    values = values.get("name")

                if values is None:
                    continue

                try:
                    area_m2 = float(
                        str(values).strip().replace(",", ".")
                    )

                    if area_m2 > 0:
                        return area_m2

                except (ValueError, TypeError):
                    continue

    # 2. Try extracting the exact area from the description.
    if description:
        patterns = [
            r'área\s+construida\s*:?\s*(\d+(?:[.,]\d+)?)\s*m\s*(?:²|2)(?!\w)',
            r'área\s+privada\s*:?\s*(\d+(?:[.,]\d+)?)\s*m\s*(?:²|2)(?!\w)',
            r'\bárea\s*:?\s*(\d+(?:[.,]\d+)?)\s*m\s*(?:²|2)(?!\w)',
            r'\b(?:con\s+)?[áa]rea\s+(?:de\s+)?(\d+(?:[.,]\d+)?)\s*m\s*(?:²|2)(?!\w)',
            r'(\d+(?:[.,]\d+)?)\s*m\s*(?:²|2)(?!\w)',
            r'(\d+(?:[.,]\d+)?)\s*metros?\s*cuadrados?\b',
        ]

        for pattern in patterns:
            match = re.search(pattern, description, re.IGNORECASE)

            if match:
                try:
                    area_m2 = float(
                        match.group(1).replace(",", ".")
                    )

                    if area_m2 > 0:
                        return area_m2

                except (ValueError, TypeError):
                    continue

    # 3. If exact area is unavailable, use the higher value
    #    from the API's constructed-area range.
    if specifications:
        for field_name, values in specifications.items():

            if field_name.strip().lower() != "rango área construida":
                # print(field_name)
                continue
            
            # Get the first value if values is a list.
            if isinstance(values, list):
                values = values[0] if values else None
                # print(values)

            if values is None:
                continue

            # Extract both numbers from a range such as "101m2 - 200m2".
            values = re.sub(r'm\s*[²2]', '', str(values), flags=re.IGNORECASE)

            numbers = re.findall(r'\d+(?:[.,]\d+)?', values)
            # print(numbers)

            if len(numbers) >= 2:
                try:
                    lower_area = float(numbers[0].replace(",", "."))
                    higher_area = float(numbers[1].replace(",", "."))

                    if lower_area >= 0 and higher_area >= lower_area:
                        return higher_area

                except (ValueError, TypeError):
                    continue

    logger.warning(
        "Area not found: description_available=%s, specification_fields=%s",
        bool(description),
        list(specifications.keys()) if specifications else [],
    )

    return None


def convert_m2_to_sqft(area_m2):

    if area_m2 is None:
        return None

    return round(area_m2 * 10.7639, 2)


# PROPERTY TYPE

def get_property_type(property_data):

    link = property_data.get("link", "").lower()

    # Check project URLs first, before trying to identify an apartment or house.
    if (
        "proyecto-de-vivienda" in link
        or "proyectos-de-vivienda" in link
        or "proyectos-vivienda" in link
    ):
        return "Project"

    match = re.search(
        r"/([^/]+)-en-venta-en-",
        link
    )

    if match:
        return match.group(1).replace("-", " ").title()

    logger.warning(
        "Could not identify property type from URL: product_id=%s, link=%s",
        property_data.get("productId"),
        link,
    )

    return None


def get_type(property_data):

    for category in property_data.get("categories", []):

        parts = category.strip("/").split("/")

        if parts:
            return parts[0]

    logger.warning(
        "Property category type not found: product_id=%s",
        property_data.get("productId"),
    )

    return None


# ADMINISTRATION PRICE

def parse_cop_amount(value):

    if value is None:
        return None

    value = str(value).strip()

    # Colombian format: 1.200.000 or 1.200,50.
    # Assumes periods are thousands separators and commas are decimal separators.
    value = value.replace(".", "").replace(",", ".")

    try:
        return float(value)

    except ValueError:
        return None


def get_admin_price(description, specifications):

    fields = [
        "Valor administración",
        "Administración",
        "Valor de administración",
        "Cuota de administración",
        "Administración mensual",
    ]

    for field in fields:

        value = get_specification_value(
            specifications,
            field
        )

        if value:

            match = re.search(
                r'\d[\d.,]*',
                str(value)
            )

            if match:
                admin_price = parse_cop_amount(
                    match.group(0)
                )

                logger.info(
                    "Administration price extracted from specification: "
                    "field=%s, price_cop=%s",
                    field,
                    admin_price,
                )

                return admin_price

    if not description:
        logger.debug("Administration price not found: no description.")
        return None

    patterns = [
        r'administraci[oó]n\s*:\s*\$?\s*([\d.]+(?:,\d+)?)',
        r'administraci[oó]n\s+de\s+\$?\s*([\d.]+(?:,\d+)?)',
        r'administraci[oó]n\s+mensual\s+de\s+\$?\s*([\d.]+(?:,\d+)?)',
        r'administraci[oó]n\s+son\s+de\s+\$?\s*([\d.]+(?:,\d+)?)',
    ]

    for pattern in patterns:

        match = re.search(
            pattern,
            description,
            re.IGNORECASE
        )

        if match:
            admin_price = parse_cop_amount(
                match.group(1)
            )

            logger.info(
                "Administration price extracted from description: "
                "price_cop=%s",
                admin_price,
            )

            return admin_price

    logger.debug("Administration price not found.")

    return None


# PROPERTY DETAILS

def create_property_details_list(
    property_type,
    specifications,
    price,
    area,
    cop_usd_rate,
):

    return [
        # {
        #     "label": "Property Type",
        #     "value": translate_text(property_type),
        # },
        # {
        #     "label": "Condition",
        #     "value": translate_text(
        #         get_specification_value(
        #             specifications,
        #             "Estado"
        #         )
        #     ),
        # },
        # {
        #     "label": "Bathrooms",
        #     "value": get_specification_value(
        #         specifications,
        #         "Baños"
        #     ),
        # },
        # {
        #     "label": "Bedrooms",
        #     "value": get_specification_value(
        #         specifications,
        #         "Habitaciones"
        #     ),
        # },
        {
            "label": "Parking Spaces",
            "value": get_specification_value(
                specifications,
                "Parqueaderos"
            ),
        },
        # {
        #     "label": "Area (sq ft)",
        #     "value": area,
        # },
        {
            "label": "Socioeconomic Stratum",
            "value": get_specification_value(
                specifications,
                "Estrato"
            ),
        },
        {
            "label": "Floor Number",
            "value": get_specification_value(
                specifications,
                "Piso"
            ),
        },
        {
            "label": "Number of Floors",
            "value": get_specification_value(
                specifications,
                "Número de pisos"
            ),
        },
        # {
        #     "label": "Price (COP)",
        #     "value": price,
        # },
        # {
        #     "label": "COP per USD",
        #     "value": round(1 / cop_usd_rate, 2)
        #     if cop_usd_rate else None,
        # },
        {
            "label": "Use",
            "value": get_specification_value(
                specifications,
                "Uso"
            ),
        }

    ]


def create_property_details(property_data, cop_usd_rate):

    product_id = property_data.get("productId")

    logger.info(
        "Processing property: product_id=%s, reference=%s, name=%s",
        product_id,
        property_data.get("productReference"),
        property_data.get("productName"),
    )

    specifications = get_specifications(property_data)

    # Keep every unique image URL from every item.
    images = get_images(property_data)

    prices = get_prices(property_data)

    description = property_data.get("description")

    property_type = get_property_type(property_data)

    is_project = property_type == "Project"

    logger.info(
        "Property classified: product_id=%s, property_type=%s, is_project=%s",
        product_id,
        property_type,
        is_project,
    )

    # Read the different apartment configurations for projects.
    project_configurations = (
        get_project_configurations(property_data)
        if is_project
        else []
    )

    # First use an exact area from the parent product's specifications.
    # Project descriptions can mention many apartment sizes, so don't use
    # the first number in the description when individual configurations are known.
    area_m2 = get_area(
        None if is_project else description,
        specifications
    )

    if is_project and not area_m2:

        known_areas = [
            config["built_area_m2"]
            for config in project_configurations
            if (
                config["built_area_m2"] is not None
                and config["built_area_m2"] > 0
            )
        ]

        if known_areas:
            area_m2 = min(known_areas)

            logger.info(
                "Project area selected from configurations: "
                "product_id=%s, area_m2=%s",
                product_id,
                area_m2,
            )

        else:
            # Only use the description if no configuration has an exact area.
            area_m2 = get_area(
                description,
                {}
            )

    area = convert_m2_to_sqft(area_m2)

    logger.info(
        "Property area result: product_id=%s, area_m2=%s, area_sq_ft=%s",
        product_id,
        area_m2,
        area,
    )

    interior_details = get_interior_details(specifications)

    exterior_details = get_exterior_details(specifications)

    amenities = (
        get_flagged_items(specifications, INTERIOR_FIELDS)
        + get_flagged_items(specifications, EXTERIOR_FIELDS)
    )

    city = get_specification_value(
        specifications,
        "Ciudad"
    )

    province = get_specification_value(
        specifications,
        "Departamento"
    )

    neighbourhood = get_specification_value(
        specifications,
        "Barrio"
    )

    latitude = get_specification_value(
        specifications,
        "Latitud"
    )

    longitude = get_specification_value(
        specifications,
        "Longitud"
    )

    try:
        valid_coordinates = (
            latitude is not None
            and longitude is not None
            and -90 <= float(latitude) <= 90
            and -180 <= float(longitude) <= 180
        )

    except (ValueError, TypeError):
        valid_coordinates = False

    lat_lng_status = 1 if valid_coordinates else 0

    if not valid_coordinates:
        logger.warning(
            "Invalid or missing coordinates: product_id=%s, lat=%s, lng=%s",
            product_id,
            latitude,
            longitude,
        )

    phone = (
        get_specification_value(
            specifications,
            "Teléfono agente"
        )
        or get_specification_value(
            specifications,
            "Número de WhatsApp"
        )
    )

    admin_price = get_admin_price(
        description,
        specifications
    )

    # For projects, use the lowest price from the parent price range first.
    # If it is missing, fall back to the lowest valid configuration price.
    if is_project:

        selling_price = (
            property_data
            .get("priceRange", {})
            .get("sellingPrice", {})
        )

        project_starting_price = parse_number(
            selling_price.get("lowPrice")
        )

        if (
            project_starting_price is not None
            and project_starting_price > 0
        ):
            price = project_starting_price

            logger.info(
                "Project starting price selected from parent price range: "
                "product_id=%s, price_cop=%s",
                product_id,
                price,
            )

        else:
            project_prices = [
                config["price_cop"]
                for config in project_configurations
                if (
                    config["price_cop"] is not None
                    and config["price_cop"] > 0
                )
            ]

            price = (
                min(project_prices)
                if project_prices
                else None
            )

            logger.info(
                "Project starting price selected from configurations: "
                "product_id=%s, price_cop=%s",
                product_id,
                price,
            )

    # Normal apartments, houses, and offices keep their existing price handling.
    elif len(prices) == 1:
        price = prices[0]

    elif len(prices) > 1:
        price = prices

    else:
        price = None

    logger.info(
        "Property price selected: product_id=%s, price_cop=%s",
        product_id,
        price,
    )

    usd_price = convert_price_to_usd(
        price,
        cop_usd_rate
    )

    logger.info(
        "Property price converted: product_id=%s, price_usd=%s",
        product_id,
        usd_price,
    )

    # If the parent project has no bedroom/bathroom counts, use the minimum
    # values from the configurations so the project row has a useful summary.
    bedrooms = get_specification_int(
        specifications,
        "Habitaciones"
    )

    full_baths = get_specification_int(
        specifications,
        "Baños"
    )

    if is_project:

        known_bedrooms = [
            config["bedrooms"]
            for config in project_configurations
            if config["bedrooms"] is not None
        ]

        known_bathrooms = [
            config["bathrooms"]
            for config in project_configurations
            if config["bathrooms"] is not None
        ]

        # Project summary fields show the smallest available configuration.
        if known_bedrooms:
            bedrooms = int(min(known_bedrooms))

        if known_bathrooms:
            full_baths = int(min(known_bathrooms))

    property_details_list = create_property_details_list(
        property_type,
        specifications,
        price,
        area,
        cop_usd_rate,
    )

    # Add each apartment configuration inside the existing property_details
    # list. This does not add columns or create extra project rows in the CSV.
    if is_project:

        main_project_images = get_main_project_images(
            property_data
        )

        if main_project_images:
            property_details_list.append({
                "label": "Main Project Images",
                "value": main_project_images,
            })

        append_project_details(
            property_details_list,
            project_configurations,
            cop_usd_rate,
        )

    # Keep the different project configurations in the database field.
    commercial_units = (
        get_commercial_units(
            project_configurations,
            cop_usd_rate
        )
        if is_project
        else None
    )

    # Build the MLS ID from the API product ID.
    mls_id = (
        f"inm{product_id}"
        if product_id is not None
        else None
    )

    logger.info(
        "Property extraction completed: product_id=%s, "
        "images=%s, amenities=%s, bedrooms=%s, bathrooms=%s, "
        "commercial_units=%s",
        product_id,
        len(images),
        len(amenities),
        bedrooms,
        full_baths,
        len(commercial_units) if commercial_units else 0,
    )

    missing_fields = [
        field
        for field, value in {
            "title": property_data.get("productName"),
            "link": property_data.get("link"),
            "city": city,
            "province": province,
            "area": area,
            "price": usd_price,
            "images": images,
        }.items()
        if value is None or value == "" or value == []
    ]

    if missing_fields:
        logger.warning(
            "Property has missing fields: product_id=%s, fields=%s",
            product_id,
            missing_fields,
        )

    return {
        "title": translate_text(
            property_data.get("productName")
        ),

        "link": BASE_URL + property_data.get("link", ""),

        "location": (
            f"{neighbourhood}, {city}, {province}"
            if neighbourhood and city and province
            else None
        ),

        "country": "Colombia",

        "lat": latitude,

        "lng": longitude,

        "latLng_status": lat_lng_status,

        "type": translate_text(get_type(property_data)),

        "phone": phone,

        "price": usd_price,

        "price_unit": None,

        "details": translate_text(description),

        "img_src": images,

        "about": None,

        # Keep the API product reference as the web ID.
        "web_id": property_data.get("productReference"),

        # Use productId with the required "inm" prefix.
        "mls_id": mls_id,

        "bedrooms": bedrooms,

        "full_baths": full_baths,

        "property_type": translate_text(property_type),

        "interior_sq_ft": area,

        "amneties": amenities,

        "features": None,

        "partial_baths": None,

        "change_price": None,

        "sold_date": None,

        "created_at": None,

        "updated_at": None,

        "city": city,

        "new_features": None,

        "property_details": property_details_list,

        "exterior_details": exterior_details,

        "interior_details": interior_details,

        "city_checked": 1 if city else 0,

        "province": province,

        "property_status": translate_text(
            get_specification_value(
                specifications,
                "Estado"
            )
        ),

        "neighbourhood": neighbourhood,

        "commercial_units": commercial_units,

        "admin_price": admin_price,
    }


# CSV

def load_existing_links():

    existing_links = set()

    if not os.path.exists(OUTPUT_FILE):
        logger.info("Existing CSV not found. A new CSV will be created.")
        return existing_links

    try:
        with open(
            OUTPUT_FILE,
            "r",
            newline="",
            encoding="utf-8-sig"
        ) as file:

            reader = csv.DictReader(file)

            if not reader.fieldnames or "link" not in reader.fieldnames:
                logger.error(
                    "Existing CSV does not contain a 'link' column."
                )

                raise ValueError(
                    "The existing CSV does not contain a 'link' column. "
                    "Back it up and check its headers before continuing."
                )

            for row in reader:

                if row.get("link"):
                    existing_links.add(row["link"])

    except (OSError, csv.Error):
        logger.exception("Failed to load existing CSV links.")
        raise

    logger.info(
        "Existing CSV links loaded: count=%s",
        len(existing_links),
    )

    return existing_links


def save_to_csv(property_details, existing_links):

    link = property_details.get("link")
    title = property_details.get("title")
    product_id = property_details.get("mls_id")

    if not link:
        logger.warning(
            "Skipping property without a link: title=%s, product_id=%s",
            title,
            product_id,
        )

        return False

    if link in existing_links:
        logger.info(
            "Duplicate property skipped: title=%s, link=%s",
            title,
            link,
        )

        print(
            "Already exists, skipping:",
            title
        )

        return False

    file_exists = (
        os.path.exists(OUTPUT_FILE)
        and os.path.getsize(OUTPUT_FILE) > 0
    )

    fieldnames = list(property_details.keys())

    row = property_details.copy()

    # CSV cells must contain strings for nested lists/dictionaries.
    for key, value in row.items():

        if isinstance(value, (list, dict)):
            row[key] = json.dumps(
                value,
                ensure_ascii=False
            )

    try:
        with open(
            OUTPUT_FILE,
            "a",
            newline="",
            encoding="utf-8"
        ) as file:

            writer = csv.DictWriter(
                file,
                fieldnames=fieldnames
            )

            if not file_exists:
                writer.writeheader()

                logger.info(
                    "CSV header created: columns=%s",
                    len(fieldnames),
                )

            writer.writerow(row)

        existing_links.add(link)

        logger.info(
            "CSV row saved successfully: title=%s, product_id=%s, type=%s",
            title,
            product_id,
            property_details.get("property_type"),
        )

        return True

    except (OSError, csv.Error, TypeError, ValueError):
        logger.exception(
            "CSV write failed: title=%s, product_id=%s",
            title,
            product_id,
        )
        raise


# MAIN

def main():

    logger.info("Starting scraper main process.")

    saved_count = 0
    skipped_count = 0
    failed_count = 0
    processed_count = 0

    # Check the translation API before starting the scraper.
    print("Testing Google Translate API...")
    logger.info("Testing Google Translate API.")

    try:
        test_translation = translate_text("Venta")

        print("Translation test successful:")
        print("Spanish: Venta")
        print("English:", test_translation)

        logger.info(
            "Translation test successful: Venta -> %s",
            test_translation,
        )

    except Exception as error:

        logger.exception("Translation API test failed")

        print("Translation test failed:")
        print(error)
        print("Scraping stopped. Fix the translation issue first.")

        return

    print("\nGetting current exchange rate...")
    logger.info("Getting current exchange rate.")

    try:
        cop_usd_rate = get_cop_usd_rate()

    except Exception:
        logger.exception(
            "Scraping stopped because the exchange rate could not be loaded."
        )
        print("Failed to retrieve exchange rate. Check the log file.")
        return

    print("Loading existing property links...")

    try:
        existing_links = load_existing_links()

    except Exception:
        logger.exception(
            "Scraping stopped because existing CSV links could not be loaded."
        )
        print("Failed to load existing CSV. Check the log file.")
        return

    print("Getting properties...")
    logger.info("Starting property extraction from TU360.")

    offset = 0
    total_records = None

    while True:

        # This assumes the API's 'to' parameter is inclusive.
        from_value = offset
        to_value = offset + BATCH_SIZE - 1

        try:
            products, total_records = get_properties(
                from_value,
                to_value
            )

        except (
            requests.RequestException,
            ValueError,
            KeyError,
            RuntimeError,
        ):

            logger.exception(
                "API request failed at offset %s. Scraping will stop.",
                offset,
            )

            print(
                f"Request failed at offset {offset}. "
                "Check the log file."
            )

            break

        if total_records is None:
            logger.error("Could not determine the total record count.")
            print("Could not determine the total record count.")
            break

        print(
            f"Offset {offset}: received {len(products)} properties "
            f"(total reported: {total_records})"
        )

        logger.info(
            "Processing batch: offset=%s, received=%s, total=%s",
            offset,
            len(products),
            total_records,
        )

        if not products:
            logger.warning(
                "No products returned at offset %s. Ending extraction.",
                offset,
            )
            break

        for product in products:

            processed_count += 1

            try:
                property_details = create_property_details(
                    product,
                    cop_usd_rate
                )

                saved = save_to_csv(
                    property_details,
                    existing_links
                )

                if saved:
                    saved_count += 1

                    print(
                        "Saved:",
                        property_details["property_type"],
                        "-",
                        property_details["title"]
                    )

                else:
                    skipped_count += 1

            except Exception as error:

                failed_count += 1

                logger.exception(
                    "Failed to process property: product_id=%s, "
                    "reference=%s, name=%s, error=%s",
                    product.get("productId"),
                    product.get("productReference"),
                    product.get("productName"),
                    error,
                )

                print(
                    "Failed to process:",
                    product.get("productName"),
                    "-",
                    str(error)
                )

        offset += len(products)

        logger.info(
            "Batch completed: next_offset=%s, saved=%s, "
            "skipped=%s, failed=%s",
            offset,
            saved_count,
            skipped_count,
            failed_count,
        )

        if offset >= total_records:
            logger.info(
                "All reported records processed: offset=%s, total=%s",
                offset,
                total_records,
            )
            break

    logger.info("=" * 70)
    logger.info("SCRAPING FINISHED")
    logger.info("Total products processed: %s", processed_count)
    logger.info("New properties saved: %s", saved_count)
    logger.info("Properties skipped: %s", skipped_count)
    logger.info("Properties failed: %s", failed_count)
    logger.info("Output file: %s", OUTPUT_FILE)
    logger.info("=" * 70)

    print("\nScraping finished.")
    print("Total processed:", processed_count)
    print("New properties saved:", saved_count)
    print("Properties skipped:", skipped_count)
    print("Properties failed:", failed_count)
    print("CSV file:", OUTPUT_FILE)


if __name__ == "__main__":
    try:
        main()

    except Exception:
        logger.exception("Unexpected fatal error in the scraper.")
        raise

    finally:
        logger.info("TU360 scraper process ended.")
