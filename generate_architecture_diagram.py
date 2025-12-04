#!/usr/bin/env python3
"""
Generiert ein Architektur-Diagramm für den ÖWA Reporter
"""

import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch
import numpy as np

# Figur erstellen
fig, ax = plt.subplots(1, 1, figsize=(16, 12))
ax.set_xlim(0, 16)
ax.set_ylim(0, 12)
ax.axis('off')
ax.set_facecolor('#1a1a2e')
fig.patch.set_facecolor('#1a1a2e')

# Farben
colors = {
    'infonline': '#FF6B6B',      # Rot
    'airtable': '#4ECDC4',       # Türkis
    'gitlab': '#FC6D26',         # Orange (GitLab)
    'github': '#6e5494',         # Lila (GitHub)
    'streamlit': '#FF4B4B',      # Rot (Streamlit)
    'teams': '#6264A7',          # Lila (Teams)
    'openai': '#10A37F',         # Grün (OpenAI)
    'user': '#FFE66D',           # Gelb
    'arrow': '#FFFFFF',          # Weiß
    'text': '#FFFFFF',           # Weiß
}

def draw_box(ax, x, y, width, height, color, label, sublabel=""):
    """Zeichnet eine Box mit Label"""
    box = FancyBboxPatch((x, y), width, height, 
                          boxstyle="round,pad=0.05,rounding_size=0.2",
                          facecolor=color, edgecolor='white', linewidth=2, alpha=0.9)
    ax.add_patch(box)
    
    # Hauptlabel
    ax.text(x + width/2, y + height/2 + (0.15 if sublabel else 0), label, 
            ha='center', va='center', fontsize=11, fontweight='bold', color='white')
    
    # Sublabel
    if sublabel:
        ax.text(x + width/2, y + height/2 - 0.25, sublabel, 
                ha='center', va='center', fontsize=8, color='white', alpha=0.8)

def draw_arrow(ax, start, end, color='white', style='->'):
    """Zeichnet einen Pfeil"""
    ax.annotate('', xy=end, xytext=start,
                arrowprops=dict(arrowstyle=style, color=color, lw=2))

def draw_label_on_arrow(ax, start, end, label, offset=(0, 0.2)):
    """Zeichnet ein Label auf einem Pfeil"""
    mid_x = (start[0] + end[0]) / 2 + offset[0]
    mid_y = (start[1] + end[1]) / 2 + offset[1]
    ax.text(mid_x, mid_y, label, ha='center', va='center', fontsize=7, 
            color='white', alpha=0.8, style='italic')

# Titel
ax.text(8, 11.5, '📊 ÖWA REPORTER - SYSTEMARCHITEKTUR', 
        ha='center', va='center', fontsize=18, fontweight='bold', color='white')
ax.text(8, 11, 'Vollständige Übersicht aller Komponenten und Datenflüsse', 
        ha='center', va='center', fontsize=10, color='white', alpha=0.7)

# ===== KOMPONENTEN =====

# INFOnline API (oben)
draw_box(ax, 6.5, 9, 3, 1.2, colors['infonline'], 'INFOnline', 'ÖWA API')

# Airtable (links, 2 Boxen)
draw_box(ax, 1, 6.5, 2.5, 1.2, colors['airtable'], 'Airtable', 'Automations')
draw_box(ax, 1, 4.5, 2.5, 1.2, colors['airtable'], 'Airtable', 'Measurements DB')

# GitLab (Mitte)
draw_box(ax, 6.5, 6.5, 3, 1.2, colors['gitlab'], 'GitLab CI/CD', 'Jobs & Pipelines')

# GitHub (rechts von GitLab)
draw_box(ax, 11, 6.5, 2.5, 1.2, colors['github'], 'GitHub', 'Repository')

# Streamlit (unten rechts)
draw_box(ax, 11, 4.5, 2.5, 1.2, colors['streamlit'], 'Streamlit', 'Cloud Dashboard')

# MS Teams (unten links)
draw_box(ax, 1, 2, 2.5, 1.2, colors['teams'], 'MS Teams', 'Benachrichtigungen')

# OpenAI (unten mitte-links)
draw_box(ax, 5, 2, 2.5, 1.2, colors['openai'], 'OpenAI', 'GPT-4o-mini')

# Imgur (unten mitte-rechts)
draw_box(ax, 9, 2, 2.5, 1.2, '#E91E63', 'Imgur', 'Bild-Upload')

# Benutzer (ganz unten)
draw_box(ax, 11, 0.5, 2.5, 1.2, colors['user'], '👤 Benutzer', 'Browser')

# ===== PFEILE & DATENFLÜSSE =====

# INFOnline -> GitLab (Daten abrufen)
draw_arrow(ax, (8, 9), (8, 7.7))
draw_label_on_arrow(ax, (8, 9), (8, 7.7), 'API Daten', (0.7, 0))

# GitLab -> Airtable DB (Daten speichern)
draw_arrow(ax, (6.5, 7.1), (3.5, 5.5))
draw_label_on_arrow(ax, (6.5, 7.1), (3.5, 5.5), 'Speichern', (-0.3, 0.3))

# Airtable Automations -> GitLab (Trigger)
draw_arrow(ax, (3.5, 7.1), (6.5, 7.1))
draw_label_on_arrow(ax, (3.5, 7.1), (6.5, 7.1), 'Trigger Jobs', (0, 0.25))

# GitLab -> GitHub (Code sync)
draw_arrow(ax, (9.5, 7.1), (11, 7.1))
draw_label_on_arrow(ax, (9.5, 7.1), (11, 7.1), 'git push', (0, 0.25))

# GitHub -> Streamlit (Deploy)
draw_arrow(ax, (12.25, 6.5), (12.25, 5.7))
draw_label_on_arrow(ax, (12.25, 6.5), (12.25, 5.7), 'Deploy', (0.5, 0))

# Airtable DB -> Streamlit (Daten lesen)
draw_arrow(ax, (3.5, 5.1), (11, 5.1))
draw_label_on_arrow(ax, (3.5, 5.1), (11, 5.1), 'Lesen (API)', (0, 0.25))

# Streamlit -> Benutzer
draw_arrow(ax, (12.25, 4.5), (12.25, 1.7))
draw_label_on_arrow(ax, (12.25, 4.5), (12.25, 1.7), 'Dashboard', (0.6, 0))

# GitLab -> Teams
draw_arrow(ax, (6.5, 6.5), (3.5, 3.2))
draw_label_on_arrow(ax, (6.5, 6.5), (3.5, 3.2), 'Notifications', (-0.5, 0.2))

# GitLab -> OpenAI
draw_arrow(ax, (7.5, 6.5), (6.25, 3.2))
draw_label_on_arrow(ax, (7.5, 6.5), (6.25, 3.2), 'KI-Analyse', (0.5, 0))

# GitLab -> Imgur
draw_arrow(ax, (8.5, 6.5), (10.25, 3.2))
draw_label_on_arrow(ax, (8.5, 6.5), (10.25, 3.2), 'Bilder', (-0.3, 0.2))

# Airtable Automations <-> Airtable DB
draw_arrow(ax, (2.25, 6.5), (2.25, 5.7), style='<->')

# ===== LEGENDE =====
legend_y = 0.5
legend_items = [
    (colors['infonline'], 'Datenquelle'),
    (colors['airtable'], 'Speicher & Trigger'),
    (colors['gitlab'], 'CI/CD'),
    (colors['github'], 'Code Repository'),
    (colors['streamlit'], 'Dashboard'),
    (colors['teams'], 'Notifications'),
]

ax.text(1, legend_y + 0.8, 'Legende:', fontsize=9, fontweight='bold', color='white')
for i, (color, label) in enumerate(legend_items):
    x = 1 + (i % 3) * 2.5
    y = legend_y if i < 3 else legend_y - 0.5
    rect = mpatches.Rectangle((x, y), 0.3, 0.3, facecolor=color, edgecolor='white')
    ax.add_patch(rect)
    ax.text(x + 0.4, y + 0.15, label, fontsize=8, color='white', va='center')

# ===== JOBS BOX =====
jobs_text = """GitLab Jobs:
• daily_ingest (23:59)
• weekly_report (Mo 20:00)
• alert_check
• backfill"""
ax.text(14.5, 9, jobs_text, fontsize=8, color='white', 
        va='top', ha='left', family='monospace',
        bbox=dict(boxstyle='round', facecolor='#2d2d44', edgecolor='white', alpha=0.8))

# Speichern
plt.tight_layout()
plt.savefig('oewa_architecture.png', dpi=150, facecolor='#1a1a2e', 
            edgecolor='none', bbox_inches='tight', pad_inches=0.5)
plt.savefig('oewa_architecture_light.png', dpi=150, facecolor='white', 
            edgecolor='none', bbox_inches='tight', pad_inches=0.5)

print("✅ Diagramme erstellt:")
print("   📊 oewa_architecture.png (Dark Mode)")
print("   📊 oewa_architecture_light.png (Light Mode)")

plt.show()

