# Website Wallet Top-up API

Base URL: your Odoo host (same as other `/v1/...` portal APIs)

Auth: `Authorization: Bearer <api_key>` (same as existing portal login API key)

---

## 1) List payment brands

`GET /v1/wallet/topup/brands`

Response `200`:

```json
{
  "result": {
    "code": 200,
    "brands": [
      {"code": "visa", "name": "Visa", "hyperpay_brands": "VISA MASTER"},
      {"code": "mada", "name": "Mada", "hyperpay_brands": "MADA"},
      {"code": "applepay", "name": "Apple Pay", "hyperpay_brands": "APPLEPAY"},
      {"code": "googlepay", "name": "Google Pay", "hyperpay_brands": "GOOGLEPAY"},
      {"code": "stc", "name": "STC Pay", "hyperpay_brands": "STC_PAY"}
    ]
  }
}
```

Use `hyperpay_brands` in the HyperPay widget `data-brands`.

---

## 2) Prepare top-up

`POST /v1/wallet/topup/prepare`  
`Content-Type: application/json`

Body:

```json
{
  "amount": 150,
  "payment_brand": "visa"
}
```

`payment_brand` allowed values: `visa` | `mada` | `applepay` | `googlepay` | `stc`

Success:

```json
{
  "jsonrpc": "2.0",
  "id": null,
  "result": {
    "code": 200,
    "message": "top-up prepared",
    "topup_id": 12,
    "topup_name": "WT/00012",
    "amount": 150.0,
    "payment_brand": "visa",
    "wallet_balance": 0.0
  }
}
```

---

## 3) Confirm top-up (after HyperPay success)

`POST /v1/wallet/topup/confirm`

Body:

```json
{
  "topup_id": 12,
  "transaction_id": "hyperpay_payment_id_or_checkout_id"
}
```

Success:

```json
{
  "result": {
    "code": 200,
    "message": "wallet topped up",
    "topup_id": 12,
    "topup_name": "WT/00012",
    "amount": 150.0,
    "payment_brand": "visa",
    "transaction_id": "hyperpay_payment_id_or_checkout_id",
    "wallet_balance": 150.0,
    "payment_id": 55,
    "exchange_log_id": 99
  }
}
```

If called twice with same done request → `message: "already processed"` (idempotent).

---

## Website flow

1. User enters amount + selects brand  
2. `GET /v1/keys/hyperpay` (existing)  
3. `POST /v1/wallet/topup/prepare`  
4. Open HyperPay widget with matching `data-brands`  
5. On success → `POST /v1/wallet/topup/confirm` with HyperPay transaction id  
6. Refresh profile / show new `wallet_balance`

---

## Notes

- Wallet is credited **only** after confirm (1 SAR = 1 wallet point).  
- Creates `loyalty.exchange.log` line (In) + `account.payment`.  
- Backend menu: **Sales → Wallet Top-up → Website Top-ups**
