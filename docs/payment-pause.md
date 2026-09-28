# Temporary Mobile Money payment pause

Payment initiation is disabled by default while reports of payment prompts without
the phone owner's consent are investigated.

`MOMO_PAYMENT_INITIATION_ENABLED=false` (or leaving the variable unset) pauses:

- All methods and currency query values at `/sponsorship/initiate/`.
- The mobile/public API at `/api/v1/payments/mobile-money/initiate/`.
- Direct calls to the production `request_to_pay` helper.

The web route returns a responsive maintenance page with HTTP 503 and no payment
form or payment scripts. The API returns HTTP 503 with the stable code
`payment_initiation_paused`. Both responses prohibit caching. No new provider
token requests, payment prompts, or transaction records are created by the paused
initiation routes. Existing status checks and callbacks continue processing.

## Deployment verification

Deploy this code to the web service and verify that a GET of
`/sponsorship/initiate/?currency=UGX` returns HTTP 503 and the maintenance page.
An empty JSON POST to the API should return `payment_initiation_paused`.
Do not send real phone numbers or live test payment prompts.

## Reopening

This pause does not fix or verify the underlying consent problem. Keep the flag
disabled until consent safeguards have been implemented and reviewed across both
the web and mobile API flows. After that review, explicitly set
`MOMO_PAYMENT_INITIATION_ENABLED=true` and redeploy. There is no automatic expiry.
Set it back to `false` and redeploy to pause again.
