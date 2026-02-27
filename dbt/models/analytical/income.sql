{{
    config(
        materialized='table'
    )
}}

with income as (

    select
        id,
        date,
        first_day_of_month,
        year_month,
        payee_name,
        import_payee_name,
        amount,
        amount_spent,
        cleared,
        memo,
        category_name,
        account_name,
        transaction_type,
        load_timestamp_ct
    from {{ ref('transactions') }}
    where category_name ilike '%ready to assign%'
    and payee_name != 'Starting Balance'
    and transaction_type != 'transfer'

)

select * from income