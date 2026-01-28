#!/usr/bin/env python3
"""Tests for sync functionality: SVG generation, data processing, and API connectivity.

Also serves as a fixture generator for template dummy SVGs.
Run with --update-fixtures to regenerate the assets/activity.svg, topics.svg, journals.svg files.

Usage:
    pytest tests/test_sync.py           # Run tests only
    python tests/test_sync.py --update-fixtures  # Regenerate SVG fixtures
"""
import math
import os
import sys
from datetime import datetime, timedelta, timezone
import random

import pytest

# Load .env file for local development
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ASSETS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets")

# Mock data for template demonstration
TOPICS_DATA = {
    "machine learning": 24,
    "deep learning": 18,
    "natural language processing": 15,
    "computer vision": 12,
    "data science": 9,
    "statistics": 8,
    "neural networks": 7,
    "optimization": 6,
}

JOURNALS_DATA = {
    "Nature": 16,
    "arXiv": 14,
    "Science": 12,
    "PNAS": 11,
    "Cell": 9,
    "IEEE": 8,
    "ACM": 6,
    "PLOS ONE": 5,
}


def generate_contribution_svg(daily_counts: dict[str, int]) -> str:
    """Generate a GitHub-style contribution graph SVG."""
    colors = ["#ebedf0", "#9be9a7", "#40c463", "#30a14e", "#216e39"]

    today = datetime.now(timezone.utc).date()
    days_since_sunday = today.weekday() + 1 if today.weekday() != 6 else 0
    end_date = today - timedelta(days=days_since_sunday - 6)
    start_date = end_date - timedelta(days=52*7 - 1)
    start_date = start_date - timedelta(days=(start_date.weekday() + 1) % 7)

    max_count = max(daily_counts.values()) if daily_counts else 1

    cell_size = 11
    cell_gap = 3
    total_cell = cell_size + cell_gap
    weeks = 53
    days = 7
    left_padding = 36
    top_padding = 18
    legend_height = 20
    outer_padding = 16

    month_labels = []
    current_month = None
    last_label_week = -4
    for week in range(weeks):
        week_start = start_date + timedelta(days=week * 7)
        if week_start.month != current_month:
            current_month = week_start.month
            if week - last_label_week >= 3:
                month_labels.append((week, week_start.strftime("%b")))
                last_label_week = week

    svg_width = weeks * total_cell + left_padding + 10 + outer_padding * 2
    svg_height = days * total_cell + top_padding + legend_height + outer_padding * 2

    svg = f'''<svg width="{svg_width}" height="{svg_height}" xmlns="http://www.w3.org/2000/svg">
  <rect width="{svg_width}" height="{svg_height}" fill="white"/>
  <style>
    text {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif; font-size: 9px; fill: #57606a; }}
    .legend {{ font-size: 9px; }}
  </style>
'''

    for week, label in month_labels:
        x = outer_padding + left_padding + week * total_cell
        svg += f'  <text x="{x}" y="{outer_padding + 10}">{label}</text>\n'

    day_labels = [(1, "Mon"), (3, "Wed"), (5, "Fri")]
    for day_idx, label in day_labels:
        y = outer_padding + top_padding + day_idx * total_cell + (cell_size / 2) + 3
        svg += f'  <text x="{outer_padding}" y="{y}">{label}</text>\n'

    for week in range(weeks):
        for day in range(days):
            date = start_date + timedelta(days=week * 7 + day)
            if date > today:
                continue

            date_str = date.strftime("%Y-%m-%d")
            count = daily_counts.get(date_str, 0)

            if count == 0:
                level = 0
            elif max_count == 1:
                level = 4 if count > 0 else 0
            else:
                pct = count / max_count
                if pct <= 0.25:
                    level = 1
                elif pct <= 0.50:
                    level = 2
                elif pct <= 0.75:
                    level = 3
                else:
                    level = 4

            color = colors[level]
            x = outer_padding + left_padding + week * total_cell
            y = outer_padding + top_padding + day * total_cell

            svg += f'  <rect x="{x}" y="{y}" width="{cell_size}" height="{cell_size}" rx="2" ry="2" fill="{color}"><title>{date_str}: {count} papers</title></rect>\n'

    legend_y = outer_padding + top_padding + days * total_cell + 8
    legend_text_y = legend_y + cell_size - 1
    box_gap = 4
    text_gap = 5
    boxes_width = 5 * cell_size + 4 * box_gap
    boxes_x = svg_width - outer_padding - 30 - text_gap - boxes_width
    less_x = boxes_x - text_gap
    svg += f'  <text x="{less_x}" y="{legend_text_y}" text-anchor="end" class="legend">Less</text>\n'
    for i, color in enumerate(colors):
        svg += f'  <rect x="{boxes_x + i * (cell_size + box_gap)}" y="{legend_y}" width="{cell_size}" height="{cell_size}" rx="2" ry="2" fill="{color}"/>\n'
    more_x = boxes_x + boxes_width + text_gap
    svg += f'  <text x="{more_x}" y="{legend_text_y}" class="legend">More</text>\n'

    svg += '</svg>'
    return svg


def generate_radar_svg(data: dict[str, int], top_n: int = 8, title_case_labels: bool = False) -> str:
    """Generate a spider/radar chart SVG from label->count data."""
    sorted_data = sorted(data.items(), key=lambda x: (-x[1], x[0]))
    top_items = sorted_data[:top_n]

    if len(top_items) < 3:
        return None

    width = 400
    height = 400
    cx, cy = width // 2, height // 2
    max_radius = 90
    label_radius = max_radius + 35

    n = len(top_items)
    max_count = top_items[0][1]

    angles = [(i * 2 * math.pi / n) - (math.pi / 2) for i in range(n)]

    svg = f'''<svg width="{width}" height="{height}" xmlns="http://www.w3.org/2000/svg">
  <rect width="{width}" height="{height}" fill="white"/>
  <style>
    text {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif; font-size: 11px; fill: #57606a; }}
    .label {{ font-size: 10px; }}
    .value {{ font-size: 9px; fill: #8b949e; }}
  </style>
'''

    rings = 4
    for i in range(1, rings + 1):
        r = (max_radius * i) // rings
        svg += f'  <circle cx="{cx}" cy="{cy}" r="{r}" fill="none" stroke="#d0d7de" stroke-width="1"/>\n'

    for angle in angles:
        x2 = cx + max_radius * math.cos(angle)
        y2 = cy + max_radius * math.sin(angle)
        svg += f'  <line x1="{cx}" y1="{cy}" x2="{x2}" y2="{y2}" stroke="#d0d7de" stroke-width="1"/>\n'

    points = []
    for i, (label, count) in enumerate(top_items):
        ratio = 0.2 + 0.8 * (count / max_count) if max_count > 0 else 0.2
        r = max_radius * ratio
        x = cx + r * math.cos(angles[i])
        y = cy + r * math.sin(angles[i])
        points.append((x, y))

    points_str = " ".join(f"{x},{y}" for x, y in points)
    svg += f'  <polygon points="{points_str}" fill="#9be9a7" fill-opacity="0.5" stroke="#40c463" stroke-width="2"/>\n'

    for x, y in points:
        svg += f'  <circle cx="{x}" cy="{y}" r="4" fill="#40c463"/>\n'

    for i, (label, count) in enumerate(top_items):
        angle = angles[i]
        lx = cx + label_radius * math.cos(angle)
        ly = cy + label_radius * math.sin(angle)

        if angle > math.pi / 4 and angle < 3 * math.pi / 4:
            anchor = "middle"
            ly += 5
        elif angle > -3 * math.pi / 4 and angle < -math.pi / 4:
            anchor = "middle"
            ly -= 15
        elif abs(angle) > math.pi / 2:
            anchor = "end"
        else:
            anchor = "start"

        display = label.title() if title_case_labels else label
        if len(display) > 25:
            display = display[:22] + "..."
        words = display.split()
        lines = []
        current_line = ""
        for word in words:
            if len(current_line + " " + word) <= 12 or not current_line:
                current_line = (current_line + " " + word).strip()
            else:
                lines.append(current_line)
                current_line = word
        if current_line:
            lines.append(current_line)
        if len(lines) > 2:
            lines = [lines[0], lines[1][:9] + "..."]

        for j, line in enumerate(lines):
            svg += f'  <text x="{lx}" y="{ly + j * 15}" text-anchor="{anchor}" class="label">{line}</text>\n'

        svg += f'  <text x="{lx}" y="{ly + len(lines) * 15}" text-anchor="{anchor}" class="value">({count})</text>\n'

    svg += '</svg>'
    return svg


def generate_dummy_activity_data() -> dict[str, int]:
    """Generate realistic-looking dummy activity data."""
    random.seed(42)  # Reproducible randomness
    today = datetime.now(timezone.utc).date()
    data = {}

    for days_ago in range(365):
        date = today - timedelta(days=days_ago)
        date_str = date.strftime("%Y-%m-%d")

        is_weekend = date.weekday() >= 5

        if random.random() < (0.15 if is_weekend else 0.35):
            count = random.choices([1, 2, 3, 4, 5, 6, 7, 8],
                                   weights=[40, 25, 15, 10, 5, 3, 1, 1])[0]
            data[date_str] = count

    return data


# --- Tests ---

def test_radar_svg_has_correct_dimensions():
    """Radar SVG should be 400x400."""
    svg = generate_radar_svg(TOPICS_DATA)
    assert 'width="400"' in svg
    assert 'height="400"' in svg


def test_radar_svg_contains_all_labels():
    """Radar SVG should contain all top labels."""
    svg = generate_radar_svg(JOURNALS_DATA)
    for label in ["Nature", "arXiv", "Science", "PNAS"]:
        assert label in svg


def test_radar_svg_contains_counts():
    """Radar SVG should show counts in parentheses."""
    svg = generate_radar_svg(TOPICS_DATA, title_case_labels=True)
    assert "(24)" in svg  # Machine Learning count
    assert "(18)" in svg  # Deep Learning count


def test_radar_svg_returns_none_for_insufficient_data():
    """Radar needs at least 3 items."""
    result = generate_radar_svg({"a": 1, "b": 2})
    assert result is None


def test_contribution_svg_has_legend():
    """Activity SVG should have Less/More legend."""
    svg = generate_contribution_svg({"2025-01-15": 5})
    assert "Less" in svg
    assert "More" in svg


def test_contribution_svg_has_day_labels():
    """Activity SVG should have Mon/Wed/Fri labels."""
    svg = generate_contribution_svg({})
    assert "Mon" in svg
    assert "Wed" in svg
    assert "Fri" in svg


def test_dummy_activity_data_is_reproducible():
    """Same seed should produce same data."""
    data1 = generate_dummy_activity_data()
    data2 = generate_dummy_activity_data()
    assert data1 == data2


def test_dummy_activity_data_has_entries():
    """Should generate some activity entries."""
    data = generate_dummy_activity_data()
    assert len(data) > 50  # Should have reasonable activity


# --- Integration Tests (require credentials) ---

# Check for credentials
ZOTERO_API_KEY = os.environ.get("ZOTERO_API_KEY")
ZOTERO_USER_ID = os.environ.get("ZOTERO_USER_ID")
MENDELEY_CLIENT_ID = os.environ.get("MENDELEY_CLIENT_ID")
MENDELEY_CLIENT_SECRET = os.environ.get("MENDELEY_CLIENT_SECRET")
MENDELEY_REFRESH_TOKEN = os.environ.get("MENDELEY_REFRESH_TOKEN")


@pytest.mark.skipif(
    not ZOTERO_API_KEY or not ZOTERO_USER_ID,
    reason="Zotero credentials not configured (set ZOTERO_API_KEY and ZOTERO_USER_ID)"
)
def test_zotero_connectivity():
    """Verify Zotero API connection works and returns valid data."""
    from sync import get_zotero_papers, normalize_zotero_paper

    papers = get_zotero_papers()
    assert isinstance(papers, list)

    # If there are papers, verify normalization works
    if papers:
        normalized = normalize_zotero_paper(papers[0])
        assert "id" in normalized
        assert "title" in normalized
        assert "authors" in normalized
        assert "created" in normalized


@pytest.mark.skipif(
    not MENDELEY_CLIENT_ID or not MENDELEY_CLIENT_SECRET or not MENDELEY_REFRESH_TOKEN,
    reason="Mendeley credentials not configured (set MENDELEY_CLIENT_ID, MENDELEY_CLIENT_SECRET, MENDELEY_REFRESH_TOKEN)"
)
def test_mendeley_connectivity():
    """Verify Mendeley API connection works and returns valid data."""
    from sync import get_mendeley_access_token, get_mendeley_papers

    access_token = get_mendeley_access_token()
    assert access_token
    assert isinstance(access_token, str)

    papers = get_mendeley_papers(access_token)
    assert isinstance(papers, list)


# --- Fixture Generation ---

def update_fixtures():
    """Regenerate the SVG fixture files in assets/."""
    os.makedirs(ASSETS_DIR, exist_ok=True)

    # Activity graph
    daily_counts = generate_dummy_activity_data()
    activity_svg = generate_contribution_svg(daily_counts)
    with open(os.path.join(ASSETS_DIR, "activity.svg"), "w") as f:
        f.write(activity_svg)
    print(f"Updated {ASSETS_DIR}/activity.svg")

    # Topics radar
    topics_svg = generate_radar_svg(TOPICS_DATA, title_case_labels=True)
    with open(os.path.join(ASSETS_DIR, "topics.svg"), "w") as f:
        f.write(topics_svg)
    print(f"Updated {ASSETS_DIR}/topics.svg")

    # Journals radar
    journals_svg = generate_radar_svg(JOURNALS_DATA, title_case_labels=False)
    with open(os.path.join(ASSETS_DIR, "journals.svg"), "w") as f:
        f.write(journals_svg)
    print(f"Updated {ASSETS_DIR}/journals.svg")

    print("\nFixtures updated successfully!")


if __name__ == "__main__":
    if "--update-fixtures" in sys.argv:
        update_fixtures()
    else:
        print("Run with --update-fixtures to regenerate SVG assets")
        print("Or use pytest to run the tests")
