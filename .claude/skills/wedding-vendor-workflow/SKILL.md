---
name: wedding-vendor-workflow
description: Work with wedding vendors — create vendors, add quote line items, update status, upload files, and manage deposits. Use when adding, editing, or querying wedding vendor data.
metadata:
  author: kiro
  version: 1.0.0
---

## Context

The wedding module's vendor system lives in `app/backend/app/api/wedding.py` and is backed by three tables:
- `wedding_vendors` — main vendor record
- `vendor_quote_items` — individual line items that make up a vendor's quote
- `vendor_files` — file attachments (stored on disk, referenced by DB row)

All wedding API routes are prefixed with `/api/wedding`.

**Vendor status values:** `not_contacted`, `contacted`, `meeting_scheduled`, `quote_received`, `booked`, `declined`

## Vendor data model

```
wedding_vendors:
  id, name, category, contact_name, phone,
  price_quoted, what_included, status,
  deposit_amount, deposit_paid_date, notes,
  instagram_url, facebook_url, location,
  inclusions, created_at

vendor_quote_items:
  id, vendor_id (FK), description, quantity,
  unit_price, apply_vat (bool), sort_order, created_at
```

## Workflow: Creating a complete vendor record

### Step 1: Create the vendor

`POST /api/wedding/vendors`

Required fields: `name`, `category`
Optional: `contact_name`, `phone`, `price_quoted`, `status`, `notes`, `instagram_url`, `facebook_url`, `location`

```json
{
  "name": "Vendor Name",
  "category": "Photography",
  "contact_name": "Jane",
  "phone": "050-0000000",
  "status": "contacted",
  "notes": "Any notes"
}
```

Returns the full vendor object including the auto-generated `id`.

### Step 2: Add quote line items

`POST /api/wedding/vendors/{vendor_id}/quote-items`

Each line item is a component of the vendor's total price:

```json
{
  "description": "5-hour coverage",
  "quantity": 1,
  "unit_price": 5000,
  "apply_vat": true,
  "sort_order": 0
}
```

Add as many line items as needed. The total quote is the sum of all items (with VAT applied where `apply_vat=true`).

### Step 3: Update vendor status

`PATCH /api/wedding/vendors/{vendor_id}`

```json
{ "status": "booked" }
```

### Step 4: Record a deposit

`PATCH /api/wedding/vendors/{vendor_id}`

```json
{
  "deposit_amount": 1500,
  "deposit_paid_date": "2025-03-15"
}
```

### Step 5: Upload files (optional)

`POST /api/wedding/vendors/{vendor_id}/files` — multipart form upload
`GET /api/wedding/vendors/{vendor_id}/files` — list files
`GET /api/wedding/vendors/{vendor_id}/files/{file_id}/download` — download a file
`DELETE /api/wedding/vendors/{vendor_id}/files/{file_id}` — delete a file

## Workflow: Adding a new vendor feature in code

When adding a new field to `wedding_vendors` or a new vendor sub-resource:

1. **DB**: Add column via inline migration in `db.py` — use the `db-migration` skill
2. **API**: Add to the relevant PATCH handler in `app/backend/app/api/wedding.py`
3. **Schema**: Wedding endpoints currently use `dict` bodies (not Pydantic schemas for all endpoints) — check the existing handler style before adding a schema

## Key API endpoints reference

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/wedding/vendors` | List all vendors |
| POST | `/api/wedding/vendors` | Create vendor |
| GET | `/api/wedding/vendors/{id}` | Get single vendor |
| PATCH | `/api/wedding/vendors/{id}` | Update vendor |
| DELETE | `/api/wedding/vendors/{id}` | Delete vendor |
| GET | `/api/wedding/vendors/{id}/quote-items` | List quote items |
| POST | `/api/wedding/vendors/{id}/quote-items` | Add quote item |
| PATCH | `/api/wedding/vendors/{id}/quote-items/{item_id}` | Update quote item |
| DELETE | `/api/wedding/vendors/{id}/quote-items/{item_id}` | Delete quote item |
| POST | `/api/wedding/vendors/{id}/files` | Upload file |
| GET | `/api/wedding/vendors/{id}/files` | List files |
| DELETE | `/api/wedding/vendors/{id}/files/{file_id}` | Delete file |

## Checklist when adding a new vendor

- [ ] Vendor created with correct `category` value (free-text, used for grouping in UI)
- [ ] Quote items added for all known pricing components
- [ ] Status set to current stage of negotiation
- [ ] Deposit recorded if paid
- [ ] Any files (contracts, quotes) uploaded

## Common pitfalls

- `price_quoted` on the vendor is a summary/override field; the computed total from `vendor_quote_items` is the detailed breakdown. Keep them in sync manually.
- `apply_vat` on quote items is a boolean stored as `0/1` in SQLite — pass `true`/`false` in JSON
- File uploads are stored on disk relative to the backend; in Docker, files are inside the container. Back up using the backup API (`POST /api/backup/create`) before restoring the DB, or files will be orphaned.
- Deleting a vendor cascades to quote items but **not** to files on disk — call `DELETE /api/wedding/vendors/{id}/files/{file_id}` for each file before deleting the vendor, or clean up orphaned files manually.
