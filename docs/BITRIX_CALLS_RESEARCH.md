# Bitrix Calls Phone Number Research

> **Date:** 2026-03-13
> **Status:** ✅ SOLVED
> **Test Client:** ФФ-4405 (Алексей)

---

## Problem

**Symptoms:**
- 66 calls in database for ФФ-4405
- All `phone_number` fields are NULL
- No way to see which phone was called

**User Impact:**
- Cannot identify call direction/outcome
- Cannot correlate multiple phone numbers
- Missing critical business data

---

## Root Cause Analysis

### Investigation Steps:

1. **Checked Database:**
```sql
SELECT id, bitrix_call_id, phone_number FROM bitrix_calls
WHERE diffy_lead_id = 'ФФ-4405';
```
Result: `bitrix_call_id` = NULL, `phone_number` = NULL

2. **Checked Bitrix API:**
```bash
curl -X POST "https://bitrix24.ff-platform.ru/rest/1/fhh009wpvmby0tn6/crm.activity.list" \
  -d '{"filter":{"OWNER_TYPE_ID":3,"OWNER_ID":5723,"TYPE_ID":2}}'
```

Response structure:
```json
{
  "ID": "150513",
  "TYPE_ID": "2",
  "SETTINGS": [],  ← EMPTY! No CALL_ID
  "COMMUNICATIONS": [
    {
      "TYPE": "PHONE",
      "VALUE": "+79135379385"  ← PHONE NUMBER HERE!
    }
  ]
}
```

### Key Findings:

1. **`SETTINGS.CALL_ID` is EMPTY** for old calls (pre-June 2025)
   - VoxImplant enrichment fails (no link between activity and voximplant)
   - `bitrix_call_id` cannot be populated from `crm.activity.list`

2. **Phone Number is in `COMMUNICATIONS[0].VALUE`**
   - Available in `crm.activity.list` response
   - Not extracted by original code

3. **`ON CONFLICT DO UPDATE` doesn't work**
   - PostgreSQL UPDATE on conflict doesn't update NULL → value
   - Requires separate enrichment step

---

## Solution

### Changes Made:

#### 1. **Extract phone_number from COMMUNICATIONS** (`bitrix_sync.py:353-359`)

```python
# Extract phone number from COMMUNICATIONS (more reliable than voximplant)
communications = activity.get("COMMUNICATIONS") or []
phone_number = ""
if communications and len(communications) > 0:
    comm = communications[0]
    if comm.get("TYPE") == "PHONE":
        phone_number = comm.get("VALUE") or ""
```

#### 2. **Add to INSERT statement** (`bitrix_sync.py:365-382`)

```python
cur.execute(
    """
    INSERT INTO bitrix_calls
        (bitrix_activity_id, bitrix_call_id, bitrix_lead_id, diffy_lead_id,
         direction, phone_number, call_date, responsible_id, responsible_name,
         call_duration, transcript_status)
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'no_record')
    ON CONFLICT (bitrix_activity_id) DO UPDATE SET
        phone_number = EXCLUDED.phone_number
    """,
    (..., phone_number, ...)
)
```

#### 3. **Separate Enrichment Step** (for existing records)

```python
# Update existing NULL phone_numbers from activities
for activity in activities:
    phone = extract_phone_from_communications(activity)
    cur.execute(
        "UPDATE bitrix_calls SET phone_number = %s WHERE bitrix_activity_id = %s",
        (phone, activity["ID"])
    )
```

---

## Test Results (ФФ-4405)

### Before Fix:
```
phone_number | COUNT
-------------+-------
 NULL         |    66
```

### After Fix:
```
phone_number    | COUNT
----------------+-------
 +79099358635    |    25
 +79135379385    |    41
```

**Total: 66 calls with phone numbers populated** ✅

---

## Files Modified

1. **`app/tasks/bitrix_sync.py`:**
   - Added phone_number extraction from COMMUNICATIONS (lines 353-359)
   - Added phone_number to INSERT statement (line 367)
   - Added ON CONFLICT UPDATE (line 371)
   - Added phone_number to voximplant enrichment (lines 110-118, 123-135)

2. **Commits:**
   - `2a90924` - save phone_number from voximplant (for new calls)
   - `f4858dc` - extract phone_number from crm.activity COMMUNICATIONS

---

## Technical Notes

### Why ON CONFLICT Doesn't Work

Postgres `ON CONFLICT DO UPDATE` has limitations:
- Won't update NULL → value if the conflicting row has NULL
- Requires explicit `IS DISTINCT FROM` clause for proper behavior

**Better approach:** Separate enrichment step after initial sync

### VoxImplant Fallback

For NEW calls (post-June 2025):
- `SETTINGS.CALL_ID` may be present
- VoxImplant enrichment will populate both `phone_number` AND `record_url`
- Transcription can proceed automatically

For OLD calls (pre-June 2025):
- `SETTINGS` is empty
- `phone_number` from COMMUNICATIONS is the only source
- `record_url` is NULL (recordings deleted after 3 months)

---

## Next Steps

1. **Full resync for all clients:**
   ```python
   # Clear phone_numbers
   UPDATE bitrix_calls SET phone_number = NULL;

   # Re-sync
   from app.tasks.bitrix_sync import sync_calls
   sync_calls(client, conn, all_leads)
   ```

2. **Verify transcription:**
   - Old calls: phone_number populated, no recording (expected)
   - New calls: phone_number + recording URL (ready for Whisper)

3. **Add phone_number to summary generation:**
   - Include in summary text: "Звонок с +79099358635"
   - Filter by phone in RAG queries

---

**Last Updated:** 2026-03-13 00:27 MSK
**Research Time:** ~90 minutes
**Solution Status:** ✅ CONFIRMED WORKING
