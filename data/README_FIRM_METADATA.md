# Firm Metadata

This file contains additional information about law firms that argue before the NH Supreme Court.

## Structure

```json
{
  "firms": [
    {
      "short_name": "Name as it appears in oral_arguments_attorney_stats.json",
      "full_name": "Full legal name of the firm",
      "website": "https://example.com",
      "description": "Optional description or note"
    }
  ]
}
```

## Usage

The firm profile page (`pages/10_Firm_Detail.py`) displays:
- **Full legal name** as the page title
- **Website link** (if provided) with a globe icon
- **Short name** as "Also known as" (if different from full name)

## Adding a Firm

1. Find the firm's short name in `data/processed/oral_arguments_attorney_stats.json`
2. Add an entry to the `firms` array in `data/firm_metadata.json`:

```json
{
  "short_name": "Exact name from stats file",
  "full_name": "Full legal firm name",
  "website": "https://firmwebsite.com/",
  "description": null
}
```

3. The changes will appear immediately after the next page load (data is cached for 1 hour)

## Notes

- `short_name` **must** match exactly the firm name in the attorney stats
- `website` should include the full URL with `https://`
- `description` is optional and currently not displayed (reserved for future use)
- Firms not in this file will still appear but only show their basic name
