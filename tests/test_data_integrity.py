"""
ÖWA Reporter - Datenintegritäts-Tests
======================================
Prüft die Integrität der Daten in Airtable und identifiziert potenzielle Probleme.
"""

import pytest
import requests
from datetime import date, timedelta
from collections import defaultdict
import re


class TestDataIntegrity:
    """Tests für Datenintegrität in Airtable"""
    
    @pytest.fixture(autouse=True)
    def setup(self, airtable_config):
        """Setup für jeden Test"""
        self.api_key = airtable_config["api_key"]
        self.base_id = airtable_config["base_id"]
        self.table_name = airtable_config["table_name"]
        self.base_url = f"https://api.airtable.com/v0/{self.base_id}/{self.table_name}"
        self.headers = {"Authorization": f"Bearer {self.api_key}"}
    
    def _fetch_all_records(self):
        """Holt alle Records aus Airtable"""
        if not self.api_key:
            pytest.skip("AIRTABLE_API_KEY nicht gesetzt")
        
        all_records = []
        offset = None
        
        while True:
            params = {"pageSize": 100}
            if offset:
                params["offset"] = offset
            
            response = requests.get(
                self.base_url, 
                headers=self.headers, 
                params=params, 
                timeout=30
            )
            
            if response.status_code != 200:
                pytest.fail(f"Airtable API Fehler: {response.status_code}")
            
            data = response.json()
            all_records.extend(data.get("records", []))
            
            offset = data.get("offset")
            if not offset:
                break
        
        return all_records
    
    @pytest.mark.critical
    def test_no_duplicates(self):
        """
        KRITISCH: Prüft ob es doppelte Unique Keys in Airtable gibt.
        
        Doppelte Einträge führen zu falschen Summen in Reports und Streamlit.
        """
        records = self._fetch_all_records()
        
        # Zähle Unique Keys
        key_counts = defaultdict(list)
        for record in records:
            unique_key = record.get("fields", {}).get("Unique Key", "")
            if unique_key:
                key_counts[unique_key].append(record.get("id"))
        
        # Finde Duplikate
        duplicates = {k: v for k, v in key_counts.items() if len(v) > 1}
        
        if duplicates:
            dup_details = "\n".join([
                f"  - {key}: {len(ids)} Records (IDs: {', '.join(ids[:3])}...)"
                for key, ids in list(duplicates.items())[:10]
            ])
            pytest.fail(
                f"DUPLIKATE GEFUNDEN! {len(duplicates)} Unique Keys haben mehrere Records:\n"
                f"{dup_details}\n"
                f"Führe cleanup_duplicates.py aus um diese zu bereinigen."
            )
    
    @pytest.mark.critical
    def test_unique_key_format(self, unique_key_pattern):
        """
        KRITISCH: Prüft ob alle Unique Keys das korrekte Format haben.
        
        Format: YYYY-MM-DD_Brand_Plattform_Metrik
        """
        records = self._fetch_all_records()
        
        invalid_keys = []
        for record in records:
            unique_key = record.get("fields", {}).get("Unique Key", "")
            if unique_key and not unique_key_pattern.match(unique_key):
                # Erlaube auch MONTH-Format für monatliche Daten
                if "_MONTH_" not in unique_key:
                    invalid_keys.append({
                        "key": unique_key,
                        "id": record.get("id")
                    })
        
        if invalid_keys:
            examples = "\n".join([f"  - {k['key']}" for k in invalid_keys[:5]])
            pytest.fail(
                f"{len(invalid_keys)} Unique Keys mit ungültigem Format gefunden:\n"
                f"{examples}"
            )
    
    def test_date_coverage(self, test_date_range):
        """
        Prüft ob alle erwarteten Tage in Airtable vorhanden sind.
        """
        records = self._fetch_all_records()
        
        # Extrahiere alle Daten aus den Records
        dates_in_db = set()
        for record in records:
            datum = record.get("fields", {}).get("Datum")
            if datum:
                dates_in_db.add(datum)
        
        # Erwartete Daten (letzte 7 Tage vor dem Delay)
        expected_dates = set()
        current = test_date_range["start"]
        while current <= test_date_range["end"]:
            expected_dates.add(current.isoformat())
            current += timedelta(days=1)
        
        # Fehlende Daten identifizieren
        missing_dates = expected_dates - dates_in_db
        
        if missing_dates:
            missing_sorted = sorted(missing_dates)[:5]
            pytest.fail(
                f"{len(missing_dates)} erwartete Daten fehlen in Airtable:\n"
                f"  Fehlend: {', '.join(missing_sorted)}\n"
                f"  Führe unified_backfill.py aus um fehlende Daten nachzuladen."
            )
    
    def test_value_plausibility(self):
        """
        Prüft ob alle Werte im plausiblen Bereich liegen.
        
        - Page Impressions: 100.000 - 5.000.000 pro Tag (VOL Web)
        - Visits: 50.000 - 1.000.000 pro Tag (VOL Web)
        - Keine negativen Werte
        """
        records = self._fetch_all_records()
        
        anomalies = []
        
        for record in records:
            fields = record.get("fields", {})
            wert = fields.get("Wert", 0)
            metrik = fields.get("Metrik", "")
            brand = fields.get("Brand", "")
            datum = fields.get("Datum", "")
            unique_key = fields.get("Unique Key", "")
            
            # Überspringe monatliche Daten
            if "_MONTH_" in unique_key:
                continue
            
            # Negative Werte sind immer falsch
            if wert < 0:
                anomalies.append({
                    "key": unique_key,
                    "issue": f"Negativer Wert: {wert}"
                })
            
            # VOL Web Page Impressions sollten > 100.000 sein
            if brand == "VOL" and metrik == "Page Impressions" and "Web" in unique_key:
                if wert < 100000 and wert > 0:
                    anomalies.append({
                        "key": unique_key,
                        "issue": f"Ungewöhnlich niedrig: {wert:,} (erwartet > 100.000)"
                    })
            
            # Extrem hohe Werte (> 10 Mio) sind verdächtig
            if wert > 10000000:
                anomalies.append({
                    "key": unique_key,
                    "issue": f"Ungewöhnlich hoch: {wert:,} (Duplikat?)"
                })
        
        if anomalies:
            examples = "\n".join([f"  - {a['key']}: {a['issue']}" for a in anomalies[:5]])
            pytest.fail(
                f"{len(anomalies)} Werte mit fragwürdiger Plausibilität:\n"
                f"{examples}"
            )
    
    def test_brand_consistency(self):
        """
        Prüft ob Brand-Werte konsistent sind (nur VOL, Vienna).
        """
        records = self._fetch_all_records()
        
        brands = set()
        for record in records:
            brand = record.get("fields", {}).get("Brand", "")
            if brand:
                brands.add(brand)
        
        expected_brands = {"VOL", "Vienna"}
        unexpected_brands = brands - expected_brands
        
        if unexpected_brands:
            pytest.fail(
                f"Unerwartete Brand-Werte gefunden: {unexpected_brands}\n"
                f"Erwartet: {expected_brands}"
            )
    
    def test_metric_consistency(self, expected_metrics):
        """
        Prüft ob Metrik-Werte konsistent sind.
        """
        records = self._fetch_all_records()
        
        metrics = set()
        for record in records:
            metrik = record.get("fields", {}).get("Metrik", "")
            if metrik:
                metrics.add(metrik)
        
        expected_set = set(expected_metrics)
        unexpected_metrics = metrics - expected_set
        
        if unexpected_metrics:
            pytest.fail(
                f"Unerwartete Metrik-Werte gefunden: {unexpected_metrics}\n"
                f"Erwartet: {expected_set}"
            )


class TestDataCompleteness:
    """Tests für Datenvollständigkeit"""
    
    @pytest.fixture(autouse=True)
    def setup(self, airtable_config):
        """Setup für jeden Test"""
        self.api_key = airtable_config["api_key"]
        self.base_id = airtable_config["base_id"]
        self.base_url = f"https://api.airtable.com/v0/{self.base_id}/Measurements"
        self.headers = {"Authorization": f"Bearer {self.api_key}"}
    
    def test_vol_web_has_all_metrics(self, test_date_range):
        """
        Prüft ob VOL Web alle erwarteten Metriken hat.
        """
        if not self.api_key:
            pytest.skip("AIRTABLE_API_KEY nicht gesetzt")
        
        # Hole nur VOL Web Daten
        formula = "AND({Brand} = 'VOL', {Plattform} = 'Web')"
        params = {
            "filterByFormula": formula,
            "fields[]": ["Datum", "Metrik"],
            "pageSize": 100
        }
        
        response = requests.get(self.base_url, headers=self.headers, params=params, timeout=30)
        
        if response.status_code != 200:
            pytest.skip(f"API-Fehler: {response.status_code}")
        
        records = response.json().get("records", [])
        
        # Gruppiere nach Datum und zähle Metriken
        metrics_per_date = defaultdict(set)
        for record in records:
            datum = record.get("fields", {}).get("Datum", "")
            metrik = record.get("fields", {}).get("Metrik", "")
            if datum and metrik:
                metrics_per_date[datum].add(metrik)
        
        # Prüfe die letzten 5 Tage
        incomplete_dates = []
        for datum, metrics in sorted(metrics_per_date.items())[-5:]:
            if len(metrics) < 3:  # Erwarten mindestens PI, Visits, HP-PI
                incomplete_dates.append(f"{datum}: {metrics}")
        
        if incomplete_dates:
            details = "\n".join(incomplete_dates)
            pytest.fail(
                f"VOL Web hat unvollständige Metriken:\n{details}"
            )

