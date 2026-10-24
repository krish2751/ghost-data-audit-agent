You are transcribing a screenshot of an internal business application (admin console, inspector or similar) for a data-deletion audit. Transcribe only what is visibly on the screen. Do not guess, infer, or fill in values that are not shown.

Return one JSON object and nothing else (no prose, no code fences) with this shape:

{
  "screen_title": "<title or heading shown, or null>",
  "system": "<application / service name shown, or null>",
  "screen_timestamp": "<any capture / as-of / current time shown, ISO-8601 if possible, or null>",
  "filters_or_query": "<search text, filters or selected tab shown, or null>",
  "records": [
    {
      "resource_id": "<exact id such as account_1234, search_12, support_5, analytics_9, export_3, backup_7, data_flow_8, audit_record_4, tombstone_2, or null>",
      "identifiers": {
        "name": null, "email": null, "phone": null, "email_hash": null,
        "user_id": null, "customer_reference": null, "subject_reference": null
      },
      "status_fields": { "<label as shown>": "<value as shown>" },
      "timestamps": { "<label as shown>": "<value as shown>" },
      "other_fields": { "<label as shown>": "<value as shown>" }
    }
  ],
  "empty_state_text": "<text such as 'No results' if the list is empty, else null>",
  "notes": "<anything on screen that does not fit above, or null>"
}

Rules:
- One entry in "records" per row / card / detail panel. Include every visible resource id, even when its identifying fields are blank, masked, "-" or "REDACTED"; use null for hidden values and copy masked text exactly (e.g. "j***@mail.com") in the matching field.
- Keep identifiers in "identifiers" using the keys shown; copy emails, phones and hashes exactly, preserving case.
- Put enabled/disabled, restore allowed, account status, deleted, active, anonymized and similar flags in "status_fields" using the on-screen labels.
- Keep dates and times exactly as displayed.
- If part of the screen is unreadable, say so in "notes".
