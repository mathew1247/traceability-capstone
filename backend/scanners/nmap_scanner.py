import shutil
import socket
from utils.logger import app_logger

# Known Industrial & OT / IT critical ports
CRITICAL_PORTS = {
    21: "ftp",
    23: "telnet",
    135: "msrpc",
    139: "netbios-ssn",
    445: "microsoft-ds",
    502: "modbus-tcp",       # Industrial PLC Protocol
    102: "s7comm",           # Siemens S7 PLC Protocol
    2222: "ethernet-ip",     # Rockwell Industrial Protocol
    3389: "ms-wbt-server"    # RDP
}

COMMON_PROBE_PORTS = [
    (21, "ftp"),
    (22, "ssh"),
    (23, "telnet"),
    (53, "dns"),
    (80, "http"),
    (102, "s7comm"),
    (443, "https"),
    (445, "microsoft-ds"),
    (502, "modbus-tcp"),
    (1883, "mqtt"),
    (2222, "ethernet-ip"),
    (3000, "frontend-ui"),
    (3389, "rdp"),
    (4840, "opc-ua"),
    (5000, "flask-api"),
    (8080, "http-alt")
]

def is_nmap_installed():
    return shutil.which('nmap') is not None

def probe_host_ports(ip_str, timeout=0.15):
    """
    Performs real TCP socket connection tests against known standard and critical ports.
    Never returns fabricated or synthetic data.
    """
    open_ports = []
    for test_port, svc_name in COMMON_PROBE_PORTS:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(timeout)
        try:
            res = s.connect_ex((ip_str, test_port))
            if res == 0:
                open_ports.append({
                    "port": test_port,
                    "protocol": "tcp",
                    "service": svc_name,
                    "state": "open",
                    "is_critical": test_port in CRITICAL_PORTS
                })
        except Exception:
            pass
        finally:
            s.close()
    return open_ports

def scan_network(target, require_nmap=False, timeout_seconds=30):
    """
    Executes network scan against the validated target.
    Uses nmap.PortScanner if Nmap binary is installed.
    Enforces safe timeout and process termination.
    Provides truthful socket TCP fallback when binary is absent.
    Never returns fabricated hosts.
    Returns (result_dict, error_message)
    """
    clean_target = target.strip()
    nmap_executable = shutil.which('nmap')

    if require_nmap and not nmap_executable:
        return None, "Nmap binary is not installed on this system. Please ensure Nmap is installed and available in PATH."

    if nmap_executable:
        try:
            import nmap
            nm = nmap.PortScanner()
            app_logger.info(f"Executing Nmap scan against target: {clean_target}")

            # Safe, fast ping & top ports scan (-F fast mode, -T4 timing)
            # timeout parameter passed to nm.scan enforces Python process termination
            nm.scan(hosts=clean_target, arguments=f'-sT -F -T4 --host-timeout {timeout_seconds}s', timeout=timeout_seconds + 5)

            hosts_list = []
            for host in nm.all_hosts():
                host_info = {
                    "ip": host,
                    "status": nm[host].state(),
                    "hostname": nm[host].hostname() or "",
                    "ports": []
                }

                for proto in nm[host].all_protocols():
                    ports = nm[host][proto].keys()
                    for port in sorted(ports):
                        port_data = nm[host][proto][port]
                        host_info["ports"].append({
                            "port": int(port),
                            "protocol": proto,
                            "service": port_data.get('name', 'unknown'),
                            "state": port_data.get('state', 'open'),
                            "is_critical": int(port) in CRITICAL_PORTS
                        })

                hosts_list.append(host_info)

            return {
                "target": clean_target,
                "devices_found": len(hosts_list),
                "hosts": hosts_list,
                "scanner_engine": "Nmap Native Engine",
                "nmap_available": True,
                "limitations": None
            }, None

        except Exception as e:
            err_str = str(e)
            is_timeout = "PortScannerTimeout" in type(e).__name__ or "timed out" in err_str.lower()
            if is_timeout:
                app_logger.error(f"Nmap scan timed out against target {clean_target}: {err_str}")
                return None, f"Network scan timed out after {timeout_seconds} seconds."

            # If nmap was explicitly required, or if it failed with PortScannerError
            if require_nmap or "PortScannerError" in type(e).__name__:
                app_logger.error(f"Nmap execution error against target {clean_target}: {err_str}")
                return None, f"Nmap execution error: {err_str}"

            app_logger.warning(f"Nmap execution encountered error: {err_str}. Utilizing fallback socket scanner.")

    # Truthful Socket TCP Fallback
    # Runs when Nmap is not installed or unavailable
    app_logger.info(f"Running fallback TCP socket discovery for target: {clean_target}")
    hosts_list = []

    if clean_target in ('127.0.0.1', 'localhost', '127.0.0.1/32'):
        open_ports = probe_host_ports('127.0.0.1', timeout=0.1)
        hosts_list.append({
            "ip": "127.0.0.1",
            "status": "up",
            "hostname": "localhost",
            "ports": open_ports
        })
    elif '/' in clean_target:
        # For CIDR subnets, probe standard gateway addresses (.1, .254)
        subnet_prefix = clean_target.rsplit('.', 1)[0]
        candidate_ips = [f"{subnet_prefix}.1", f"{subnet_prefix}.254"]
        for cand_ip in candidate_ips:
            open_ports = probe_host_ports(cand_ip, timeout=0.08)
            if open_ports:
                hosts_list.append({
                    "ip": cand_ip,
                    "status": "up",
                    "hostname": "",
                    "ports": open_ports
                })
    else:
        # Single target IP
        open_ports = probe_host_ports(clean_target, timeout=0.15)
        if open_ports:
            hosts_list.append({
                "ip": clean_target,
                "status": "up",
                "hostname": "",
                "ports": open_ports
            })

    return {
        "target": clean_target,
        "devices_found": len(hosts_list),
        "hosts": hosts_list,
        "scanner_engine": "Python Socket Fallback (Nmap unavailable)",
        "nmap_available": False,
        "limitations": "Nmap binary is not installed on this system. Operating in non-privileged TCP socket fallback mode. ICMP sweeps, OS fingerprinting, and raw SYN packet inspection are unavailable."
    }, None
