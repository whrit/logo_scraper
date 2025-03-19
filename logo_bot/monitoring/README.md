# Logo Bot Monitoring System

This directory contains scripts to monitor and automatically maintain the logo extraction system, with a focus on keeping Google Images extraction working reliably.

## Why Monitoring Is Needed

Google frequently changes their HTML and CSS selectors, which can break our extraction code. This monitoring system:

1. Regularly checks if the extraction is working
2. Logs results and generates reports
3. Can automatically update selectors when they change
4. Sets up scheduled tasks to run these checks daily

## Components

- `check_extractors.py`: Tests the logo extraction against known websites
- `update_selectors.py`: Analyzes Google Images pages and updates selectors
- `cron_setup.py`: Sets up automated daily checks (cron or launchd)

## Setup Instructions

### 1. Install Dependencies

```bash
pip install beautifulsoup4 requests selenium
```

### 2. Configure Scheduled Checks

Run the setup script to configure daily checks:

```bash
python logo_bot/monitoring/cron_setup.py
```

This will:
- On macOS: Create LaunchAgent jobs to run at 3:00 AM and 3:30 AM
- On Linux: Set up cron jobs to run at the same times

### 3. Manual Testing

You can also run the checks manually:

```bash
# Check if extractors are working
python logo_bot/monitoring/check_extractors.py

# Update selectors if needed
python logo_bot/monitoring/update_selectors.py
```

## How It Works

### Checking Extractors

The `check_extractors.py` script:
1. Tests the Google extractor against well-known domains
2. First tries the fast extraction method
3. Falls back to the original method if the fast one fails
4. Records success rates and timings
5. Generates a report with detailed results

### Updating Selectors

When checks indicate the selectors may be out of date, the `update_selectors.py` script:

1. Analyzes the structure of Google Images search pages
2. Identifies likely image selectors by analyzing CSS classes
3. Updates the selectors used by the fast extraction method
4. Tests if the updates fix the issues
5. Preserves the original code by making backups

## Reports and Logs

All logs and reports are stored in `CACHE_DIR/logs`:

- `extractor_check_YYYYMMDD.log`: Daily check results
- `extractor_report_YYYYMMDD.json`: Detailed JSON reports
- `selector_update.log`: Log of selector updates
- `cron_*.log` or `launchd_*.log`: Scheduled task logs

## Troubleshooting

If the automated updates aren't fixing issues:

1. Check the logs for detailed error information
2. Manually inspect Google Images search to see how the page structure has changed
3. Try updating the regex patterns in the page source extraction
4. Sometimes Google makes more substantial changes that require code updates

## License

Same as the main project 