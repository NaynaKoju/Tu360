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
        params=params
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


def get_specification_value(specifications, field):

    values = specifications.get(
        field,
        []
    )

    if values:

        return values[0]

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

    # First look for private area

    match = re.search(
        r"Área\s+privada:\s*(\d+(?:[.,]\d+)?)\s*m²",
        description,
        re.IGNORECASE
    )

    if match:

        return match.group(1)

    # Then look for general area

    match = re.search(
        r"Área(?:\s+construida)?\s*:\s*(\d+(?:[.,]\d+)?)\s*m²",
        description,
        re.IGNORECASE
    )

    if match:

        return match.group(1)

    return None


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


def create_property_details_list(
    property_data,
    specifications,
    property_type,
    price,
    area
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
            "value": None
        }
    ]

    return property_details


def create_property_details(property_data):

    specifications = get_specifications(
        property_data
    )

    images = get_images(
        property_data
    )

    prices = get_prices(
        property_data
    )

    area = get_area(
        property_data.get("description")
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

    admin_price = specifications.get(
        "Valor administración",
        [None]
    )[0]

    if admin_price:

        try:

            admin_price = int(admin_price)

        except ValueError:

            pass

    if len(prices) == 1:

        price = prices[0]

    else:

        price = prices

    # Create property_details in the required format

    property_details_list = create_property_details_list(
        property_data,
        specifications,
        property_type,
        price,
        area
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
            "sales",

        "phone":
            phone,

        "price":
            price,

        "price_unit":
            None,

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
            specifications.get("Habitaciones"),

        "full_baths":
            specifications.get("Baños"),

        "property_type":
            property_type,

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
            product
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