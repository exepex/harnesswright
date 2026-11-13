---
id: P-order-retry
status: approved
---

## Goal

Order calls survive short network failures.

## Steps

1. Retry the payment call with backoff.
2. Log each retry with the order id.
3. Show the customer a clear message when all tries fail.
