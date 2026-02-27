{{
    config(
        materialized='table'
    )
}}

select
	date,
    year,
	date_trunc('month', date) as first_day_of_month,
	amount_spent,
	payee_name,
	category_name,
	account_name,
    lag(amount_spent, 1, null) over (partition by payee_name order by date) as previous_month_amount,
    (amount_spent-lag(amount_spent, 1, null) over (partition by payee_name order by date))/lag(amount_spent, 1, null) over (partition by payee_name order by date) as mom_change,
	lag(amount_spent, 12, null) over (partition by payee_name order by date) as previous_year_amount,
	(amount_spent-lag(amount_spent, 12, null) over (partition by payee_name order by date))/lag(amount_spent, 12, null) over (partition by payee_name order by date) as yoy_change
from {{ ref('transactions') }}
where {{ is_utilities('category_name') }}