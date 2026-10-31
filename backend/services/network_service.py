import uuid
from datetime import datetime, timezone
from config import Config
from config.firebase import db
from scanners.nmap_scanner import scan_network
from services.activity_log_service import log_activity
from services.alert_service import create_alert
from utils.validators import validate_network_target
from utils.logger import app_logger

def execute_network_scan(target, current_user, ip_address=None):
    """
    Requirements 17, 18, 19, 21:
    1. Validates target authorization scope.
    2. Runs Nmap / safe discovery engine.
    3. Detects newly observed hosts vs previous scan baseline (Unknown Host Detection).
    4. Detects exposed critical/industrial ports.
    5. Stores scan in network_scans collection (both successful and failed scans).
    6. Returns structured results.
    """
    start_time = datetime.now(timezone.utc)
    now_iso = start_time.isoformat()
    scan_id = f"SCAN-{uuid.uuid4().hex[:6].upper()}"

    is_valid, err_msg = validate_network_target(target)
    if not is_valid:
        return None, err_msg, 400

    scan_result, scan_err = scan_network(target)
    duration_seconds = round((datetime.now(timezone.utc) - start_time).total_seconds(), 2)

    if scan_err:
        # Record failed scan record in Firestore for auditability
        failed_record = {
            "scan_id": scan_id,
            "target": target.strip(),
            "devices_found": 0,
            "open_ports": [],
            "status": "Failed",
            "error_message": str(scan_err),
            "created_by": current_user.get('user_id'),
            "scan_date": now_iso,
            "duration": f"{duration_seconds}s",
            "duration_seconds": duration_seconds,
            "hosts": [],
            "scanner_engine": "Nmap Scanner",
            "nmap_available": False,
            "limitations": str(scan_err),
            "new_hosts_detected": []
        }
        try:
            db.collection(Config.COLLECTION_NETWORK_SCANS).document(scan_id).set(failed_record)
        except Exception as db_err:
            app_logger.error(f"Failed to record failed scan entry in Firestore: {db_err}")

        return None, f"Network scan failure: {scan_err}", 500

    # Extract all discovered open ports
    all_open_ports = []
    current_ips = set()
    critical_ports_found = []

    for host in scan_result.get('hosts', []):
        ip = host.get('ip')
        if ip:
            current_ips.add(ip)
        for p in host.get('ports', []):
            port_entry = {
                "host": ip,
                "port": p.get('port'),
                "protocol": p.get('protocol'),
                "service": p.get('service'),
                "state": p.get('state'),
                "is_critical": p.get('is_critical', False)
            }
            all_open_ports.append(port_entry)
            if p.get('is_critical'):
                critical_ports_found.append((ip, p.get('port'), p.get('service')))

    # Requirement 21: Unknown Host Detection by comparing with latest previous scan
    newly_observed_hosts = []
    try:
        previous_scans = db.collection(Config.COLLECTION_NETWORK_SCANS)\
                           .order_by('scan_date', direction='DESCENDING')\
                           .limit(1)\
                           .get()

        prev_ips = set()
        for doc in previous_scans:
            prev_data = doc.to_dict()
            for h in prev_data.get('hosts', []):
                if h.get('ip'):
                    prev_ips.add(h['ip'])

        if prev_ips:  # Only if a previous baseline exists
            newly_observed_hosts = list(current_ips - prev_ips)
            for new_ip in newly_observed_hosts:
                create_alert(
                    severity="Warning",
                    source="Nmap Scanner",
                    message=f"Previously unseen host detected: {new_ip} on subnet {target}.",
                    resource_id=scan_id
                )
    except Exception as base_err:
        app_logger.warning(f"Baseline comparison failed: {base_err}")

    # Trigger alerts for exposed critical ports
    for ip, port, service in critical_ports_found:
        create_alert(
            severity="Warning" if port in (502, 102, 2222) else "Notice",
            source="Nmap Scanner",
            message=f"Industrial OT/IT port {port} ({service}) exposed on device {ip}.",
            resource_id=scan_id
        )

    scan_record = {
        "scan_id": scan_id,
        "target": target.strip(),
        "devices_found": scan_result.get('devices_found', len(current_ips)),
        "open_ports": all_open_ports,
        "status": "Completed",
        "created_by": current_user.get('user_id'),
        "scan_date": now_iso,
        "duration": f"{duration_seconds}s",
        "duration_seconds": duration_seconds,
        "hosts": scan_result.get('hosts', []),
        "scanner_engine": scan_result.get('scanner_engine', 'Nmap Native Engine'),
        "nmap_available": scan_result.get('nmap_available', False),
        "limitations": scan_result.get('limitations'),
        "new_hosts_detected": newly_observed_hosts
    }

    try:
        db.collection(Config.COLLECTION_NETWORK_SCANS).document(scan_id).set(scan_record)
    except Exception as e:
        app_logger.error(f"Failed to persist scan record {scan_id} to Firestore: {str(e)}")
        return None, f"Database error: Unable to record network scan. {str(e)}", 500

    try:
        log_activity(
            user_id=current_user.get('user_id'),
            username=current_user.get('username'),
            action='SCAN_TRIGGER',
            resource='NetworkScan',
            resource_id=scan_id,
            details=f"Executed network scan on {target}. Found {scan_record['devices_found']} devices.",
            ip_address=ip_address
        )
    except Exception as log_err:
        app_logger.warning(f"Activity log failed for network scan: {log_err}")

    return scan_record, None, 201


def get_scan_history(limit=20):
    """Fetches past network scan records."""
    try:
        docs = db.collection(Config.COLLECTION_NETWORK_SCANS)\
                 .order_by('scan_date', direction='DESCENDING')\
                 .limit(limit)\
                 .get()
        return [doc.to_dict() for doc in docs if doc.to_dict()]
    except Exception as e:
        app_logger.error(f"Failed to fetch network scan history: {str(e)}")
        return []


def get_security_monitor_summary():
    """
    Requirement 20:
    Aggregates network security observations:
    network_status, active_devices, suspicious_hosts, open_critical_ports, threat_level, recent_events.
    """
    scans = get_scan_history(limit=10)
    # Prefer the most recent scan that discovered devices/open ports; fallback to latest scan
    latest_scan = None
    for s in scans:
        if s.get('devices_found', 0) > 0 or s.get('open_ports'):
            latest_scan = s
            break
    if not latest_scan and scans:
        latest_scan = scans[0]

    devices_count = latest_scan.get('devices_found', 0) if latest_scan else 0
    all_open_ports = latest_scan.get('open_ports', []) if latest_scan else []

    critical_ports_list = [p for p in all_open_ports if p.get('is_critical')]
    critical_ports_count = len(critical_ports_list)

    # Active security alerts count
    active_alerts = db.collection(Config.COLLECTION_ALERTS)\
                      .where('source', '==', 'Nmap Scanner')\
                      .where('status', '==', 'Active')\
                      .get()
    active_alert_count = len(active_alerts)

    # Resolve suspicious / newly detected hosts from latest scan
    new_host_ips = set(latest_scan.get('new_hosts_detected', [])) if latest_scan else set()
    suspicious_hosts_list = []

    if latest_scan:
        for h in latest_scan.get('hosts', []):
            ip = h.get('ip')
            if ip in new_host_ips or h.get('status') == 'unverified':
                suspicious_hosts_list.append({
                    "ip": ip,
                    "risk": "Unverified Host",
                    "hostname": h.get('hostname', ''),
                    "mac": h.get('mac', 'N/A'),
                    "vendor": h.get('vendor', 'Unregistered Host')
                })
        found_ips = {h.get('ip') for h in suspicious_hosts_list}
        for ip in new_host_ips:
            if ip not in found_ips:
                suspicious_hosts_list.append({
                    "ip": ip,
                    "risk": "Unverified Host",
                    "hostname": "",
                    "mac": "N/A",
                    "vendor": "Unregistered Host"
                })

    suspicious_count = len(suspicious_hosts_list)

    threat_level = "Low"
    network_status = "Secure"

    if active_alert_count >= 3 or critical_ports_count >= 3 or suspicious_count >= 3:
        threat_level = "High"
        network_status = "Critical"
    elif active_alert_count >= 1 or critical_ports_count >= 1 or suspicious_count >= 1:
        threat_level = "Medium"
        network_status = "Warning"

    # Recent security events
    recent_events = []
    for doc in active_alerts[:5]:
        d = doc.to_dict()
        recent_events.append({
            "event": d.get('message'),
            "severity": d.get('severity'),
            "timestamp": d.get('created_at'),
            "status": d.get('status', 'Active'),
            "ip": d.get('resource_id', 'Subnet')
        })

    return {
        "network_status": network_status,
        "active_devices": devices_count,
        "suspicious_hosts": suspicious_hosts_list,
        "suspicious_hosts_count": suspicious_count,
        "open_critical_ports": critical_ports_list,
        "open_critical_ports_count": critical_ports_count,
        "threat_level": threat_level,
        "recent_events": recent_events,
        "last_scan_date": latest_scan.get('scan_date') if latest_scan else None
    }
