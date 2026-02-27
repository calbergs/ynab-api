{{
    config(
        materialized='table'
    )
}}

with weekly_spend as (
    select
        first_day_of_week,
        sum(amount_spent) as total_spend,
        lead(sum(amount_spent)) over (order by first_day_of_week desc) as previous_week_spend,
        case when sum(amount_spent)=0 then 0 else (sum(amount_spent)- lead(sum(amount_spent)) over (order by first_day_of_week desc))/sum(amount_spent) end as pct_change
    from {{ ref('spend') }}
    group by first_day_of_week
),

payee_weekly_spend as (
    select
        first_day_of_week,
        payee_name,
        sum(amount_spent) as payee_week_spend
    from {{ ref('spend') }}
    where payee_name is not null
    group by 
        first_day_of_week,
        payee_name
),

top_payee_per_week as (
    select
        first_day_of_week,
        payee_name as top_payee_name,
        payee_week_spend as top_payee_spend,
        row_number() over (
            partition by first_day_of_week 
            order by payee_week_spend desc
        ) as rn
    from payee_weekly_spend
)

select 
    ws.first_day_of_week,
    ws.total_spend,
    ws.previous_week_spend,
    ws.pct_change,
    tp.top_payee_name,
    tp.top_payee_spend
from weekly_spend ws
left join top_payee_per_week tp
    on ws.first_day_of_week = tp.first_day_of_week
    and tp.rn = 1
order by ws.first_day_of_week desc