{{
    config(
        materialized='table'
    )
}}

with income as (

    select * from {{ ref('rpt_income') }}

),

spend as (

    select * from {{ ref('rpt_spend') }}

)

select
    income.first_day_of_month,
    income.year_month,
    income.total_income,
    spend.total_spend,
    income.total_income-spend.total_spend as total_savings,
    (income.total_income-spend.total_spend)/income.total_income as savings_rate,
    case when income.total_income-spend.total_spend >0 then 'saved' else null end as savings_status
from income
left join spend
on income.year_month = spend.year_month