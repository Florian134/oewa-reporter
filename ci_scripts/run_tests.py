#!/usr/bin/env python3
"""
ÖWA Reporter - Test Runner für CI/CD
=====================================
Führt alle Tests aus und sendet Ergebnisse an Teams bei Fehlern.
"""

import subprocess
import sys
import os
import requests
from datetime import datetime

TEAMS_WEBHOOK_URL = os.environ.get("TEAMS_WEBHOOK_URL", "")


def run_tests(test_type: str = "all") -> tuple:
    """
    Führt pytest aus und gibt (success, output) zurück.
    
    Args:
        test_type: "all", "critical", "security", "integration"
    
    Returns:
        (bool, str): (success, output)
    """
    # Basis-Befehl
    cmd = ["python", "-m", "pytest", "tests/", "-v", "--tb=short"]
    
    # Filter nach Test-Typ
    if test_type == "critical":
        cmd.extend(["-m", "critical"])
    elif test_type == "security":
        cmd.extend(["-m", "security"])
    elif test_type == "integration":
        cmd.extend(["-m", "integration"])
    
    # Führe Tests aus
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONIOENCODING": "utf-8"}
    )
    
    output = result.stdout + result.stderr
    success = result.returncode == 0
    
    return success, output


def send_failure_notification(test_type: str, output: str):
    """Sendet Fehler-Benachrichtigung an Teams"""
    if not TEAMS_WEBHOOK_URL:
        print("TEAMS_WEBHOOK_URL nicht gesetzt - keine Benachrichtigung")
        return
    
    # Extrahiere relevante Zeilen (max 500 Zeichen)
    relevant_output = ""
    for line in output.split('\n'):
        if any(keyword in line for keyword in ['FAILED', 'ERROR', 'AssertionError']):
            relevant_output += line + "\n"
    
    relevant_output = relevant_output[:500] if relevant_output else output[-500:]
    
    card = {
        "@type": "MessageCard",
        "@context": "http://schema.org/extensions",
        "summary": f"ÖWA Tests fehlgeschlagen",
        "themeColor": "DC3545",  # Rot
        "sections": [
            {
                "activityTitle": "❌ ÖWA Reporter Tests fehlgeschlagen",
                "activitySubtitle": f"Test-Typ: {test_type}",
                "facts": [
                    {"name": "📅 Zeitpunkt", "value": datetime.now().strftime("%d.%m.%Y %H:%M")},
                    {"name": "🔍 Test-Suite", "value": test_type},
                ],
                "markdown": True
            },
            {
                "title": "📋 Fehler-Details",
                "text": f"```\n{relevant_output}\n```",
                "markdown": True
            }
        ],
        "potentialAction": [
            {
                "@type": "OpenUri",
                "name": "📊 Pipeline öffnen",
                "targets": [
                    {"os": "default", "uri": "https://gitlab.com/Florian1143/oewa-reporter/-/pipelines"}
                ]
            }
        ]
    }
    
    try:
        response = requests.post(TEAMS_WEBHOOK_URL, json=card, timeout=10)
        if response.status_code == 200:
            print("✅ Fehler-Benachrichtigung an Teams gesendet")
        else:
            print(f"⚠️ Teams Webhook Fehler: {response.status_code}")
    except Exception as e:
        print(f"⚠️ Teams Webhook Fehler: {e}")


def main():
    print("=" * 70)
    print("🧪 ÖWA REPORTER - TEST RUNNER")
    print("=" * 70)
    
    # Bestimme Test-Typ aus Argument oder Umgebung
    test_type = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("TEST_TYPE", "all")
    
    print(f"\n🔍 Führe Tests aus: {test_type}")
    print("-" * 70)
    
    success, output = run_tests(test_type)
    
    print(output)
    
    if success:
        print("\n" + "=" * 70)
        print("✅ ALLE TESTS ERFOLGREICH")
        print("=" * 70)
    else:
        print("\n" + "=" * 70)
        print("❌ TESTS FEHLGESCHLAGEN")
        print("=" * 70)
        
        # Sende Benachrichtigung bei Fehlern
        send_failure_notification(test_type, output)
        
        sys.exit(1)


if __name__ == "__main__":
    main()

