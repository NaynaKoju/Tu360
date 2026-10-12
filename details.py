
import os
import re
import csv
import json
import html
import logging
import base64

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

os.makedirs("../scraper_logs", exist_ok=True)

logging.basicConfig(
    filename="../scraper_logs/TU360details.log",
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

logger = logging.getLogger(__name__)

# TRANSLATION

TRANSLATE_URL = "https://translate-pa.googleapis.com/v1/translateHtml"

_translation_cache = {}


def translate_text(text, source="es", target="en"):
    if not text or not isinstance(text, str):
        return text

    text = text.strip()

    if not text:
        return text

    # Avoid translating the same text multiple times
    cache_key = (text, source, target)

    if cache_key in _translation_cache:
        return _translation_cache[cache_key]

    if not GOOGLE_TRANSLATE_API_KEY:
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

    try:
        response = requests.post(
            TRANSLATE_URL,
            headers=headers,
            json=payload,
            timeout=20,
        )

        response.raise_for_status()
        result = response.json()

        # Extract the translated text
        if not result or not result[0]:
            raise ValueError("Google returned an empty translation")

        translated = result[0][0]

        # Some responses may contain multiple text segments
        if isinstance(translated, list):
            translated = "".join(str(part) for part in translated)

        if not isinstance(translated, str):
            raise ValueError(
                f"Unexpected translation format: {translated!r}"
            )

        _translation_cache[cache_key] = translated

        return translated

    except requests.RequestException as error:
        raise RuntimeError(
            f"Google Translate request failed: {error}"
        ) from error

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

    response = requests.get(
        API_URL,
        params=params,
        timeout=30,
    )

    response.raise_for_status()

    data = response.json()

    if data.get("errors"):
        raise RuntimeError(
            f"TU360 API returned errors: {data['errors']}"
        )

    product_search = data["data"]["productSearch"]

    return (
        product_search["products"],
        product_search["recordsFiltered"],
    )

# SPECIFICATIONS

def get_specifications(property_data):

    specifications = {}

    for item in property_data.get("properties", []):

        name = item.get("name")
        values = item.get("values", [])

        if name:
            specifications[name] = values

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

    try:
        return int(float(str(value).strip()))

    except (ValueError, TypeError):
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

    images = []

    for item in property_data.get("items", []):

        for image in item.get("images", []):

            image_url = image.get("imageUrl")

            if image_url:
                images.append(image_url)

    return list(dict.fromkeys(images))


def get_prices(property_data):

    prices = []

    for item in property_data.get("items", []):

        for seller in item.get("sellers", []):

            offer = seller.get("commertialOffer", {})
            price = offer.get("Price")

            if price is not None:
                prices.append(price)

    return list(dict.fromkeys(prices))

def get_cop_usd_rate():

    response = requests.get(
        "https://api.frankfurter.dev/v2/rates?base=usd",
        timeout=15,
    )

    response.raise_for_status()

    data = response.json()

    rate_data = next(
        (item for item in data if item["quote"] == "COP"),
        None
    )

    if not rate_data or not rate_data.get("rate"):
        raise ValueError(
            "Could not retrieve the USD to COP exchange rate."
        )

    usd_cop_rate = float(rate_data["rate"])

    cop_usd_rate = 1 / usd_cop_rate

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
        return round(float(price) * cop_usd_rate, 3)

    except (ValueError, TypeError):
        return None

# AREA

def get_area(description=None, specifications=None):

    # 1. Try extracting area from API specifications first
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

                # Get the first value if values is a list
                if isinstance(values, list):
                    values = values[0] if values else None

                # Handle API values that are dictionaries
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

    # 2. Fall back to extracting area from the description
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
                    area_m2 = float(match.group(1).replace(",", "."))

                    if area_m2 > 0:
                        return area_m2

                except (ValueError, TypeError):
                    continue

    return None

def convert_m2_to_sqft(area_m2):

    if area_m2 is None:
        return None

    return round(area_m2 * 10.7639, 2)

# PROPERTY TYPE

def get_property_type(property_data):
    link = property_data.get("link", "").lower()

    # Extract the property type from the beginning of the URL
    match = re.search(r"/([^/]+)-en-venta-en-", link)

    if match:
        property_type = match.group(1)
        return property_type.replace("-", " ").title()

    # Handle housing project URLs separately
    if "proyecto-de-vivienda" in link:
        return "Project"

    return None

def get_type(property_data):

    for category in property_data.get("categories", []):

        parts = category.strip("/").split("/")

        if parts:
            return parts[0]

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
                return parse_cop_amount(match.group(0))

    if not description:
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
            return parse_cop_amount(match.group(1))

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
        {
            "label": "Property Type",
            "value": translate_text(property_type),
        },
        {
            "label": "Condition",
            "value": translate_text(
                get_specification_value(
                    specifications,
                    "Estado"
                )
            ),
        },
        {
            "label": "Bathrooms",
            "value": get_specification_value(
                specifications,
                "Baños"
            ),
        },
        {
            "label": "Bedrooms",
            "value": get_specification_value(
                specifications,
                "Habitaciones"
            ),
        },
        {
            "label": "Parking Spaces",
            "value": get_specification_value(
                specifications,
                "Parqueaderos"
            ),
        },
        {
            "label": "Area (sq ft)",
            "value": area,
        },
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
        {
            "label": "Price (COP)",
            "value": price,
        },
        {
            "label": "COP per USD",
            "value": round(1 / cop_usd_rate, 2)
            if cop_usd_rate else None,
        },
    ]


def create_property_details(property_data, cop_usd_rate):

    specifications = get_specifications(property_data)

    images = get_images(property_data)
    prices = get_prices(property_data)

    description = property_data.get("description")

    # Extract area and convert square meters to square feet.
    area_m2 = get_area(description, specifications)
    area = convert_m2_to_sqft(area_m2)

    property_type = get_property_type(property_data)

    interior_details = get_interior_details(specifications)
    exterior_details = get_exterior_details(specifications)

    amenities = (
        get_flagged_items(specifications, INTERIOR_FIELDS)
        + get_flagged_items(specifications, EXTERIOR_FIELDS)
    )

    city = get_specification_value(specifications, "Ciudad")
    province = get_specification_value(specifications, "Departamento")
    neighbourhood = get_specification_value(specifications, "Barrio")

    latitude = get_specification_value(specifications, "Latitud")
    longitude = get_specification_value(specifications, "Longitud")

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

    phone = (
        get_specification_value(specifications, "Teléfono agente")
        or get_specification_value(specifications, "Número de WhatsApp")
    )

    admin_price = get_admin_price(
        description,
        specifications
    )

    # Use None when no price is available.
    if len(prices) == 1:
        price = prices[0]
    elif len(prices) > 1:
        price = prices
    else:
        price = None

    usd_price = convert_price_to_usd(
        price,
        cop_usd_rate
    )

    property_details_list = create_property_details_list(
        property_type,
        specifications,
        price,
        area,
        cop_usd_rate,
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

        "type": get_type(property_data),

        "phone": phone,

        "price": usd_price,
        "price_unit": "USD",

        "details": translate_text(description),

        "img_src": images,

        "about": None,

        "web_id": property_data.get("productReference"),
        "mls_id": None,

        "bedrooms": get_specification_int(
            specifications,
            "Habitaciones"
        ),

        "full_baths": get_specification_int(
            specifications,
            "Baños"
        ),

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

        "commercial_units": None,

        "admin_price": admin_price,
    }

# CSV

def load_existing_links():

    existing_links = set()

    if not os.path.exists(OUTPUT_FILE):
        return existing_links

    with open(
        OUTPUT_FILE,
        "r",
        newline="",
        encoding="utf-8-sig"
    ) as file:

        reader = csv.DictReader(file)

        if not reader.fieldnames or "link" not in reader.fieldnames:
            raise ValueError(
                "The existing CSV does not contain a 'link' column. "
                "Back it up and check its headers before continuing."
            )

        for row in reader:

            if row.get("link"):
                existing_links.add(row["link"])

    return existing_links

def save_to_csv(property_details, existing_links):

    link = property_details.get("link")

    if not link:
        logger.warning(
            "Skipping property without a link: %s",
            property_details.get("title")
        )
        return False

    if link in existing_links:
        print(
            "Already exists, skipping:",
            property_details.get("title")
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

        writer.writerow(row)

    existing_links.add(link)

    return True

# MAIN

def main():

    # Check the translation API before starting the scraper.
    print("Testing Google Translate API...")

    try:
        test_translation = translate_text("Venta")

        print("Translation test successful:")
        print("Spanish: Venta")
        print("English:", test_translation)

    except Exception as error:

        logger.exception("Translation API test failed")

        print("Translation test failed:")
        print(error)
        print("Scraping stopped. Fix the translation issue first.")

        return

    print("\nGetting current exchange rate...")

    cop_usd_rate = get_cop_usd_rate()

    print("Loading existing property links...")

    existing_links = load_existing_links()

    print("Getting properties...")

    offset = 0
    total_records = None
    saved_count = 0
    skipped_count = 0

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
        ) as error:

            logger.exception(
                "API request failed at offset %s: %s",
                offset,
                error
            )

            print(
                f"Request failed at offset {offset}. "
                "Check the log file."
            )
            break

        if total_records is None:
            print("Could not determine the total record count.")
            break

        print(
            f"Offset {offset}: received {len(products)} properties "
            f"(total reported: {total_records})"
        )

        if not products:
            break

        for product in products:

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

                logger.exception(
                    "Failed to process property %s: %s",
                    product.get("productReference"),
                    error
                )

                print(
                    "Failed to process:",
                    product.get("productName"),
                    "-",
                    str(error)
                )

        offset += len(products)

        if offset >= total_records:
            break

    print("\nScraping finished.")
    print("New properties saved:", saved_count)
    print("Properties skipped:", skipped_count)
    print("CSV file:", OUTPUT_FILE)


if __name__ == "__main__":
    main()
