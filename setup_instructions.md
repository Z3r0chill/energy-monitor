# Energy Monitor Dashboard Setup Guide

## Overview
This energy monitoring system provides real-time tracking and analysis of your Refoss EM16 energy monitor data with a sophisticated web dashboard, cost analysis, and historical reporting.

## Prerequisites

### Hardware Requirements
- Refoss EM16 Energy Monitor properly installed and connected to your network
- Server or computer to run the data collection service (Raspberry Pi, dedicated server, etc.)
- MySQL/MariaDB database server

### Software Requirements
- Python 3.8+
- MySQL/MariaDB 8.0+
- Modern web browser for dashboard access

## Installation Steps

### 1. Database Setup

First, create the database and user:

```sql
-- Connect to MySQL as root
CREATE DATABASE energy_monitor;
CREATE USER 'energy_monitor'@'localhost' IDENTIFIED BY 'your_secure_password';
GRANT ALL PRIVILEGES ON energy_monitor.* TO 'energy_monitor'@'localhost';
FLUSH PRIVILEGES;
```

Run the provided SQL schema to create all tables:

```bash
mysql -u energy_monitor -p energy_monitor < energy_monitor_schema.sql
```

### 2. Python Environment Setup

Create a virtual environment and install dependencies:

```bash
# Create virtual environment
python3 -m venv energy_monitor_env
source energy_monitor_env/bin/activate  # On Windows: energy_monitor_env\Scripts\activate

# Install required packages
pip install flask flask-cors mysql-connector-python requests python-dotenv
```

### 3. Configuration

Create a `.env` file in your project directory:

```env
# Device Configuration
REFOSS_DEVICE_IP=192.168.1.100
REFOSS_DEVICE_ID=your_device_id

# Database Configuration
DB_HOST=localhost
DB_USER=energy_monitor
DB_PASSWORD=your_secure_password
DB_NAME=energy_monitor

# Server Configuration
PORT=5000
DEBUG=False
POLLING_INTERVAL=1

# Optional: Enable logging
LOG_LEVEL=INFO
```

### 4. Find Your Refoss Device IP

Use one of these methods to find your device IP:

```bash
# Method 1: Network scan
nmap -sn 192.168.1.0/24 | grep -E "(Refoss|EM16)"

# Method 2: Check your router's DHCP table
# Login to your router and look for the Refoss device

# Method 3: Use the Refoss app to find the IP address
# Open the Refoss app > Device Settings > Device Information
```

### 5. Customize Circuit Names

Edit the `default_circuits` list in `energy_monitor_client.py` to match your electrical setup:

```python
default_circuits = [
    (1, "Main Panel A", "Main electrical panel circuit A", "main", 200),
    (2, "Main Panel B", "Main electrical panel circuit B", "main", 200),
    (3, "Your AC Unit", "Your actual AC unit description", "branch", 60),
    (4, "Your Pool Pump", "Your actual pool pump description", "branch", 60),
    # ... customize all 18 circuits to match your setup
]
```

### 6. Update FPL Billing Rates

Update the billing rates in the SQL schema or via the API with current FPL rates:

```sql
-- Update with current FPL rates
UPDATE billing_rates SET rate_per_kwh = 0.1234 WHERE rate_name = 'FPL Summer On-Peak';
-- Add more rate updates as needed
```

## Running the System

### 1. Start the Data Collection Service

```bash
# Navigate to project directory
cd /path/to/energy_monitor

# Activate virtual environment
source energy_monitor_env/bin/activate

# Start data collector
python energy_monitor_client.py
```

### 2. Start the Web API Server

In a separate terminal:

```bash
# Navigate to project directory
cd /path/to/energy_monitor

# Activate virtual environment
source energy_monitor_env/bin/activate

# Start API server
python api_server.py
```

### 3. Access the Dashboard

Open your web browser and navigate to:
```
http://localhost:5000
```

Or if running on a different server:
```
http://your-server-ip:5000
```

## Running as System Services

### Linux (systemd)

Create service files for automatic startup:

**Data Collector Service** (`/etc/systemd/system/energy-collector.service`):

```ini
[Unit]
Description=Energy Monitor Data Collector
After=network.target mysql.service

[Service]
Type=simple
User=your_username
WorkingDirectory=/path/to/energy_monitor
Environment=PATH=/path/to/energy_monitor/energy_monitor_env/bin
ExecStart=/path/to/energy_monitor/energy_monitor_env/bin/python energy_monitor_client.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

**API Server Service** (`/etc/systemd/system/energy-api.service`):

```ini
[Unit]
Description=Energy Monitor API Server
After=network.target mysql.service

[Service]
Type=simple
User=your_username
WorkingDirectory=/path/to/energy_monitor
Environment=PATH=/path/to/energy_monitor/energy_monitor_env/bin
ExecStart=/path/to/energy_monitor/energy_monitor_env/bin/python api_server.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Enable and start the services:

```bash
sudo systemctl enable energy-collector.service
sudo systemctl enable energy-api.service
sudo systemctl start energy-collector.service
sudo systemctl start energy-api.service
```

### Windows

Create batch files or use Windows Service Wrapper (WinSW) for running as Windows services.

## Troubleshooting

### Common Issues

1. **Cannot connect to device**
   - Verify the device IP address is correct
   - Ensure your server is on the same network as the Refoss device
   - Check firewall settings

2. **Database connection errors**
   - Verify MySQL is running
   - Check database credentials
   - Ensure database and tables exist

3. **No data appearing in dashboard**
   - Check the data collector logs
   - Verify the device is responding to API calls
   - Check that circuits are configured correctly

### Checking Logs

```bash
# View real-time logs
tail -f energy_monitor.log

# Check service logs (Linux)
journalctl -u energy-collector.service -f
journalctl -u energy-api.service -f
```

### Manual Testing

Test the API endpoints manually:

```bash
# Test real-time data
curl http://localhost:5000/api/realtime-data

# Test system status
curl http://localhost:5000/api/system-status

# Test circuits configuration
curl http://localhost:5000/api/circuits
```

## Maintenance

### Regular Tasks

1. **Database cleanup** - The system automatically removes old raw data after 3 years
2. **Log rotation** - Set up log rotation to prevent disk space issues
3. **Backup database** - Regular backups of the energy monitoring data

### Monthly Tasks

1. Update FPL billing rates if they change
2. Review and update circuit names/descriptions
3. Check system performance and optimize if needed

### Backup Script

```bash
#!/bin/bash
# backup_energy_data.sh
DATE=$(date +%Y%m%d_%H%M%S)
mysqldump -u energy_monitor -p energy_monitor > backup_energy_$DATE.sql
gzip backup_energy_$DATE.sql
```

## Advanced Features

### Grafana Integration

For advanced visualization, you can integrate with Grafana:

1. Install Grafana
2. Add MySQL data source
3. Import energy monitoring dashboards
4. Create custom alerts and notifications

### Home Assistant Integration

The system can be integrated with Home Assistant for smart home automation:

1. Use the REST API to create sensors in Home Assistant
2. Create automations based on energy usage
3. Set up notifications for high usage or anomalies

### Mobile Access

The dashboard is mobile-responsive and can be accessed from phones and tablets. For enhanced mobile experience, consider:

1. Setting up HTTPS with SSL certificates
2. Creating PWA (Progressive Web App) features
3. Push notifications for alerts

## API Documentation

### Available Endpoints

- `GET /api/realtime-data` - Current energy data for all circuits
- `GET /api/historical-data?hours=24` - Historical data for specified hours
- `GET /api/daily-usage` - Daily usage for last 30 days
- `GET /api/cost-analysis` - Cost breakdown and analysis
- `GET /api/circuits` - Circuit configuration
- `PUT /api/circuits/{id}` - Update circuit configuration
- `GET /api/billing-rates` - Current billing rates
- `GET /api/system-status` - System health and status
- `GET /api/export-data` - Export data for analysis

### Example API Calls

```bash
# Get current energy data
curl "http://localhost:5000/api/realtime-data"

# Get last 48 hours of data
curl "http://localhost:5000/api/historical-data?hours=48"

# Export daily data for analysis
curl "http://localhost:5000/api/export-data?start_date=2024-01-01&end_date=2024-01-31&type=daily"
```

## Support

For issues or questions:

1. Check the troubleshooting section above
2. Review the logs for error messages
3. Verify all configuration settings
4. Test individual components (database, API, device connectivity)

The system is designed to be robust and handle network interruptions, device restarts, and database issues gracefully. It will automatically reconnect and resume data collection when issues are resolved.
