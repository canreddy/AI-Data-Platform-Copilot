with payments as (
    select * from {{ ref('stg_payments') }}
),

orders as (
    select * from {{ ref('stg_orders') }}
),

final as (
    select
        payments.payment_id,
        payments.order_id,
        orders.customer_id,
        orders.order_date,
        orders.status as order_status,
        payments.payment_method,
        payments.amount
    from payments
    inner join orders on payments.order_id = orders.order_id
)

select * from final

