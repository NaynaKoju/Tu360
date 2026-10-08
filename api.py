import requests
import csv
import logging
import json
import base64


# Output file
OUTPUT_FILE = "./csv_files/api_urls.csv"


# API URL
API_URL = "https://inmobiliariotu360.bancolombia.com/_v/segment/graphql/v1"


# Configuring logging
logging.basicConfig(
    filename="../scraper_logs/TU360api.log",
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

logger = logging.getLogger(__name__)


# Function to get properties from the API
def get_properties(from_value, to_value):

    # Variables required by the API
    variables = {
        "skusFilter": "ALL",
        "simulationBehavior": "default",
        "installmentCriteria": "MAX_WITHOUT_INTEREST",
        "productOriginVtex": False,

        "map": "category-1,ciudad",
        "query": "venta/medellin",

        "orderBy": "OrderByTopSaleDESC",

        # Pagination values
        "from": from_value,
        "to": to_value,

        # Filters used by the website
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

        # Additional values found in the browser request
        "operator": "and",
        "fuzzy": "0",

        "searchState": None,
        "facetsBehavior": "Static",
        "categoryTreeBehavior": "default",
        "withFacets": False
    }


    # Convert variables into JSON
    variables_json = json.dumps(variables)


    # Convert JSON into Base64
    variables_base64 = base64.b64encode(
        variables_json.encode()
    ).decode()


    # Parameters required by the API
    params = {
        "workspace": "master",
        "maxAge": "short",
        "appsEtag": "remove",
        "domain": "store",
        "locale": "es-CO",

        "__bindingId": (
            "f91c6084-ca4b-4afa-9b2d-7d09efca9e7c"
        ),

        "operationName": "productSearchV3",

        "variables": "{}",

        "extensions": json.dumps({
            "persistedQuery": {
                "version": 1,

                "sha256Hash": (
                    "a96c5ed03ef513568c34b63a4bf8da055ea6296293ee02eadb56e2e895eaffbc"
                ),

                "sender": "vtex.store-resources@0.x",

                "provider": "vtex.search-graphql@0.x"
            },

            "variables": variables_base64
        })
    }


    # Send GET request to the API
    response = requests.get(
        API_URL,
        params=params
    )


    # Check if the request was successful
    response.raise_for_status()


    # Convert JSON response into Python dictionary
    data = response.json()


    # Get product search data
    product_search = data["data"]["productSearch"]


    # Get total number of matching records
    total_records = product_search["recordsFiltered"]


    # Get products from the response
    products = product_search["products"]


    # Log successful request
    logger.info(
        "From %s to %s: %s products collected",
        from_value,
        to_value,
        len(products)
    )


    # Return products and total number of records
    return products, total_records


# Function to extract URLs from products
def extract_urls(products):

    urls = []


    # Go through every product
    for product in products:

        # Get the relative product link
        link = product.get("link")


        # Make sure a link exists
        if link:

            # Add the website domain
            full_url = (
                "https://inmobiliariotu360.bancolombia.com"
                + link
            )


            # Add URL to the list
            urls.append(full_url)


    return urls


# Function to save URLs to CSV
def save_urls(urls):

    with open(
        OUTPUT_FILE,
        "w",
        newline="",
        encoding="utf-8"
    ) as file:

        writer = csv.writer(file)


        # Write column name
        writer.writerow(["url"])


        # Write URLs
        for url in urls:

            writer.writerow([url])


    # Log total URLs
    logger.info(
        "Total URLs saved: %s",
        len(urls)
    )


    # Log output file
    logger.info(
        "URLs saved to %s",
        OUTPUT_FILE
    )


# Main function
def main():

    all_urls = []


    # Starting position
    from_value = 0


    # Number of products requested in each API request
    batch_size = 36


    # Total number of records
    total_records = None


    while True:

        # Calculate ending position
        to_value = from_value + batch_size - 1


        # Get products from API
        products, total_records = get_properties(
            from_value,
            to_value
        )


        # Display total number of records
        print(
            f"Total records: {total_records}"
        )


        # Stop if API returns no products
        if not products:
            break


        # Extract URLs
        urls = extract_urls(products)


        # Add URLs to main list
        all_urls.extend(urls)


        # Display progress
        print(
            f"From {from_value} to {to_value}: "
            f"{len(urls)} URLs collected"
        )


        # Log progress
        logger.info(
            "From %s to %s: %s URLs collected",
            from_value,
            to_value,
            len(urls)
        )


        # Calculate how many records have been requested
        records_processed = from_value + len(products)


        # Stop when we have reached all available records
        if records_processed >= total_records:
            break


        # Move to the next batch
        from_value += batch_size


    # Remove duplicate URLs
    all_urls = list(dict.fromkeys(all_urls))


    # Save all URLs
    save_urls(all_urls)


    # Display total unique URLs
    print(
        f"Total unique URLs: {len(all_urls)}"
    )


    # Log total unique URLs
    logger.info(
        "Total unique URLs: %s",
        len(all_urls)
    )


    # Log completion
    logger.info(
        "API scraping completed successfully"
    )

# def main():

#     products, total_records = get_properties(0, 35)

#     property_data = products[0]

#     print("\nPRODUCT NAME:")
#     print(property_data.get("productName"))

#     print("\nLINK:")
#     print(property_data.get("link"))

#     print("\nDESCRIPTION:")
#     print(property_data.get("description"))

#     print("\nPRODUCT REFERENCE:")
#     print(property_data.get("productReference"))

#     print("\nPRICE RANGE:")
#     print(property_data.get("priceRange"))

#     print("\nSPECIFICATION GROUPS:")
#     print(property_data.get("specificationGroups"))

#     print("\nPROPERTIES:")
#     print(property_data.get("properties"))
 #checking images and prices
    # products, total_records = get_properties(0, 35)

    # property_data = products[0]

    # print("\nIMAGES:")
    # for item in property_data.get("items", []):
    #     for image in item.get("images", []):
    #         print(image.get("imageUrl"))

    # print("\nPRICES:")
    # for item in property_data.get("items", []):
    #     for seller in item.get("sellers", []):
    #         offer = seller.get("commertialOffer", {})
    #         print(offer.get("Price"))



# Run main function
if __name__ == "__main__":
    main()