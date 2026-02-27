{{
    config(
        materialized='table'
    )
}}

with income as (

    select
        first_day_of_month,
        year_month,
        sum(amount) as total_income
    from {{ ref('income') }}

    group by first_day_of_month, year_month

)

select * from income