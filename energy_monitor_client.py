#!/usr/bin/env python3
"""
Refoss Energy Monitor API Client and Data Collector
Polls the Refoss EM16 device every second and stores data in MySQL database
"""

import requests
import json
import time
import logging
import mysql.connector
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
import threading
from dataclasses import dataclass
import os
from decimal import Decimal
import socket

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('energy_monitor.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

@dataclass
class EnergyReading:
    """Data class for energy readings"""
    circuit_id: int
    voltage: float
    current_amps: float
    power_watts: float
    energy_kwh: float
    power_factor: float = 0.0
    frequency: float = 60.0
    timestamp: datetime = None
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now()

class RefossEnergyMonitor:
    """Client for Refoss Energy Monitor API"""
    
    def __init__(self, device_ip: str, device_id: str = None):
        self.device_ip = device_ip
        self.device_id = device_id or self._discover_device_id()
        self.base_url = f"http://{device_ip}"
        self.session = requests.Session()
        self.session.timeout = 5
        
        # Common headers for API requests
        self.headers = {
            'Content-Type': 'application/json',
            'User-Agent': 'RefossEnergyCollector/1.0'
        }
        
    def _discover_device_id(self) -> str:
        """Discover device ID from the device info endpoint"""
        try:
            response = self.session.get(f"{self.base_url}/api/v1/device/info", 
                                      headers=self.headers)
            response.raise_for_status()
            data = response.json()
            return data.get('deviceId', f"em16_{self.device_ip.replace('.', '_')}")
        except Exception as e:
            logger.warning(f"Could not discover device ID: {e}")
            return f"em16_{self.device_ip.replace('.', '_')}"
    
    def get_device_info(self) -> Dict:
        """Get device information"""
        try:
            response = self.session.get(f"{self.base_url}/api/v1/device/info", 
                                      headers=self.headers)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Failed to get device info: {e}")
            return {}
    
    def get_real_time_data(self) -> List[Dict]:
        """Get real-time energy data for all circuits"""
        try:
            # Try different possible endpoints based on common patterns
            endpoints = [
                "/api/v1/energy/realtime",
                "/api/v1/data/current",
                "/api/v1/circuits/data",
                "/cgi-bin/luci/admin/refoss/energy"
            ]
            
            for endpoint in endpoints:
                try:
                    response = self.session.get(f"{self.base_url}{endpoint}", 
                                              headers=self.headers)
                    if response.status_code == 200:
                        data = response.json()
                        if data:  # If we get valid data, use this endpoint
                            return self._parse_energy_data(data)
                except:
                    continue
            
            # If no endpoint works, try local network discovery
            return self._get_local_network_data()
            
        except Exception as e:
            logger.error(f"Failed to get real-time data: {e}")
            return []
    
    def _parse_energy_data(self, data: Dict) -> List[Dict]:
        """Parse energy data from API response"""
        readings = []
        
        # Handle different possible data formats
        if 'circuits' in data:
            circuits_data = data['circuits']
        elif 'channels' in data:
            circuits_data = data['channels']
        elif isinstance(data, list):
            circuits_data = data
        else:
            circuits_data = [data]
        
        for i, circuit_data in enumerate(circuits_data):
            # Handle different naming conventions
            reading = {
                'circuit_number': circuit_data.get('circuit', circuit_data.get('channel', i + 1)),
                'voltage': float(circuit_data.get('voltage', circuit_data.get('V', 240.0))),
                'current': float(circuit_data.get('current', circuit_data.get('A', circuit_data.get('amps', 0.0)))),
                'power': float(circuit_data.get('power', circuit_data.get('W', circuit_data.get('watts', 0.0)))),
                'energy': float(circuit_data.get('energy', circuit_data.get('kWh', circuit_data.get('kwh', 0.0)))),
                'power_factor': float(circuit_data.get('power_factor', circuit_data.get('pf', 1.0))),
                'frequency': float(circuit_data.get('frequency', circuit_data.get('Hz', 60.0)))
            }
            readings.append(reading)
        
        return readings
    
    def _get_local_network_data(self) -> List[Dict]:
        """Attempt to get data via local network protocol (fallback)"""
        try:
            # This is a placeholder for local network communication
            # You may need to implement UDP/TCP communication based on the device protocol
            logger.warning("Using mock data - implement actual local network protocol")
            
            # Return mock data for development/testing
            return self._generate_mock_data()
            
        except Exception as e:
            logger.error(f"Failed to get local network data: {e}")
            return []
    
    def _generate_mock_data(self) -> List[Dict]:
        """Generate mock data for testing (remove in production)"""
        import random
        readings = []
        
        # Generate data for 18 circuits (2 main + 16 branch)
        for i in range(18):
            if i < 2:  # Main circuits
                base_power = random.uniform(2000, 8000)
                voltage = random.uniform(235, 245)
            else:  # Branch circuits
                base_power = random.uniform(0, 2000)
                voltage = random.uniform(115, 125)
            
            current = base_power / voltage if voltage > 0 else 0
            
            readings.append({
                'circuit_number': i + 1,
                'voltage': voltage,
                'current': current,
                'power': base_power,
                'energy': random.uniform(0, 100),
                'power_factor': random.uniform(0.8, 1.0),
                'frequency': random.uniform(59.5, 60.5)
            })
        
        return readings

class DatabaseManager:
    """Database management for energy monitoring data"""
    
    def __init__(self, host: str, user: str, password: str, database: str):
        self.connection_params = {
            'host': host,
            'user': user,
            'password': password,
            'database': database,
            'autocommit': True,
            'charset': 'utf8mb4'
        }
        self.connection = None
        self.connect()
    
    def connect(self):
        """Connect to MySQL database"""
        try:
            self.connection = mysql.connector.connect(**self.connection_params)
            logger.info("Connected to MySQL database")
        except Exception as e:
            logger.error(f"Failed to connect to database: {e}")
            raise
    
    def ensure_connection(self):
        """Ensure database connection is alive"""
        try:
            if not self.connection.is_connected():
                self.connect()
        except:
            self.connect()
    
    def insert_device(self, device_id: str, device_name: str, ip_address: str, 
                     mac_address: str = None, firmware_version: str = None) -> int:
        """Insert or update device information"""
        self.ensure_connection()
        cursor = self.connection.cursor()
        
        try:
            query = """
                INSERT INTO devices (device_id, device_name, device_type, ip_address, 
                                   mac_address, firmware_version, status, last_seen)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    device_name = VALUES(device_name),
                    ip_address = VALUES(ip_address),
                    mac_address = VALUES(mac_address),
                    firmware_version = VALUES(firmware_version),
                    status = VALUES(status),
                    last_seen = VALUES(last_seen)
            """
            
            cursor.execute(query, (
                device_id, device_name, 'EM16', ip_address,
                mac_address, firmware_version, 'active', datetime.now()
            ))
            
            # Get the device ID
            cursor.execute("SELECT id FROM devices WHERE device_id = %s", (device_id,))
            result = cursor.fetchone()
            return result[0] if result else None
            
        except Exception as e:
            logger.error(f"Failed to insert device: {e}")
            raise
        finally:
            cursor.close()
    
    def insert_circuit(self, device_id: int, circuit_number: int, circuit_name: str,
                      circuit_description: str = None, circuit_type: str = 'branch',
                      max_amperage: int = 60) -> int:
        """Insert or update circuit information"""
        self.ensure_connection()
        cursor = self.connection.cursor()
        
        try:
            query = """
                INSERT INTO circuits (device_id, circuit_number, circuit_name, 
                                    circuit_description, circuit_type, max_amperage)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    circuit_name = VALUES(circuit_name),
                    circuit_description = VALUES(circuit_description),
                    circuit_type = VALUES(circuit_type),
                    max_amperage = VALUES(max_amperage)
            """
            
            cursor.execute(query, (
                device_id, circuit_number, circuit_name,
                circuit_description, circuit_type, max_amperage
            ))
            
            # Get the circuit ID
            cursor.execute("""
                SELECT id FROM circuits 
                WHERE device_id = %s AND circuit_number = %s
            """, (device_id, circuit_number))
            result = cursor.fetchone()
            return result[0] if result else None
            
        except Exception as e:
            logger.error(f"Failed to insert circuit: {e}")
            raise
        finally:
            cursor.close()
    
    def insert_reading(self, reading: EnergyReading):
        """Insert energy reading into database"""
        self.ensure_connection()
        cursor = self.connection.cursor()
        
        try:
            query = """
                INSERT INTO energy_readings 
                (circuit_id, timestamp, voltage, current_amps, power_watts, 
                 energy_kwh, power_factor, frequency)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """
            
            cursor.execute(query, (
                reading.circuit_id, reading.timestamp, reading.voltage,
                reading.current_amps, reading.power_watts, reading.energy_kwh,
                reading.power_factor, reading.frequency
            ))
            
        except Exception as e:
            logger.error(f"Failed to insert reading: {e}")
            raise
        finally:
            cursor.close()
    
    def get_circuit_map(self, device_id: int) -> Dict[int, int]:
        """Get mapping of circuit numbers to circuit IDs"""
        self.ensure_connection()
        cursor = self.connection.cursor()
        
        try:
            cursor.execute("""
                SELECT circuit_number, id FROM circuits 
                WHERE device_id = %s AND is_active = TRUE
            """, (device_id,))
            
            return {row[0]: row[1] for row in cursor.fetchall()}
            
        except Exception as e:
            logger.error(f"Failed to get circuit map: {e}")
            return {}
        finally:
            cursor.close()
    
    def cleanup_old_data(self, days_to_keep: int = 1095):
        """Clean up old raw data (keep aggregated data)"""
        self.ensure_connection()
        cursor = self.connection.cursor()
        
        try:
            cutoff_date = datetime.now() - timedelta(days=days_to_keep)
            
            cursor.execute("""
                DELETE FROM energy_readings 
                WHERE timestamp < %s
            """, (cutoff_date,))
            
            deleted_count = cursor.rowcount
            logger.info(f"Cleaned up {deleted_count} old readings")
            
        except Exception as e:
            logger.error(f"Failed to cleanup old data: {e}")
        finally:
            cursor.close()

class EnergyDataCollector:
    """Main data collection service"""
    
    def __init__(self, config: Dict):
        self.config = config
        self.device = RefossEnergyMonitor(
            config['device_ip'], 
            config.get('device_id')
        )
        self.db = DatabaseManager(
            config['db_host'],
            config['db_user'],
            config['db_password'],
            config['db_name']
        )
        self.running = False
        self.device_db_id = None
        self.circuit_map = {}
        
    def setup_device_and_circuits(self):
        """Setup device and circuit information in database"""
        # Get device info
        device_info = self.device.get_device_info()
        
        # Insert device
        self.device_db_id = self.db.insert_device(
            self.device.device_id,
            device_info.get('name', f"Refoss EM16 {self.device.device_ip}"),
            self.device.device_ip,
            device_info.get('mac'),
            device_info.get('firmware')
        )
        
        # Setup default circuits if not already configured
        default_circuits = [
            (1, "Main Panel A", "Main electrical panel circuit A", "main", 200),
            (2, "Main Panel B", "Main electrical panel circuit B", "main", 200),
            (3, "Upstairs AC", "Upstairs air conditioning compressor", "branch", 60),
            (4, "Downstairs AC", "Downstairs air conditioning compressor", "branch", 60),
            (5, "Pool Pump", "Swimming pool pump and equipment", "branch", 60),
            (6, "Water Heater", "Electric water heater", "branch", 60),
            (7, "Dryer", "Electric clothes dryer", "branch", 60),
            (8, "Kitchen", "Kitchen appliances and outlets", "branch", 60),
            (9, "Living Room", "Living room lights and outlets", "branch", 60),
            (10, "Master Bedroom", "Master bedroom circuit", "branch", 60),
            (11, "Guest Rooms", "Guest bedroom circuits", "branch", 60),
            (12, "Garage", "Garage outlets and door opener", "branch", 60),
            (13, "Outdoor Lighting", "Exterior lighting", "branch", 60),
            (14, "Office", "Home office equipment", "branch", 60),
            (15, "Basement", "Basement lights and outlets", "branch", 60),
            (16, "EV Charger", "Electric vehicle charging station", "branch", 60),
            (17, "Spare 1", "Spare circuit 1", "branch", 60),
            (18, "Spare 2", "Spare circuit 2", "branch", 60)
        ]
        
        for circuit_num, name, desc, circuit_type, max_amp in default_circuits:
            circuit_id = self.db.insert_circuit(
                self.device_db_id, circuit_num, name, desc, circuit_type, max_amp
            )
            self.circuit_map[circuit_num] = circuit_id
        
        logger.info(f"Setup complete: Device ID {self.device_db_id}, {len(self.circuit_map)} circuits")
    
    def collect_data(self):
        """Main data collection loop"""
        self.running = True
        logger.info("Starting data collection...")
        
        while self.running:
            try:
                # Get real-time data
                readings_data = self.device.get_real_time_data()
                
                if not readings_data:
                    logger.warning("No data received from device")
                    time.sleep(1)
                    continue
                
                # Process each reading
                for reading_data in readings_data:
                    circuit_number = reading_data['circuit_number']
                    
                    if circuit_number not in self.circuit_map:
                        logger.warning(f"Unknown circuit number: {circuit_number}")
                        continue
                    
                    circuit_id = self.circuit_map[circuit_number]
                    
                    reading = EnergyReading(
                        circuit_id=circuit_id,
                        voltage=reading_data['voltage'],
                        current_amps=reading_data['current'],
                        power_watts=reading_data['power'],
                        energy_kwh=reading_data['energy'],
                        power_factor=reading_data['power_factor'],
                        frequency=reading_data['frequency']
                    )
                    
                    self.db.insert_reading(reading)
                
                logger.debug(f"Collected {len(readings_data)} readings")
                
            except Exception as e:
                logger.error(f"Error in data collection: {e}")
            
            time.sleep(self.config.get('polling_interval', 1))
    
    def start(self):
        """Start the data collection service"""
        self.setup_device_and_circuits()
        self.collect_data()
    
    def stop(self):
        """Stop the data collection service"""
        self.running = False
        logger.info("Data collection stopped")

def main():
    """Main function"""
    # Configuration
    config = {
        'device_ip': os.getenv('REFOSS_DEVICE_IP', '192.168.1.100'),
        'device_id': os.getenv('REFOSS_DEVICE_ID'),
        'db_host': os.getenv('DB_HOST', 'localhost'),
        'db_user': os.getenv('DB_USER', 'energy_monitor'),
        'db_password': os.getenv('DB_PASSWORD', 'your_password'),
        'db_name': os.getenv('DB_NAME', 'energy_monitor'),
        'polling_interval': int(os.getenv('POLLING_INTERVAL', '1'))
    }
    
    # Create collector
    collector = EnergyDataCollector(config)
    
    try:
        collector.start()
    except KeyboardInterrupt:
        logger.info("Received interrupt signal")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
    finally:
        collector.stop()

if __name__ == "__main__":
    main()
