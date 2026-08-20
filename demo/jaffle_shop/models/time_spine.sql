{{ config(materialized='table') }}

select cast(date_value as date) as date_day
from generate_series(
    date '2010-01-01',
    date '2030-12-31',
    interval 1 day
) as dates(date_value)

