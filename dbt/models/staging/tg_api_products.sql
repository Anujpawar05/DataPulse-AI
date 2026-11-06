{{ config(materialized='view') }}

SELECT
    id,
    TRIM(title) AS title,
    TRIM(description) AS description,
    TRIM(category) AS category,
    CAST(price AS NUMERIC) AS price,
    discountPercentage,
    rating,
    stock,
    tags,
    brand,
    sku,
    weight,
    dimensions,
    warrantyInformation,
    shippingInformation,
    availabilityStatus,
    reviews,
    returnPolicy,
    minimumOrderQuantity,
    meta,
    images,
    thumbnail
FROM {{ source('datapulse_raw', 'api_products') }}