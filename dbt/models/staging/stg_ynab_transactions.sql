{{
    config(
        materialized='table'
    )
}}

with source_ynab_transactions as (
    select * from {{ source('ynab', 'ynab_transactions') }}
),

final as (
    select * from source_ynab_transactions
)

select * from final