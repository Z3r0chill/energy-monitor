-- Energy Monitor Database Schema
-- MySQL/MariaDB compatible

-- Table to store device information
CREATE TABLE devices (
    id INT AUTO_INCREMENT PRIMARY KEY,
    device_id VARCHAR(64) UNIQUE NOT NULL,
    device_name VARCHAR(128) NOT NULL,
    device_type VARCHAR(32) NOT NULL DEFAULT 'EM16',
    ip_address VARCHAR(45),
    mac_address VARCHAR(17),
    firmware_version VARCHAR(32),
    status ENUM('active', 'inactive', 'error') DEFAULT 'active',
    last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Table to store circuit/sensor information
CREATE TABLE circuits (
    id INT AUTO_INCREMENT PRIMARY KEY,
    device_id INT NOT NULL,
    circuit_number INT NOT NULL,
    circuit_name VARCHAR(128) NOT NULL,
    circuit_description TEXT,
    circuit_type ENUM('main', 'branch') NOT NULL,
    max_amperage INT DEFAULT 60,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (device_id) REFERENCES devices(id) ON DELETE CASCADE,
    UNIQUE KEY unique_circuit (device_id, circuit_number)
);

-- Table to store real-time energy readings
CREATE TABLE energy_readings (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    circuit_id INT NOT NULL,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    voltage DECIMAL(8,2) NOT NULL,
    current_amps DECIMAL(8,3) NOT NULL,
    power_watts DECIMAL(10,2) NOT NULL,
    energy_kwh DECIMAL(12,4) NOT NULL,
    power_factor DECIMAL(4,3),
    frequency DECIMAL(6,2),
    INDEX idx_circuit_timestamp (circuit_id, timestamp),
    INDEX idx_timestamp (timestamp),
    FOREIGN KEY (circuit_id) REFERENCES circuits(id) ON DELETE CASCADE
);

-- Table to store aggregated hourly data for faster queries
CREATE TABLE energy_hourly (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    circuit_id INT NOT NULL,
    hour_start TIMESTAMP NOT NULL,
    avg_voltage DECIMAL(8,2),
    avg_current DECIMAL(8,3),
    avg_power DECIMAL(10,2),
    min_power DECIMAL(10,2),
    max_power DECIMAL(10,2),
    total_energy_kwh DECIMAL(12,4),
    sample_count INT DEFAULT 0,
    PRIMARY KEY (id),
    UNIQUE KEY unique_circuit_hour (circuit_id, hour_start),
    INDEX idx_hour_start (hour_start),
    FOREIGN KEY (circuit_id) REFERENCES circuits(id) ON DELETE CASCADE
);

-- Table to store daily aggregated data
CREATE TABLE energy_daily (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    circuit_id INT NOT NULL,
    date_day DATE NOT NULL,
    avg_voltage DECIMAL(8,2),
    avg_current DECIMAL(8,3),
    avg_power DECIMAL(10,2),
    min_power DECIMAL(10,2),
    max_power DECIMAL(10,2),
    total_energy_kwh DECIMAL(12,4),
    cost_estimate DECIMAL(10,2),
    PRIMARY KEY (id),
    UNIQUE KEY unique_circuit_day (circuit_id, date_day),
    INDEX idx_date_day (date_day),
    FOREIGN KEY (circuit_id) REFERENCES circuits(id) ON DELETE CASCADE
);

-- Table for FPL billing rates configuration
CREATE TABLE billing_rates (
    id INT AUTO_INCREMENT PRIMARY KEY,
    rate_name VARCHAR(64) NOT NULL,
    rate_type ENUM('on_peak', 'off_peak', 'super_off_peak') NOT NULL,
    season ENUM('summer', 'winter', 'year_round') NOT NULL,
    start_time TIME NOT NULL,
    end_time TIME NOT NULL,
    rate_per_kwh DECIMAL(8,4) NOT NULL,
    effective_date DATE NOT NULL,
    expiry_date DATE,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Table to store cost calculations
CREATE TABLE energy_costs (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    circuit_id INT NOT NULL,
    date_day DATE NOT NULL,
    on_peak_kwh DECIMAL(12,4) DEFAULT 0,
    off_peak_kwh DECIMAL(12,4) DEFAULT 0,
    super_off_peak_kwh DECIMAL(12,4) DEFAULT 0,
    on_peak_cost DECIMAL(10,2) DEFAULT 0,
    off_peak_cost DECIMAL(10,2) DEFAULT 0,
    super_off_peak_cost DECIMAL(10,2) DEFAULT 0,
    total_cost DECIMAL(10,2) DEFAULT 0,
    UNIQUE KEY unique_circuit_cost_day (circuit_id, date_day),
    FOREIGN KEY (circuit_id) REFERENCES circuits(id) ON DELETE CASCADE
);

-- Table to store system configuration
CREATE TABLE system_config (
    id INT AUTO_INCREMENT PRIMARY KEY,
    config_key VARCHAR(64) UNIQUE NOT NULL,
    config_value TEXT,
    description TEXT,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);

-- Insert default system configurations
INSERT INTO system_config (config_key, config_value, description) VALUES
('polling_interval', '1', 'Polling interval in seconds'),
('data_retention_days', '1095', 'Number of days to retain raw data (3 years)'),
('aggregation_enabled', 'true', 'Enable hourly/daily aggregation'),
('cost_calculation_enabled', 'true', 'Enable cost calculations'),
('timezone', 'America/New_York', 'System timezone for FPL billing');

-- Insert default FPL billing rates (example rates - update with actual FPL rates)
INSERT INTO billing_rates (rate_name, rate_type, season, start_time, end_time, rate_per_kwh, effective_date) VALUES
('FPL Summer On-Peak', 'on_peak', 'summer', '12:00:00', '21:00:00', 0.1234, '2024-01-01'),
('FPL Summer Off-Peak', 'off_peak', 'summer', '21:00:01', '11:59:59', 0.0876, '2024-01-01'),
('FPL Winter On-Peak', 'on_peak', 'winter', '06:00:00', '10:00:00', 0.1156, '2024-01-01'),
('FPL Winter Mid-Peak', 'off_peak', 'winter', '10:00:01', '18:00:00', 0.0987, '2024-01-01'),
('FPL Winter Off-Peak', 'super_off_peak', 'winter', '18:00:01', '05:59:59', 0.0743, '2024-01-01');

-- Create indexes for better performance
CREATE INDEX idx_readings_circuit_recent ON energy_readings(circuit_id, timestamp DESC);
CREATE INDEX idx_hourly_circuit_recent ON energy_hourly(circuit_id, hour_start DESC);
CREATE INDEX idx_daily_circuit_recent ON energy_daily(circuit_id, date_day DESC);

-- Create a view for current readings with circuit information
CREATE VIEW current_readings AS
SELECT 
    c.id as circuit_id,
    c.circuit_name,
    c.circuit_description,
    c.circuit_type,
    c.max_amperage,
    d.device_name,
    d.ip_address,
    er.voltage,
    er.current_amps,
    er.power_watts,
    er.energy_kwh,
    er.power_factor,
    er.frequency,
    er.timestamp as last_reading
FROM circuits c
JOIN devices d ON c.device_id = d.id
LEFT JOIN energy_readings er ON c.id = er.circuit_id
WHERE er.timestamp = (
    SELECT MAX(timestamp) 
    FROM energy_readings er2 
    WHERE er2.circuit_id = c.id
)
AND c.is_active = TRUE
ORDER BY c.circuit_number;

-- Create a view for daily usage summary
CREATE VIEW daily_usage_summary AS
SELECT 
    c.circuit_name,
    ed.date_day,
    ed.total_energy_kwh,
    ed.avg_power,
    ed.max_power,
    COALESCE(ec.total_cost, 0) as estimated_cost
FROM circuits c
JOIN energy_daily ed ON c.id = ed.circuit_id
LEFT JOIN energy_costs ec ON c.id = ec.circuit_id AND ed.date_day = ec.date_day
WHERE c.is_active = TRUE
ORDER BY ed.date_day DESC, c.circuit_number;
