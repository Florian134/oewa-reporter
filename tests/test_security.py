"""
ÖWA Reporter - Sicherheits-Tests
=================================
Prüft auf potenzielle Sicherheitslücken und sensible Daten im Repository.
"""

import pytest
import os
import re
from pathlib import Path


class TestSecuritySecrets:
    """Tests für Secrets und API-Keys im Code"""
    
    # Patterns für potenzielle Secrets
    SECRET_PATTERNS = [
        (r'api[_-]?key\s*[=:]\s*["\'][a-zA-Z0-9_-]{20,}["\']', "API Key"),
        (r'secret\s*[=:]\s*["\'][a-zA-Z0-9_-]{20,}["\']', "Secret"),
        (r'password\s*[=:]\s*["\'][^"\']{8,}["\']', "Password"),
        (r'pat[a-zA-Z0-9]{10,}', "Airtable Personal Access Token"),
        (r'sk-[a-zA-Z0-9]{20,}', "OpenAI API Key"),
        (r'https://[^/]+\.webhook\.office\.com/webhookb2/[a-zA-Z0-9-]+', "Teams Webhook URL"),
    ]
    
    # Dateien die übersprungen werden sollen
    SKIP_FILES = [
        '.env',
        '.env.local',
        'env.example',
        '__pycache__',
        '.git',
        'node_modules',
        'venv',
        'Lib',
        'Scripts',
        'Include',
        'share',
        'etc',
        'archive',
        '.cache',
        'site-packages',
        'tests',  # Test-Dateien selbst überspringen
    ]
    
    # Erlaubte Dateiendungen
    SCAN_EXTENSIONS = ['.py', '.yml', '.yaml', '.json', '.md', '.txt', '.sh']
    
    def _should_skip(self, path: Path) -> bool:
        """Prüft ob eine Datei übersprungen werden soll"""
        path_str = str(path)
        for skip in self.SKIP_FILES:
            if skip in path_str:
                return True
        return False
    
    def _scan_file(self, filepath: Path) -> list:
        """Scannt eine Datei nach Secrets"""
        findings = []
        
        try:
            content = filepath.read_text(encoding='utf-8', errors='ignore')
            
            for pattern, secret_type in self.SECRET_PATTERNS:
                matches = re.findall(pattern, content, re.IGNORECASE)
                for match in matches:
                    # Ignoriere Platzhalter
                    if any(placeholder in match.lower() for placeholder in [
                        'your_', 'xxx', 'example', 'placeholder', 'here', 'test_key'
                    ]):
                        continue
                    
                    findings.append({
                        "file": str(filepath),
                        "type": secret_type,
                        "match": match[:50] + "..." if len(match) > 50 else match
                    })
        except Exception:
            pass  # Datei konnte nicht gelesen werden
        
        return findings
    
    @pytest.mark.critical
    @pytest.mark.security
    def test_no_secrets_in_code(self):
        """
        KRITISCH: Scannt alle Code-Dateien nach hardcoded Secrets.
        """
        project_root = Path(__file__).parent.parent
        
        all_findings = []
        
        for ext in self.SCAN_EXTENSIONS:
            for filepath in project_root.rglob(f"*{ext}"):
                if self._should_skip(filepath):
                    continue
                
                findings = self._scan_file(filepath)
                all_findings.extend(findings)
        
        if all_findings:
            details = "\n".join([
                f"  - {f['file']}: {f['type']} ({f['match']})"
                for f in all_findings[:10]
            ])
            pytest.fail(
                f"SICHERHEITSWARNUNG: {len(all_findings)} potenzielle Secrets gefunden:\n"
                f"{details}\n\n"
                f"Entferne diese aus dem Code und verwende Umgebungsvariablen!"
            )
    
    @pytest.mark.security
    def test_gitignore_covers_sensitive_files(self):
        """
        Prüft ob .gitignore alle sensiblen Dateitypen abdeckt.
        """
        project_root = Path(__file__).parent.parent
        gitignore_path = project_root / ".gitignore"
        
        if not gitignore_path.exists():
            pytest.fail(".gitignore existiert nicht!")
        
        content = gitignore_path.read_text()
        
        required_patterns = [
            ".env",
            "*.db",
            "__pycache__",
            "*.log",
            "secrets",
        ]
        
        missing = []
        for pattern in required_patterns:
            if pattern not in content:
                missing.append(pattern)
        
        if missing:
            pytest.fail(
                f".gitignore fehlen wichtige Patterns: {missing}"
            )
    
    @pytest.mark.security
    def test_no_database_files_tracked(self):
        """
        Prüft ob Datenbank-Dateien im Git getrackt werden.
        """
        project_root = Path(__file__).parent.parent
        
        # Finde alle .db Dateien
        db_files = list(project_root.rglob("*.db"))
        db_files += list(project_root.rglob("*.sqlite"))
        db_files += list(project_root.rglob("*.sqlite3"))
        
        # Filter: Nur Dateien die nicht in ignorierten Ordnern sind
        tracked_dbs = []
        for db_file in db_files:
            if not self._should_skip(db_file):
                tracked_dbs.append(str(db_file))
        
        # Hinweis: Wir können hier nicht direkt prüfen ob sie in Git sind,
        # aber wir warnen wenn sie existieren
        if tracked_dbs:
            pytest.fail(
                f"Datenbank-Dateien im Projekt gefunden (sollten in .gitignore sein):\n"
                f"{tracked_dbs}"
            )
    
    @pytest.mark.security
    def test_env_example_has_no_real_values(self):
        """
        Prüft ob env.example nur Platzhalter enthält.
        """
        project_root = Path(__file__).parent.parent
        env_example = project_root / "env.example"
        
        if not env_example.exists():
            pytest.skip("env.example nicht gefunden")
        
        content = env_example.read_text()
        
        # Suche nach verdächtigen Werten
        suspicious = []
        
        for line in content.split('\n'):
            if '=' in line and not line.strip().startswith('#'):
                key, _, value = line.partition('=')
                value = value.strip().strip('"\'')
                
                # Verdächtige Werte (keine Platzhalter)
                if value and not any(placeholder in value.lower() for placeholder in [
                    'your', 'xxx', 'example', 'here', 'todo', 'change', 'replace',
                    'false', 'true', 'http', '...', '0', '1', '2', '3'
                ]):
                    # Prüfe ob es wie ein echter Key aussieht
                    if len(value) > 30 and re.match(r'^[a-zA-Z0-9_-]+$', value):
                        suspicious.append(f"{key}={value[:20]}...")
        
        if suspicious:
            pytest.fail(
                f"env.example enthält möglicherweise echte Werte:\n"
                f"{suspicious}"
            )


class TestCodeQuality:
    """Tests für Code-Qualität und Best Practices"""
    
    @pytest.mark.security
    def test_no_debug_print_statements(self):
        """
        Prüft auf Debug-Print-Statements mit sensiblen Daten.
        """
        project_root = Path(__file__).parent.parent
        
        suspicious_prints = []
        
        for filepath in project_root.rglob("*.py"):
            if "__pycache__" in str(filepath) or "test_" in str(filepath):
                continue
            
            try:
                content = filepath.read_text(encoding='utf-8', errors='ignore')
                lines = content.split('\n')
                
                for i, line in enumerate(lines, 1):
                    # Suche nach print-Statements mit verdächtigen Inhalten
                    if 'print(' in line and any(
                        keyword in line.lower() for keyword in 
                        ['api_key', 'password', 'secret', 'token', 'webhook']
                    ):
                        suspicious_prints.append(f"{filepath}:{i}")
            except Exception:
                pass
        
        if suspicious_prints:
            pytest.fail(
                f"Verdächtige Print-Statements gefunden:\n"
                f"{suspicious_prints[:5]}"
            )
    
    @pytest.mark.security
    def test_exception_handling_no_secrets(self):
        """
        Prüft ob Exception-Handler keine Secrets loggen.
        """
        project_root = Path(__file__).parent.parent
        
        risky_patterns = []
        
        for filepath in project_root.rglob("*.py"):
            if "__pycache__" in str(filepath):
                continue
            
            try:
                content = filepath.read_text(encoding='utf-8', errors='ignore')
                
                # Suche nach Exception-Handling das Variablen mit "key" oder "secret" loggt
                if re.search(r'except.*:\s*\n.*print.*(?:api_key|secret|password)', content, re.IGNORECASE):
                    risky_patterns.append(str(filepath))
            except Exception:
                pass
        
        if risky_patterns:
            pytest.fail(
                f"Exception-Handler könnten Secrets loggen:\n"
                f"{risky_patterns[:5]}"
            )

