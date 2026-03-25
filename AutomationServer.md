# Frontend Task: Add Job Status Polling & Progress Display

## IMPORTANT: Do NOT modify existing components, routes, or how the frontend communicates with the backend. Only ADD the status polling and progress display logic described below.

## Context
The frontend already has: driver search/selection, state toggle buttons, permit type dropdown, effective date picker, and a submit button that sends `POST /api/permits/order` to the backend. The backend now returns `{ jobId, status: "queued" }` after submit.

I need to ADD logic to poll for job progress and display results.

## What to ADD (do not change existing code)

### 1. After submit, start polling `GET /api/permits/status/:jobId`
- Poll every 3 seconds after receiving the jobId from the submit response
- Stop polling when `status` is `"complete"` or `"failed"`

**Response format from backend:**
```json
{
  "jobId": "JOB-123",
  "status": "processing",
  "results": [
    { "permitId": "P001", "permitType": "ITP - IRP TRIP PERMIT", "driverName": "Jonattan Vazquez Perez", "tractor": "F894", "status": "success" },
    { "permitId": "P002", "permitType": "MFTP - MTTP PERMIT", "driverName": "John Smith", "status": "error", "message": "Make not found in dropdown" }
  ],
  "summary": null
}
```

When job finishes, `summary` will be: `{ "total": 4, "succeeded": 3, "failed": 1 }`

### 2. Display results in the log console as they arrive
Each poll may return new results. Show each one as a log entry:
- **Success:** green indicator + driver name + tractor number + permit type
- **Error:** red indicator + driver name + error message
- **Job complete:** summary line (e.g., "3 of 4 permits completed successfully")

### 3. Toast notifications
- All succeeded → success toast
- Some failed → warning toast with failure count
- All failed → error toast

### 4. Submit button state
- Disable submit button while a job is processing
- Show a spinner or "Processing..." text
- Re-enable when job completes

## Notes
- Backend base URL is `http://localhost:3001` (should already be configured)
- `permitType: "trip_fuel"` creates 2 permits per driver — if 3 drivers selected with "trip_fuel", total is 6 permits. Consider showing this count to the dispatcher.
- Only "GA" is supported as a state right now
