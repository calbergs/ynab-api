{{
    config(
        materialized='table'
    )
}}

with transactions as (

	select
		id,
		date,
		date_trunc('month', date) as first_day_of_month,
		date_trunc('week', date) as first_day_of_week,
		to_char(date, 'YYYY-MM') AS year_month,
		extract(year from date) as year,
		extract(month from date) as month,
		extract(day from date) as day,
		to_char(date, 'Day') as day_of_week,
		cast(amount / 1000.0 as decimal(18,2)) as amount,
		-cast(amount / 1000.0 as decimal(18,2)) as amount_spent,
		approved,
		cleared,
		debt_transaction_type,
		deleted,
		flag_color,
		flag_name,
		import_id,
		import_payee_name,
		import_payee_name_original,
		matched_transaction_id,
		memo,
		payee_id,
		payee_name,
		category_id,
		category_name,
		account_id,
		account_name,
		subtransactions,
		transfer_account_id,
		transfer_transaction_id,
		case when payee_name ilike 'Transfer%' then 'transfer'
		 	 when payee_name ilike '%interest%' or payee_name ilike '%Sav Increase Int Paid%' then 'interest'
		else 'non-transfer' end as transaction_type,
		case
			when {{ is_recurring_fee('category_name') }} then 'recurring fees'
			else 'other'
    	end as fee_category,
		case
			when {{ is_subscription('category_name') }} then 'subscription'
			else 'other'
    	end as subscription_category,
		case when category_name ilike '%💳%' then 'credit card fee' else 'other' end as credit_card_fee_category,
		load_timestamp AT TIME ZONE 'America/Chicago' as load_timestamp_ct
	from {{ ref('stg_ynab_transactions') }}
)

select * from transactions