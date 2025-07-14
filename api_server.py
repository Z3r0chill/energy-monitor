#!/usr/bin/env python3
"""
Energy Monitor API Server
Flask-based REST API for serving dashboard data
"""

from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
import mysql.connector
import json
from datetime import datetime, timedelta
import os
import logging
from decimal import Decimal
import threading
import time

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)

# Database configuration
DB_CONFIG = {
    'host': os.getenv('DB_HOST', 'localhost'),
    'user': os.getenv('DB_USER', 'energy_monitor'),
    'password': os.getenv('DB_PASSWORD', 'your_password'),
    'database': os.getenv('DB_NAME', 'energy_monitor'),
    'charset': 'utf8mb4'
}

def get_db_connection():
    """Get database connection"""
    try:
        return mysql.connector.connect(**DB_CONFIG)
    except Exception as e:
        logger.error(f"Database connection error: {e}")
        raise

def decimal_to_float(obj):
    """Convert Decimal objects to float for JSON serialization"""
    if isinstance(obj, Decimal):
        return float(obj)
    raise TypeError

@app.route('/')
def dashboard():
    """Serve the main dashboard"""
    return send_from_directory('.', 'dashboard.html')

@app.route('/api/realtime-data')
def get_realtime_data():
    """Get current real-time data for all circuits"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        # Get current readings for all circuits
        query = """
            SELECT 
                c.id,
                c.circuit_number,
                c.circuit_name,
                c.circuit_description,
                c.circuit_type,
                c.max_amperage,
                er.voltage,
                er.current_amps,
                er.power_watts,
                er.energy_kwh,
                er.power_factor,
                er.frequency,
                er.timestamp
            FROM circuits c
            LEFT JOIN energy_readings er ON c.id = er.circuit_id
            WHERE c.is_active = TRUE
            AND er.timestamp = (
                SELECT MAX(timestamp) 
                FROM energy_readings er2 
                WHERE er2.circuit_id = c.id
            )
            ORDER BY c.circuit_number
        """
        
        cursor.execute(query)
        circuits = cursor.fetchall()
        
        # Calculate totals
        total_power = sum(float(c['power_watts'] or 0) for c in circuits)
        avg_voltage = sum(float(c['voltage'] or 0) for c in circuits if c['voltage']) / len([c for c in circuits if c['voltage']]) if circuits else 0
        avg_frequency = sum(float(c['frequency'] or 0) for c in circuits if c['frequency']) / len([c for c in circuits if c['frequency']]) if circuits else 60.0
        
        # Get today's energy total
        today = datetime.now().date()
        cursor.execute("""
            SELECT SUM(total_energy_kwh) as total_energy
            FROM energy_daily 
            WHERE date_day = %s
        """, (today,))
        
        today_energy_result = cursor.fetchone()
        today_energy = float(today_energy_result['total_energy'] or 0) if today_energy_result else 0
        
        # Get estimated cost for today
        cursor.execute("""
            SELECT SUM(total_cost) as total_cost
            FROM energy_costs 
            WHERE date_day = %s
        """, (today,))
        
        today_cost_result = cursor.fetchone()
        today_cost = float(today_cost_result['total_cost'] or 0) if today_cost_result else 0
        
        # Convert timestamps to strings for JSON serialization
        for circuit in circuits:
            if circuit['timestamp']:
                circuit['timestamp'] = circuit['timestamp'].isoformat()
        
        response_data = {
            'circuits': circuits,
            'summary': {
                'total_power': total_power,
                'avg_voltage': avg_voltage,
                'avg_frequency': avg_frequency,
                'today_energy': today_energy,
                'today_cost': today_cost,
                'last_update': datetime.now().isoformat()
            }
        }
        
        return jsonify(response_data)
        
    except Exception as e:
        logger.error(f"Error getting realtime data: {e}")
        return jsonify({'error': str(e)}), 500
    finally:
        if 'conn' in locals():
            conn.close()

@app.route('/api/historical-data')
def get_historical_data():
    """Get historical data for charts"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        # Get time range from query parameters
        hours = int(request.args.get('hours', 24))
        start_time = datetime.now() - timedelta(hours=hours)
        
        # Get hourly aggregated data
        cursor.execute("""
            SELECT 
                c.circuit_name,
                eh.hour_start,
                eh.avg_power,
                eh.total_energy_kwh
            FROM energy_hourly eh
            JOIN circuits c ON eh.circuit_id = c.id
            WHERE eh.hour_start >= %s
            AND c.is_active = TRUE
            ORDER BY eh.hour_start, c.circuit_number
        """, (start_time,))
        
        historical_data = cursor.fetchall()
        
        # Convert timestamps to strings
        for record in historical_data:
            record['hour_start'] = record['hour_start'].isoformat()
        
        return jsonify(historical_data)
        
    except Exception as e:
        logger.error(f"Error getting historical data: {e}")
        return jsonify({'error': str(e)}), 500
    finally:
        if 'conn' in locals():
            conn.close()

@app.route('/api/daily-usage')
def get_daily_usage():
    """Get daily usage data for the last 30 days"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        # Get last 30 days
        start_date = datetime.now().date() - timedelta(days=30)
        
        cursor.execute("""
            SELECT 
                date_day,
                SUM(total_energy_kwh) as total_energy,
                SUM(cost_estimate) as total_cost
            FROM energy_daily 
            WHERE date_day >= %s
            GROUP BY date_day
            ORDER BY date_day
        """, (start_date,))
        
        daily_data = cursor.fetchall()
        
        # Convert dates to strings
        for record in daily_data:
            record['date_day'] = record['date_day'].isoformat()
        
        return jsonify(daily_data)
        
    except Exception as e:
        logger.error(f"Error getting daily usage: {e}")
        return jsonify({'error': str(e)}), 500
    finally:
        if 'conn' in locals():
            conn.close()

@app.route('/api/cost-analysis')
def get_cost_analysis():
    """Get cost analysis data"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        # Get today's cost breakdown
        today = datetime.now().date()
        cursor.execute("""
            SELECT 
                SUM(on_peak_cost) as on_peak_cost,
                SUM(off_peak_cost) as off_peak_cost,
                SUM(super_off_peak_cost) as super_off_peak_cost,
                SUM(total_cost) as total_cost
            FROM energy_costs 
            WHERE date_day = %s
        """, (today,))
        
        today_costs = cursor.fetchone()
        
        # Get monthly costs for the last 12 months
        cursor.execute("""
            SELECT 
                YEAR(date_day) as year,
                MONTH(date_day) as month,
                SUM(total_cost) as monthly_cost
            FROM energy_costs 
            WHERE date_day >= DATE_SUB(CURDATE(), INTERVAL 12 MONTH)
            GROUP BY YEAR(date_day), MONTH(date_day)
            ORDER BY year, month
        """, )
        
        monthly_costs = cursor.fetchall()
        
        # Get top consuming circuits for today
        cursor.execute("""
            SELECT 
                c.circuit_name,
                SUM(ec.total_cost) as circuit_cost,
                SUM(ec.on_peak_kwh + ec.off_peak_kwh + ec.super_off_peak_kwh) as total_kwh
            FROM energy_costs ec
            JOIN circuits c ON ec.circuit_id = c.id
            WHERE ec.date_day = %s
            GROUP BY c.id, c.circuit_name
            ORDER BY circuit_cost DESC
            LIMIT 10
        """, (today,))
        
        top_circuits = cursor.fetchall()
        
        return jsonify({
            'today': today_costs,
            'monthly': monthly_costs,
            'top_circuits': top_circuits
        })
        
    except Exception as e:
        logger.error(f"Error getting cost analysis: {e}")
        return jsonify({'error': str(e)}), 500
    finally:
        if 'conn' in locals():
            conn.close()

@app.route('/api/circuits')
def get_circuits():
    """Get all circuits configuration"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        cursor.execute("""
            SELECT 
                id,
                circuit_number,
                circuit_name,
                circuit_description,
                circuit_type,
                max_amperage,
                is_active
            FROM circuits 
            ORDER BY circuit_number
        """)
        
        circuits = cursor.fetchall()
        return jsonify(circuits)
        
    except Exception as e:
        logger.error(f"Error getting circuits: {e}")
        return jsonify({'error': str(e)}), 500
    finally:
        if 'conn' in locals():
            conn.close()

@app.route('/api/circuits/<int:circuit_id>', methods=['PUT'])
def update_circuit(circuit_id):
    """Update circuit configuration"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        data = request.get_json()
        
        cursor.execute("""
            UPDATE circuits 
            SET circuit_name = %s, 
                circuit_description = %s,
                max_amperage = %s,
                is_active = %s
            WHERE id = %s
        """, (
            data.get('circuit_name'),
            data.get('circuit_description'),
            data.get('max_amperage'),
            data.get('is_active', True),
            circuit_id
        ))
        
        conn.commit()
        return jsonify({'success': True})
        
    except Exception as e:
        logger.error(f"Error updating circuit: {e}")
        return jsonify({'error': str(e)}), 500
    finally:
        if 'conn' in locals():
            conn.close()

@app.route('/api/billing-rates')
def get_billing_rates():
    """Get current billing rates"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        cursor.execute("""
            SELECT 
                rate_name,
                rate_type,
                season,
                start_time,
                end_time,
                rate_per_kwh,
                effective_date,
                is_active
            FROM billing_rates 
            WHERE is_active = TRUE
            ORDER BY rate_type, start_time
        """)
        
        rates = cursor.fetchall()
        
        # Convert time objects to strings
        for rate in rates:
            if rate['start_time']:
                rate['start_time'] = str(rate['start_time'])
            if rate['end_time']:
                rate['end_time'] = str(rate['end_time'])
            if rate['effective_date']:
                rate['effective_date'] = rate['effective_date'].isoformat()
        
        return jsonify(rates)
        
    except Exception as e:
        logger.error(f"Error getting billing rates: {e}")
        return jsonify({'error': str(e)}), 500
    finally:
        if 'conn' in locals():
            conn.close()

@app.route('/api/system-status')
def get_system_status():
    """Get system status information"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        # Get device status
        cursor.execute("""
            SELECT 
                device_name,
                ip_address,
                status,
                last_seen,
                firmware_version
            FROM devices 
            ORDER BY last_seen DESC
        """)
        
        devices = cursor.fetchall()
        
        # Get latest reading timestamp
        cursor.execute("""
            SELECT MAX(timestamp) as last_reading
            FROM energy_readings
        """)
        
        last_reading = cursor.fetchone()
        
        # Get database statistics
        cursor.execute("""
            SELECT 
                COUNT(*) as total_readings,
                COUNT(DISTINCT circuit_id) as active_circuits
            FROM energy_readings 
            WHERE timestamp > DATE_SUB(NOW(), INTERVAL 1 DAY)
        """)
        
        stats = cursor.fetchone()
        
        # Convert timestamps to strings
        for device in devices:
            if device['last_seen']:
                device['last_seen'] = device['last_seen'].isoformat()
        
        if last_reading['last_reading']:
            last_reading['last_reading'] = last_reading['last_reading'].isoformat()
        
        return jsonify({
            'devices': devices,
            'last_reading': last_reading,
            'stats': stats,
            'server_time': datetime.now().isoformat()
        })
        
    except Exception as e:
        logger.error(f"Error getting system status: {e}")
        return jsonify({'error': str(e)}), 500
    finally:
        if 'conn' in locals():
            conn.close()

@app.route('/api/export-data')
def export_data():
    """Export data for external analysis"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        # Get date range from query parameters
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        export_type = request.args.get('type', 'daily')  # daily, hourly, or raw
        
        if not start_date or not end_date:
            return jsonify({'error': 'start_date and end_date are required'}), 400
        
        if export_type == 'daily':
            cursor.execute("""
                SELECT 
                    c.circuit_name,
                    ed.date_day,
                    ed.total_energy_kwh,
                    ed.avg_power,
                    ed.max_power,
                    ed.cost_estimate
                FROM energy_daily ed
                JOIN circuits c ON ed.circuit_id = c.id
                WHERE ed.date_day BETWEEN %s AND %s
                ORDER BY ed.date_day, c.circuit_number
            """, (start_date, end_date))
        elif export_type == 'hourly':
            cursor.execute("""
                SELECT 
                    c.circuit_name,
                    eh.hour_start,
                    eh.avg_power,
                    eh.total_energy_kwh,
                    eh.sample_count
                FROM energy_hourly eh
                JOIN circuits c ON eh.circuit_id = c.id
                WHERE DATE(eh.hour_start) BETWEEN %s AND %s
                ORDER BY eh.hour_start, c.circuit_number
            """, (start_date, end_date))
        else:  # raw data
            cursor.execute("""
                SELECT 
                    c.circuit_name,
                    er.timestamp,
                    er.voltage,
                    er.current_amps,
                    er.power_watts,
                    er.energy_kwh,
                    er.power_factor,
                    er.frequency
                FROM energy_readings er
                JOIN circuits c ON er.circuit_id = c.id
                WHERE DATE(er.timestamp) BETWEEN %s AND %s
                ORDER BY er.timestamp, c.circuit_number
                LIMIT 10000
            """, (start_date, end_date))
        
        data = cursor.fetchall()
        
        # Convert timestamps/dates to strings
        for record in data:
            for key, value in record.items():
                if isinstance(value, (datetime, type(datetime.now().date()))):
                    record[key] = value.isoformat()
        
        return jsonify(data)
        
    except Exception as e:
        logger.error(f"Error exporting data: {e}")
        return jsonify({'error': str(e)}), 500
    finally:
        if 'conn' in locals():
            conn.close()

def run_data_aggregation():
    """Background task to aggregate data hourly and daily"""
    while True:
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            
            # Aggregate hourly data
            current_hour = datetime.now().replace(minute=0, second=0, microsecond=0)
            last_hour = current_hour - timedelta(hours=1)
            
            cursor.execute("""
                INSERT INTO energy_hourly (
                    circuit_id, hour_start, avg_voltage, avg_current, 
                    avg_power, min_power, max_power, total_energy_kwh, sample_count
                )
                SELECT 
                    circuit_id,
                    %s as hour_start,
                    AVG(voltage) as avg_voltage,
                    AVG(current_amps) as avg_current,
                    AVG(power_watts) as avg_power,
                    MIN(power_watts) as min_power,
                    MAX(power_watts) as max_power,
                    SUM(power_watts) / 3600000 as total_energy_kwh,
                    COUNT(*) as sample_count
                FROM energy_readings
                WHERE timestamp >= %s AND timestamp < %s
                GROUP BY circuit_id
                ON DUPLICATE KEY UPDATE
                    avg_voltage = VALUES(avg_voltage),
                    avg_current = VALUES(avg_current),
                    avg_power = VALUES(avg_power),
                    min_power = VALUES(min_power),
                    max_power = VALUES(max_power),
                    total_energy_kwh = VALUES(total_energy_kwh),
                    sample_count = VALUES(sample_count)
            """, (last_hour, last_hour, current_hour))
            
            # Aggregate daily data
            yesterday = (datetime.now() - timedelta(days=1)).date()
            
            cursor.execute("""
                INSERT INTO energy_daily (
                    circuit_id, date_day, avg_voltage, avg_current,
                    avg_power, min_power, max_power, total_energy_kwh
                )
                SELECT 
                    circuit_id,
                    %s as date_day,
                    AVG(avg_voltage) as avg_voltage,
                    AVG(avg_current) as avg_current,
                    AVG(avg_power) as avg_power,
                    MIN(min_power) as min_power,
                    MAX(max_power) as max_power,
                    SUM(total_energy_kwh) as total_energy_kwh
                FROM energy_hourly
                WHERE DATE(hour_start) = %s
                GROUP BY circuit_id
                ON DUPLICATE KEY UPDATE
                    avg_voltage = VALUES(avg_voltage),
                    avg_current = VALUES(avg_current),
                    avg_power = VALUES(avg_power),
                    min_power = VALUES(min_power),
                    max_power = VALUES(max_power),
                    total_energy_kwh = VALUES(total_energy_kwh)
            """, (yesterday, yesterday))
            
            conn.commit()
            logger.info("Data aggregation completed")
            
        except Exception as e:
            logger.error(f"Error in data aggregation: {e}")
        finally:
            if 'conn' in locals():
                conn.close()
        
        # Wait 1 hour before next aggregation
        time.sleep(3600)

@app.errorhandler(404)
def not_found(error):
    return jsonify({'error': 'Endpoint not found'}), 404

@app.errorhandler(500)
def internal_error(error):
    return jsonify({'error': 'Internal server error'}), 500

if __name__ == '__main__':
    # Start background aggregation task
    aggregation_thread = threading.Thread(target=run_data_aggregation, daemon=True)
    aggregation_thread.start()
    
    # Start Flask app
    app.run(
        host='0.0.0.0',
        port=int(os.getenv('PORT', 5000)),
        debug=os.getenv('DEBUG', 'False').lower() == 'true'
    )
