import csv
import json
import logging
import base64
import requests
import re


API_URL = "https://inmobiliariotu360.bancolombia.com/_v/segment/graphql/v1"

OUTPUT_FILE = "./csv_files/property_details.csv"


# Logging
logging.basicConfig(
    filename="../scraper_logs/TU360details.log",
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

logger = logging.getLogger(__name__)


# INTERIOR AMENITIES

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


# EXTERIOR AMENITIES

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
            {
                "key": "category-1",
                "value": "venta"
            },
            {
                "key": "ciudad",
                "value": "medellin"
            }
        ],

        "operator": "and",
        "fuzzy": "0",
        "searchState": None,
        "facetsBehavior": "Static",
        "categoryTreeBehavior": "default",
        "withFacets": False
    }

    variables_json = json.dumps(variables)

    variables_base64 = base64.b64encode(
        variables_json.encode()
    ).decode()

    params = {
        "workspace": "master",
        "maxAge": "short",
        "appsEtag": "remove",
        "domain": "store",
        "locale": "es-CO",

        "__bindingId":
            "f91c6084-ca4b-4afa-9b2d-7d09efca9e7c",

        "operationName": "productSearchV3",

        "variables": "{}",

        "extensions": json.dumps({
            "persistedQuery": {
                "version": 1,
                "sha256Hash":
                    "a96c5ed03ef513568c34b63a4bf8da055ea6296293ee02eadb56e2e895eaffbc",
                "sender": "vtex.store-resources@0.x",
                "provider": "vtex.search-graphql@0.x"
            },

            "variables": variables_base64
        })
    }

    response = requests.get(
        API_URL,
        params=params,
        timeout=30
    )

    response.raise_for_status()

    data = response.json()

    product_search = data["data"]["productSearch"]

    return (
        product_search["products"],
        product_search["recordsFiltered"]
    )


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

#for bedroom and fullbath
def get_specification_int(specifications, name):
    value = get_specification_value(specifications, name)

    if value is None or value == "":
        return None

    try:
        return int(value)
    except (ValueError, TypeError):
        return None

def get_flagged_items(specifications, fields):

    items = []

    for field in fields:

        value = get_specification_value(
            specifications,
            field
        )

        if value and value.strip().upper() == "SI":

            items.append(field)

    return items


def get_interior_details(specifications):

    return json.dumps(
        {
            "Interior":
                get_flagged_items(
                    specifications,
                    INTERIOR_FIELDS
                )
        },
        ensure_ascii=False
    )


def get_exterior_details(specifications):

    return json.dumps(
        {
            "Exterior":
                get_flagged_items(
                    specifications,
                    EXTERIOR_FIELDS
                )
        },
        ensure_ascii=False
    )


def get_images(property_data):

    images = []

    for item in property_data.get("items", []):

        for image in item.get("images", []):

            image_url = image.get("imageUrl")

            if image_url:

                images.append(image_url)

    return list(dict.fromkeys(images))


def get_cop_usd_rate():

    response = requests.get(
        "https://api.frankfurter.dev/v2/rates?base=usd",
        timeout=10
    )

    response.raise_for_status()

    data = response.json()

    # Find the USD -> COP exchange rate
    rate_data = next(
        item
        for item in data
        if item["quote"] == "COP"
    )

    usd_cop_rate = rate_data["rate"]

    # Get the date of the exchange rate
    rate_date = rate_data["date"]

    print(
        f"USD to COP exchange rate: {usd_cop_rate} "
        f"(rate date: {rate_date})"
    )

    # Convert USD -> COP rate into COP -> USD rate
    cop_usd_rate = 1 / usd_cop_rate

    return cop_usd_rate


def convert_price_to_usd(price, cop_usd_rate):

    # Convert multiple prices from COP to USD
    if isinstance(price, list):

        usd_prices = []

        for item in price:

            if item is not None:

                usd_prices.append(
                    round(float(item) * cop_usd_rate, 3)
                )

            else:

                usd_prices.append(None)

        return usd_prices

    # Convert a single price from COP to USD
    if price is not None:

        return round(
            float(price) * cop_usd_rate,
            3
        )

    return None


def get_prices(property_data):

    prices = []

    for item in property_data.get("items", []):

        for seller in item.get("sellers", []):

            offer = seller.get(
                "commertialOffer",
                {}
            )

            price = offer.get("Price")

            if price is not None:

                prices.append(price)

    return list(dict.fromkeys(prices))


def get_area(description):

    if not description:
        return None

    patterns = [
        # Prefer built area
        r'área\s+construida\s*:?\s*(\d+(?:[.,]\d+)?)\s*m\s*(?:²|2)(?!\w)',

        # Fallback to private area
        r'área\s+privada\s*:?\s*(\d+(?:[.,]\d+)?)\s*m\s*(?:²|2)(?!\w)',

        # Fallback to general area
        r'\bárea\s*:?\s*(\d+(?:[.,]\d+)?)\s*m\s*(?:²|2)(?!\w)',

        # Match area mentioned in complementName, e.g. "con area 170m2"
        r'\b(?:con\s+)?[áa]rea\s+(?:de\s+)?(\d+(?:[.,]\d+)?)\s*m\s*(?:²|2)(?!\w)',

        # Match area without a specific label
        r'(\d+(?:[.,]\d+)?)\s*m\s*(?:²|2)(?!\w)',

        # Match Spanish wording
        r'(\d+(?:[.,]\d+)?)\s*metros?\s*cuadrados?\b',
    ]

    for pattern in patterns:

        match = re.search(
            pattern,
            description,
            re.IGNORECASE
        )

        if match:

            return float(
                match.group(1).replace(",", ".")
            )

    return None


# Convert square meters into square feet
def convert_m2_to_sqft(area_m2):

    if area_m2 is None:
        return None

    return round(
        area_m2 * 10.7639,
        2
    )


def get_property_type(property_data):

    link = property_data.get(
        "link",
        ""
    ).lower()

    if "proyecto-de-vivienda" in link:

        property_type = "Proyecto"

    elif "apartamento-en-venta" in link:

        property_type = "Apartamento"

    elif "casa-en-venta" in link:

        property_type = "Casa"

    elif "oficina-en-venta" in link:

        property_type = "Oficina"

    elif "local-en-venta" in link:

        property_type = "Local"

    else:

        property_type = None

    return property_type

def get_admin_price(description, specifications):

    # Check the administration price in API specifications
    for field in [
        "Valor administración",
        "Administración",
        "Valor de administración",
        "Cuota de administración",
        "Administración mensual"
    ]:

        values = specifications.get(field, [])

        if values and values[0]:

            match = re.search(
                r'\d[\d.,]*',
                str(values[0])
            )

            if match:

                return float(
                    match.group(0).replace(".", "").replace(",", ".")
                )

    # Extract administration price from the description
    if description:

        patterns = [
            # Match "administración: $456.000"
            r'administraci[oó]n\s*:\s*\$?\s*([\d.]+(?:,\d+)?)',

            # Match "administración de $738.305"
            r'administraci[oó]n\s+de\s+\$?\s*([\d.]+(?:,\d+)?)',

            # Match "de administración mensual de $490,000"
            r'administraci[oó]n\s+mensual\s+de\s+\$?\s*([\d.]+(?:,\d+)?)',

            # Match "de administración son de $380,000"
            r'administraci[oó]n\s+son\s+de\s+\$?\s*([\d.]+(?:,\d+)?)',

            # Match other formats containing "administración" before the price
            r'administraci[oó]n[^.$\n]{0,60}\$?\s*([\d][\d.,]*)',
        ]

        for pattern in patterns:

            match = re.search(
                pattern,
                description,
                re.IGNORECASE
            )

            if match:

                # Convert Colombian currency formatting into a number
                price_text = match.group(1).replace(".", "").replace(",", "")

                return int(price_text)

    return None


def create_property_details_list(
    property_data,
    specifications,
    property_type,
    price,
    area,
    cop_usd_rate
):

    property_details = [

        {
            "label": "Property Type",
            "value": property_type
        },

        {
            "label": "Condition",
            "value": get_specification_value(
                specifications,
                "Estado"
            )
        },

        {
            "label": "Bathrooms",
            "value": get_specification_value(
                specifications,
                "Baños"
            )
        },

        {
            "label": "Bedrooms",
            "value": get_specification_value(
                specifications,
                "Habitaciones"
            )
        },

        {
            "label": "Parking Spaces",
            "value": get_specification_value(
                specifications,
                "Parqueaderos"
            )
        },

        {
            "label": "Private Area",
            "value": area
        },

        {
            "label": "Socioeconomic Stratum",
            "value": get_specification_value(
                specifications,
                "Estrato"
            )
        },

        {
            "label": "Floor Number",
            "value": get_specification_value(
                specifications,
                "Piso"
            )
        },

        {
            "label": "Number of Floors",
            "value": get_specification_value(
                specifications,
                "Número de pisos"
            )
        },

        {
            "label": "Price (COP)",
            "value": price
        },

        {
            "label": "COP per USD",
            "value": round(1 / cop_usd_rate, 2)
            if cop_usd_rate else None
        }
    ]

    return property_details

def get_type(property_data):
    categories = property_data.get("categories", [])

    for category in categories:
        parts = category.strip("/").split("/")

        if parts:
            return parts[0]

    return None

def create_property_details(property_data, cop_usd_rate):

    specifications = get_specifications(
        property_data
    )

    images = get_images(
        property_data
    )

    prices = get_prices(
        property_data
    )

    # Extract the original area in square meters
    area_m2 = get_area(
        property_data.get("description")
    )

    # Convert the area from square meters into square feet
    area = convert_m2_to_sqft(
        area_m2
    )

    property_type = get_property_type(
        property_data
    )

    # Interior and exterior details

    interior_details = get_interior_details(
        specifications
    )

    exterior_details = get_exterior_details(
        specifications
    )

    # Combined amenities

    amenities = (
        get_flagged_items(
            specifications,
            INTERIOR_FIELDS
        )
        +
        get_flagged_items(
            specifications,
            EXTERIOR_FIELDS
        )
    )

    city = specifications.get(
        "Ciudad",
        [None]
    )[0]

    province = specifications.get(
        "Departamento",
        [None]
    )[0]

    neighbourhood = specifications.get(
        "Barrio",
        [None]
    )[0]

    latitude = specifications.get(
        "Latitud",
        [None]
    )[0]

    longitude = specifications.get(
        "Longitud",
        [None]
    )[0]

    if latitude and longitude:

        lat_lng_status = 1

    else:

        lat_lng_status = 0

    phone = specifications.get(
        "Teléfono agente",
        [None]
    )[0]

    if not phone:

        phone = specifications.get(
            "Número de WhatsApp",
            [None]
        )[0]

    admin_price = get_admin_price(
    property_data.get("description"),
    specifications
    )

    if admin_price:

        try:

            admin_price = int(admin_price)

        except ValueError:

            pass

    if len(prices) == 1:

        price = prices[0]

    else:

        price = prices


    # Convert the original COP price into USD
    usd_price = convert_price_to_usd(
        price,
        cop_usd_rate
    )

    

    # Create property_details in the required format

    property_details_list = create_property_details_list(
        property_data,
        specifications,
        property_type,
        price,
        area,
        cop_usd_rate
    )

    property_details = {

        "title":
            property_data.get("productName"),

        "link":
            "https://inmobiliariotu360.bancolombia.com"
            + property_data.get("link", ""),

        "location":
            f"{neighbourhood}, {city}, {province}"
            if neighbourhood and city and province
            else None,

        "country":
            "Colombia",

        "lat":
            latitude,

        "lng":
            longitude,

        "latLng_status":
            lat_lng_status,

        "type": 
            get_type(property_data),

        "phone":
            phone,

        "price":
            usd_price,

        "price_unit":
            "USD",

        "details":
            property_data.get("description"),

        "img_src":
            images,

        "about":
            None,

        "web_id":
            property_data.get("productReference"),

        "mls_id":
            None,

        "bedrooms":
            get_specification_int(
                specifications,
                "Habitaciones"
            ),

        "full_baths":
            get_specification_int(
                specifications,
                "Baños"
            ),
            
        "property_type":
            property_type,

        # Area is now stored in square feet
        "interior_sq_ft":
            area,

        "amneties":
            amenities,

        "features":
            None,

        "partial_baths":
            None,

        "change_price":
            None,

        "sold_date":
            None,

        "created_at":
            None,

        "updated_at":
            None,

        "city":
            city,

        "new_features":
            None,

        "property_details":
            property_details_list,

        "exterior_details":
            exterior_details,

        "interior_details":
            interior_details,

        "city_checked":
            1 if city else 0,

        "province":
            province,

        "property_status":
            specifications.get(
                "Estado",
                [None]
            )[0],

        "neighbourhood":
            neighbourhood,

        "commercial_units":
            None,

        "admin_price":
            admin_price
    }

    return property_details


def save_to_csv(property_details):

    existing_links = set()

    try:

        with open(
            OUTPUT_FILE,
            "r",
            encoding="utf-8"
        ) as file:

            reader = csv.DictReader(file)

            for row in reader:

                existing_links.add(
                    row["link"]
                )

    except FileNotFoundError:

        pass

    # Check if property already exists

    if property_details["link"] in existing_links:

        print(
            "Already exists, skipping:",
            property_details["title"]
        )

        return

    file_exists = False

    try:

        with open(
            OUTPUT_FILE,
            "r",
            encoding="utf-8"
        ):

            file_exists = True

    except FileNotFoundError:

        file_exists = False

    fieldnames = property_details.keys()

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

        row = property_details.copy()

        row["img_src"] = json.dumps(
            row["img_src"],
            ensure_ascii=False
        )

        row["amneties"] = json.dumps(
            row["amneties"],
            ensure_ascii=False
        )

        row["bedrooms"] = json.dumps(
            row["bedrooms"],
            ensure_ascii=False
        )

        row["full_baths"] = json.dumps(
            row["full_baths"],
            ensure_ascii=False
        )

        row["property_details"] = json.dumps(
            row["property_details"],
            ensure_ascii=False
        )

        writer.writerow(row)


def main():

    # Get current COP to USD exchange rate
    cop_usd_rate = get_cop_usd_rate()

    print("Getting properties...")

    products, total_records = get_properties(
        0,
        35
    )

    print(
        "Total properties:",
        total_records
    )

    for product in products:

        property_details = create_property_details(
            product,
            cop_usd_rate
        )

        save_to_csv(
            property_details
        )

        print(
            "Saved:",
            property_details["property_type"],
            "-",
            property_details["title"]
        )


if __name__ == "__main__":

    main()
