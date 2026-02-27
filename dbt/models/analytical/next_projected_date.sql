{{
    config(
        materialized='table'
    )
}}

with transaction_frequency as (
    select * from {{ ref('transaction_frequency') }}
),

projected_dates as (

    select
        date,
        last_date,
        days_between,
        months_between,
        category_name,
        amount,
        amount_spent,
        avg(days_between) over (partition by category_name) as avg_days_between,
        date + (avg(days_between) over (partition by category_name) || ' days')::interval as next_projected_date,
        rank() over (partition by category_name order by date desc) as rnk
    from transaction_frequency
    where date >= CURRENT_DATE - INTERVAL '4 years'

)

select *
from projected_dates
where rnk = 1