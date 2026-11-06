{{ config(materialized='view') }}

SELECT
    id,
    TRIM(firstName) AS first_name,
    TRIM(lastName) AS last_name,
    LOWER(TRIM(email)) AS email,
    username,
    age,
    gender,
    address
FROM {{ source('datapulse_raw', 'api_users') }}