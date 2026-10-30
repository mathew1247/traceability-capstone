import re
import ipaddress
from config import Config

EMAIL_REGEX = re.compile(r'^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$')

VALID_ROLES = {'Admin', 'Inspector', 'Auditor', 'Operator'}
VALID_USER_STATUSES = {'Active', 'Inactive', 'Suspended'}
VALID_PRODUCT_STATUSES = {'In Production', 'Certified', 'Quarantined', 'Active', 'Discontinued'}
VALID_BATCH_STATUSES = {'Completed', 'In QA Inspection', 'Passed', 'Running', 'Pending', 'Failed'}
VALID_COMPLIANCE_STANDARDS = {'ISO 9001:2015', 'RoHS', 'GMP', 'ISO 27001', 'FDA'}
VALID_COMPLIANCE_STATUSES = {'Compliant', 'Pending', 'Expired', 'Non-Compliant', 'Review Required'}
VALID_ALERT_SEVERITIES = {'Critical', 'Warning', 'Notice'}
VALID_ALERT_STATUSES = {'Open', 'Active', 'Acknowledged', 'Resolved', 'Dismissed'}

def validate_email(email):
    """Checks whether the given string is a valid email address."""
    if not email or not isinstance(email, str):
        return False
    return bool(EMAIL_REGEX.match(email.strip()))


def validate_required_fields(data, required_fields):
    """
    Checks if all required fields are present and non-empty in the input dictionary.
    Returns list of missing field names.
    """
    if not isinstance(data, dict):
        return list(required_fields)
    missing = []
    for field in required_fields:
        if field not in data or data[field] is None or (isinstance(data[field], str) and not data[field].strip()):
            missing.append(field)
    return missing


def validate_role(role):
    return role in VALID_ROLES


def validate_product_status(status):
    return status in VALID_PRODUCT_STATUSES


def validate_batch_status(status):
    return status in VALID_BATCH_STATUSES


def validate_compliance_standard(standard):
    return standard in VALID_COMPLIANCE_STANDARDS


def validate_compliance_status(status):
    return status in VALID_COMPLIANCE_STATUSES


def validate_alert_severity(severity):
    return severity in VALID_ALERT_SEVERITIES


def validate_alert_status(status):
    return status in VALID_ALERT_STATUSES


def validate_network_target(target):
    """
    Validates network scan targets:
    1. Checks if it's a valid non-empty string within safe length limits (<= 64 chars).
    2. Explicitly rejects IPv6 addresses and networks with a clear message.
    3. Rejects invalid, unspecified (0.0.0.0), multicast (224.0.0.0/4), and reserved addresses.
    4. Enforces authorized scope (RFC 1918 private IPv4 or IPv4 loopback only).
       Disallows arbitrary public Internet scanning for security compliance.
    5. Enforces max CIDR subnet size (/24 to /32) to prevent unbounded scan workloads.
    Returns (is_valid: bool, error_message: str or None)
    """
    if target is None or not isinstance(target, str):
        return False, "Target must be a non-empty string."

    clean_target = target.strip()
    if not clean_target:
        return False, "Target must be a non-empty string."

    if len(clean_target) > 64:
        return False, "Target string exceeds maximum allowable length of 64 characters."

    if clean_target in ('localhost', '127.0.0.1', '127.0.0.1/32'):
        return True, None

    # Check for IPv6 notation (contains colon)
    if ':' in clean_target:
        return False, "IPv6 scanning is not supported. Please specify an IPv4 address or CIDR range."

    try:
        if '/' in clean_target:
            net = ipaddress.ip_network(clean_target, strict=False)
            if net.version != 4:
                return False, "IPv6 scanning is not supported. Please specify an IPv4 address or CIDR range."
            if net.prefixlen < 24:
                return False, f"Target subnet /{net.prefixlen} is too broad. Please specify a /24 or narrower subnet (e.g., 192.168.1.0/24)."
            if net.prefixlen > 32:
                return False, f"Invalid CIDR prefix length: /{net.prefixlen}."
            if not (net.is_private or net.is_loopback):
                return False, f"Target {clean_target} is outside authorized private network scopes. External scanning is prohibited."
            if net.is_multicast or net.is_reserved:
                return False, f"Target {clean_target} is a multicast or reserved range and cannot be scanned."
            return True, None
        else:
            ip = ipaddress.ip_address(clean_target)
            if ip.version != 4:
                return False, "IPv6 scanning is not supported. Please specify an IPv4 address or CIDR range."
            if ip.is_unspecified:
                return False, "Target address 0.0.0.0 is non-routable and cannot be scanned."
            if ip.is_multicast:
                return False, f"Target IP {clean_target} is a multicast address and cannot be scanned."
            if ip.is_reserved:
                return False, f"Target IP {clean_target} is a reserved address and cannot be scanned."
            if not (ip.is_private or ip.is_loopback):
                return False, f"Target IP {clean_target} is outside authorized private network scopes. External scanning is prohibited."
            return True, None
    except ValueError:
        return False, f"Invalid IP address or CIDR notation: {clean_target}"
