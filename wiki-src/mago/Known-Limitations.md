# Known Limitations

TAG Mago data relies on periodic snapshots published by Transportadora Associada de Gás (TAG).

## Data Cadence and Availability

<<<<<<< HEAD
- Snapshots are polled and refreshed automatically via GitHub Actions about once per hour (a single combined workflow rebuilds `/monitor/` and publishes payloads to R2). The monitor page also re-fetches published artifacts every few minutes in the browser.
=======
- Snapshots are polled and refreshed automatically via GitHub Actions about once per hour (a single combined workflow rebuilds `/monitor/` and publishes payloads to R2).
>>>>>>> 018b37f (Combine Mago and NTS into one hourly monitor workflow)
- If TAG's API endpoint is unavailable or returns an error, the latest cached snapshot is retained until connectivity is restored.

## Scope of Measurements

- Values are stored exactly as published by TAG: line pack is reported in cubic meters (m³), and zone forecasts are reported in millions of cubic meters per day (Mm³/d).
- The dashboard covers TAG's integrated pipeline grid; other transportadora line pack figures (TBG, NTS) are not published through this specific feed.
