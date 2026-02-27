{{
    config(
        materialized='table'
    )
}}

with spend as (

    select
        first_day_of_month,
        year_month,
        sum(amount_spent) as total_spend
    from {{ ref('spend') }}
    group by first_day_of_month, year_month

)

select * from spend