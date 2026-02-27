{{
    config(
        materialized='table'
    )
}}

with transactions as (
    select
        account_id,
        account_name,
        payee_name,
        category_name,
        date,
        amount_spent,
        deleted,
        transaction_type
    from {{ ref('transactions') }}
    where 
        deleted = false
        and transaction_type != 'transfer'  -- Exclude transfers
),

card_metrics as (
    select
        account_id,
        account_name,
        sum(amount_spent) as total_lifetime_spend,
        count(*) as total_lifetime_transaction_count,
        max(date) as last_used_date,
        min(date) as first_used_date,
        -- Calculate days since last use
        current_date - max(date) as days_since_last_use
    from transactions
    group by 
        account_id,
        account_name
),

payee_spend as (
    select
        account_id,
        account_name,
        payee_name,
        sum(amount_spent) as payee_total_spend
    from transactions
    where payee_name is not null
    group by 
        account_id,
        account_name,
        payee_name
),

top_payee_per_account as (
    select
        account_id,
        account_name,
        payee_name as top_payee_name,
        payee_total_spend as top_payee_spend,
        row_number() over (
            partition by account_id, account_name 
            order by payee_total_spend desc
        ) as rn
    from payee_spend
),

payee_transaction_count as (
    select
        account_id,
        account_name,
        payee_name,
        count(*) as payee_transaction_count
    from transactions
    where payee_name is not null
    group by 
        account_id,
        account_name,
        payee_name
),

top_payee_by_count_per_account as (
    select
        account_id,
        account_name,
        payee_name as top_payee_by_count_name,
        payee_transaction_count as top_payee_by_count_transactions,
        row_number() over (
            partition by account_id, account_name 
            order by payee_transaction_count desc
        ) as rn
    from payee_transaction_count
),

last_transaction_per_account as (
    select
        account_id,
        account_name,
        payee_name as last_transaction_payee_name,
        amount_spent as last_transaction_amount,
        date as last_transaction_date,
        row_number() over (
            partition by account_id, account_name 
            order by date desc
        ) as rn
    from transactions
),

current_month_metrics as (
    select
        account_id,
        account_name,
        sum(amount_spent) as current_month_spend,
        count(*) as current_month_transaction_count
    from transactions
    where 
        date_trunc('month', date) = date_trunc('month', current_date)
    group by 
        account_id,
        account_name
),

category_spend_all_time as (
    select
        account_id,
        account_name,
        category_name,
        sum(amount_spent) as category_total_spend
    from transactions
    where category_name is not null
    group by 
        account_id,
        account_name,
        category_name
),

top_category_all_time as (
    select
        account_id,
        account_name,
        category_name as top_category_all_time,
        category_total_spend as top_category_all_time_spend,
        row_number() over (
            partition by account_id, account_name 
            order by category_total_spend desc
        ) as rn
    from category_spend_all_time
),

category_spend_current_month as (
    select
        account_id,
        account_name,
        category_name,
        sum(amount_spent) as category_month_spend
    from transactions
    where 
        category_name is not null
        and date_trunc('month', date) = date_trunc('month', current_date)
    group by 
        account_id,
        account_name,
        category_name
),

top_category_current_month as (
    select
        account_id,
        account_name,
        category_name as top_category_current_month,
        category_month_spend as top_category_current_month_spend,
        row_number() over (
            partition by account_id, account_name 
            order by category_month_spend desc
        ) as rn
    from category_spend_current_month
)

select 
    cm.account_id,
    cm.account_name,
    cm.total_lifetime_spend,
    cm.total_lifetime_transaction_count,
    cm.last_used_date,
    cm.first_used_date,
    cm.days_since_last_use,
    tp.top_payee_name,
    tp.top_payee_spend,
    tpc.top_payee_by_count_name,
    tpc.top_payee_by_count_transactions,
    lt.last_transaction_payee_name,
    lt.last_transaction_amount,
    lt.last_transaction_date,
    coalesce(cmm.current_month_spend, 0) as current_month_spend,
    coalesce(cmm.current_month_transaction_count, 0) as current_month_transaction_count,
    tcat_all.top_category_all_time,
    tcat_all.top_category_all_time_spend,
    tcat_month.top_category_current_month,
    tcat_month.top_category_current_month_spend
from card_metrics cm
left join top_payee_per_account tp
    on cm.account_id = tp.account_id
    and cm.account_name = tp.account_name
    and tp.rn = 1
left join top_payee_by_count_per_account tpc
    on cm.account_id = tpc.account_id
    and cm.account_name = tpc.account_name
    and tpc.rn = 1
left join last_transaction_per_account lt
    on cm.account_id = lt.account_id
    and cm.account_name = lt.account_name
    and lt.rn = 1
left join current_month_metrics cmm
    on cm.account_id = cmm.account_id
    and cm.account_name = cmm.account_name
left join top_category_all_time tcat_all
    on cm.account_id = tcat_all.account_id
    and cm.account_name = tcat_all.account_name
    and tcat_all.rn = 1
left join top_category_current_month tcat_month
    on cm.account_id = tcat_month.account_id
    and cm.account_name = tcat_month.account_name
    and tcat_month.rn = 1
order by cm.last_used_date desc
