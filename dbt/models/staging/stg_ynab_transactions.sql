{{
    config(
        materialized='table'
    )
}}

with source_ynab_transactions as (
    select * from {{ source('ynab', 'ynab_transactions') }}
),

-- YNAB (and bank imports) often use curly/smart apostrophes (U+2018/U+2019).
-- Normalize to ASCII ' before matching so corrections persist across reloads.
payee_for_match as (
    select
        *,
        replace(replace(payee_name, '’', ''''), '‘', '''') as payee_name_ascii
    from source_ynab_transactions
),

-- Normalize payee names so corrections persist when raw data is reloaded from the API.
-- Correction rules live in macros/correct_payee_name.sql (gitignored, personal to this instance).
payee_normalized as (
    select
        *,
        {{ correct_payee_name('payee_name_ascii') }} as payee_name_normalized
    from payee_for_match
),

final as (
    select
        id, date, amount, approved, cleared, debt_transaction_type, deleted,
        flag_color, flag_name, import_id, import_payee_name, import_payee_name_original,
        matched_transaction_id, memo, payee_id,
        payee_name_normalized as payee_name,
        category_id, category_name, account_id, account_name,
        subtransactions, transfer_account_id, transfer_transaction_id, load_timestamp
    from payee_normalized
)

select * from final
where (deleted is null or deleted = false)
and (cleared = 'cleared' or cleared = 'reconciled')
