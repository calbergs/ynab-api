{{
    config(
        materialized='table'
    )
}}

select
	date,
	lead(date) over (partition by category_name order by date desc) as last_date,
	date - lead(date) over (partition by category_name order by date desc) as days_between,
	(
		EXTRACT(YEAR  FROM AGE(date, LEAD(date) OVER (PARTITION BY category_name ORDER BY date DESC))) * 12
		+ EXTRACT(MONTH FROM AGE(date, LEAD(date) OVER (PARTITION BY category_name ORDER BY date DESC)))
		+ EXTRACT(DAY   FROM AGE(date, LEAD(date) OVER (PARTITION BY category_name ORDER BY date DESC))) / 30.4375
) AS months_between,
	category_name,
	amount,
	amount_spent
from {{ ref('transactions') }}
where (category_name ilike '%haircut%'
or category_name ilike '%gas%')
and date >= '2020-01-01'