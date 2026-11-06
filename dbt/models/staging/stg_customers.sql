{{ config(materialized='view') }}

SELECT
    customer_id,
    TRIM(full_name) AS full_name,
    LOWER(TRIM(email)) AS email,
    TRIM(city) AS city,
    TRIM(state) AS state,
    TRIM(country) AS country,
    registration_date,
    created_at

FROM {{ source('datapulse_raw', 'customers') }}