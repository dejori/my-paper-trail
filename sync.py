#!/usr/bin/env python3
import logging
import math
import os
import re
import requests
import subprocess
from datetime import datetime, timedelta, timezone
from collections import defaultdict

# Load .env file for local development (optional dependency)
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
)
log = logging.getLogger(__name__)

MAX_NUM_PAPERS = 500
ASSETS_DIR = "assets"


def get_repo_url() -> str:
    """Get the GitHub repository URL from git remote."""
    try:
        result = subprocess.run(
            ["git", "config", "--get", "remote.origin.url"],
            capture_output=True,
            text=True,
            check=True,
        )
        remote_url = result.stdout.strip()

        # Parse different git URL formats
        # SSH: git@github.com:user/repo.git
        # HTTPS: https://github.com/user/repo.git
        if remote_url.startswith("git@github.com:"):
            path = remote_url.replace("git@github.com:", "").replace(".git", "")
        elif "github.com/" in remote_url:
            path = remote_url.split("github.com/")[1].replace(".git", "")
        else:
            # Fallback to default
            return "https://github.com/dejori/paper-trail"

        return f"https://github.com/{path}"
    except (subprocess.CalledProcessError, FileNotFoundError, IndexError):
        # Fallback to default if git not available or no remote
        return "https://github.com/dejori/paper-trail"


# =============================================================================
# Mendeley API
# =============================================================================

def get_mendeley_access_token() -> str:
    """Get OAuth access token for Mendeley API."""
    response = requests.post(
        "https://api.mendeley.com/oauth/token",
        data={
            "grant_type": "refresh_token",
            "refresh_token": os.environ["MENDELEY_REFRESH_TOKEN"],
            "client_id": os.environ["MENDELEY_CLIENT_ID"],
            "client_secret": os.environ["MENDELEY_CLIENT_SECRET"],
        },
    )
    response.raise_for_status()
    return response.json()["access_token"]


def get_mendeley_papers(access_token: str) -> list[dict]:
    """Fetch papers from Mendeley API."""
    response = requests.get(
        "https://api.mendeley.com/documents",
        params={"sort": "created", "order": "desc", "limit": MAX_NUM_PAPERS},
        headers={
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/vnd.mendeley-document.1+json",
        },
    )
    response.raise_for_status()
    return response.json()


# =============================================================================
# Zotero API
# =============================================================================

def get_zotero_papers() -> list[dict]:
    """Fetch papers from Zotero API."""
    api_key = os.environ["ZOTERO_API_KEY"]
    user_id = os.environ["ZOTERO_USER_ID"]

    response = requests.get(
        f"https://api.zotero.org/users/{user_id}/items",
        params={
            "limit": MAX_NUM_PAPERS,
            "sort": "dateAdded",
            "direction": "desc",
            "itemType": "-attachment",  # Exclude attachments
        },
        headers={
            "Zotero-API-Key": api_key,
            "Zotero-API-Version": "3",
        },
    )
    response.raise_for_status()
    return response.json()


def normalize_zotero_paper(item: dict) -> dict:
    """Convert Zotero item to common paper format."""
    data = item.get("data", {})

    # Extract authors
    creators = data.get("creators", [])
    authors = []
    for creator in creators:
        if creator.get("creatorType") == "author":
            authors.append({
                "first_name": creator.get("firstName", ""),
                "last_name": creator.get("lastName", ""),
            })

    # Extract identifiers
    identifiers = {}
    if data.get("DOI"):
        identifiers["doi"] = data["DOI"]
    extra = data.get("extra", "")
    if "arXiv:" in extra:
        arxiv_id = extra.split("arXiv:")[1].split()[0].strip()
        identifiers["arxiv"] = arxiv_id

    # Extract URL
    websites = []
    if data.get("url"):
        websites.append(data["url"])

    # Map to common format
    return {
        "id": item.get("key", ""),
        "title": data.get("title", ""),
        "authors": authors,
        "year": data.get("date", "")[:4] if data.get("date") else "",
        "abstract": data.get("abstractNote", ""),
        "source": data.get("publicationTitle", "") or data.get("journalAbbreviation", ""),
        "keywords": [t.get("tag", "") for t in data.get("tags", [])],
        "created": data.get("dateAdded", ""),
        "websites": websites,
        "identifiers": identifiers,
    }


# =============================================================================
# Unified paper fetching
# =============================================================================

def get_all_papers() -> tuple[list[dict], list[str]]:
    """Fetch papers from all configured sources. Returns (papers, source_names)."""
    papers = []
    sources = []
    errors = []

    # Try Mendeley
    if os.environ.get("MENDELEY_CLIENT_ID"):
        try:
            access_token = get_mendeley_access_token()
            mendeley_papers = get_mendeley_papers(access_token)
            papers.extend(mendeley_papers)
            sources.append("Mendeley")
            log.info(f"Fetched {len(mendeley_papers)} papers from Mendeley")
        except Exception as e:
            errors.append(f"Mendeley: {e}")

    # Try Zotero
    if os.environ.get("ZOTERO_API_KEY"):
        try:
            zotero_items = get_zotero_papers()
            zotero_papers = [normalize_zotero_paper(item) for item in zotero_items]
            papers.extend(zotero_papers)
            sources.append("Zotero")
            log.info(f"Fetched {len(zotero_papers)} papers from Zotero")
        except Exception as e:
            errors.append(f"Zotero: {e}")

    # Fail if any configured source failed
    if errors:
        raise RuntimeError(f"Failed to fetch from configured sources: {'; '.join(errors)}")

    # Sort all papers by created date (descending)
    papers.sort(key=lambda p: p.get("created", ""), reverse=True)

    return papers, sources


def build_daily_counts(papers: list[dict]) -> dict[str, int]:
    """Build a dict of date -> paper count."""
    counts = defaultdict(int)
    for paper in papers:
        created = paper.get("created", "")
        if created:
            # Just get the date part (YYYY-MM-DD)
            date_str = created[:10]
            counts[date_str] += 1
    return counts


def generate_contribution_svg(papers: list[dict]) -> tuple[str, int]:
    """Generate a GitHub-style contribution graph SVG. Returns (svg, total_count)."""
    # GitHub colors (5 levels: 0, 1-25%, 26-50%, 51-75%, 76-100%)
    colors = ["#ebedf0", "#9be9a7", "#40c463", "#30a14e", "#216e39"]

    daily_counts = build_daily_counts(papers)

    # Get the date range: last 52 weeks ending today
    today = datetime.now(timezone.utc).date()
    # Find the last Sunday (or today if it's Sunday)
    days_since_sunday = today.weekday() + 1 if today.weekday() != 6 else 0
    end_date = today - timedelta(days=days_since_sunday - 6)  # End on Saturday
    start_date = end_date - timedelta(days=52*7 - 1)  # 52 weeks back

    # Adjust start to the nearest Sunday
    start_date = start_date - timedelta(days=(start_date.weekday() + 1) % 7)

    # Count papers in the last year (within the date range)
    total_papers_last_year = sum(
        count for date_str, count in daily_counts.items()
        if start_date <= datetime.strptime(date_str, "%Y-%m-%d").date() <= today
    )

    # Calculate max for scaling
    max_count = max(daily_counts.values()) if daily_counts else 1

    # SVG dimensions
    cell_size = 11
    cell_gap = 3
    total_cell = cell_size + cell_gap
    weeks = 53
    days = 7
    left_padding = 36  # Space for day labels
    top_padding = 18   # Space for month labels
    legend_height = 20 # Space for legend at bottom
    outer_padding = 16 # Padding around entire chart

    # Calculate month label positions - only show if there's enough space from previous
    month_labels = []
    current_month = None
    last_label_week = -4  # Ensure first label shows
    for week in range(weeks):
        week_start = start_date + timedelta(days=week * 7)
        if week_start.month != current_month:
            current_month = week_start.month
            # Only add label if at least 3 weeks from last label
            if week - last_label_week >= 3:
                month_labels.append((week, week_start.strftime("%b")))
                last_label_week = week

    # SVG dimensions
    svg_width = weeks * total_cell + left_padding + 10 + outer_padding * 2
    svg_height = days * total_cell + top_padding + legend_height + outer_padding * 2

    svg = f'''<svg width="{svg_width}" height="{svg_height}" xmlns="http://www.w3.org/2000/svg">
  <rect width="{svg_width}" height="{svg_height}" fill="white"/>
  <style>
    text {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif; font-size: 9px; fill: #57606a; }}
    .legend {{ font-size: 9px; }}
  </style>
'''

    # Month labels
    for week, label in month_labels:
        x = outer_padding + left_padding + week * total_cell
        svg += f'  <text x="{x}" y="{outer_padding + 10}">{label}</text>\n'

    # Day labels (Mon, Wed, Fri) - align to center of cell row
    day_labels = [(1, "Mon"), (3, "Wed"), (5, "Fri")]
    for day_idx, label in day_labels:
        y = outer_padding + top_padding + day_idx * total_cell + (cell_size / 2) + 3
        svg += f'  <text x="{outer_padding}" y="{y}">{label}</text>\n'

    # Contribution squares
    for week in range(weeks):
        for day in range(days):
            date = start_date + timedelta(days=week * 7 + day)
            if date > today:
                continue

            date_str = date.strftime("%Y-%m-%d")
            count = daily_counts.get(date_str, 0)

            # Determine color level
            if count == 0:
                level = 0
            elif max_count == 1:
                level = 4 if count > 0 else 0
            else:
                # Scale to 1-4
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

    # Legend at bottom right
    legend_y = outer_padding + top_padding + days * total_cell + 8
    legend_text_y = legend_y + cell_size - 1  # Baseline positioning for vertical centering
    box_gap = 4  # Gap between boxes
    text_gap = 5  # Symmetrical gap between text and boxes
    boxes_width = 5 * cell_size + 4 * box_gap  # Total width of 5 boxes with gaps
    boxes_x = svg_width - outer_padding - 30 - text_gap - boxes_width  # 30 = approx "More" width
    less_x = boxes_x - text_gap  # Position "Less" so its right edge is text_gap from first box
    svg += f'  <text x="{less_x}" y="{legend_text_y}" text-anchor="end" class="legend">Less</text>\n'
    for i, color in enumerate(colors):
        svg += f'  <rect x="{boxes_x + i * (cell_size + box_gap)}" y="{legend_y}" width="{cell_size}" height="{cell_size}" rx="2" ry="2" fill="{color}"/>\n'
    more_x = boxes_x + boxes_width + text_gap
    svg += f'  <text x="{more_x}" y="{legend_text_y}" class="legend">More</text>\n'

    svg += '</svg>'
    return svg, total_papers_last_year


def get_paper_url(paper: dict) -> str | None:
    """Get best URL for paper: website > DOI > arXiv."""
    websites = paper.get("websites", [])
    if websites:
        return websites[0]

    identifiers = paper.get("identifiers", {})
    if identifiers.get("doi"):
        return f"https://doi.org/{identifiers['doi']}"
    if identifiers.get("arxiv"):
        return f"https://arxiv.org/abs/{identifiers['arxiv']}"

    return None


def get_abstract_snippet(abstract: str, max_chars: int = 200) -> str | None:
    """Get first sentence or truncated abstract."""
    if not abstract:
        return None

    # Try to get first sentence
    for end in [". ", ".\n", ".\t"]:
        if end in abstract:
            first_sentence = abstract.split(end)[0] + "."
            if len(first_sentence) <= max_chars:
                return first_sentence
            break

    # Truncate if too long
    if len(abstract) <= max_chars:
        return abstract
    return abstract[:max_chars].rsplit(" ", 1)[0] + "..."


def format_paper(paper: dict) -> str | None:
    """Format a paper as a markdown list item with abstract snippet."""
    title = paper.get("title", "")
    if not title:
        return None

    authors = paper.get("authors", [])
    author_str = ", ".join(a.get("last_name", "") for a in authors) if authors else ""
    year = paper.get("year", "")
    url = get_paper_url(paper)
    abstract = paper.get("abstract", "")

    if url:
        entry = f"- [{title}]({url})"
    else:
        entry = f"- {title}"

    if author_str:
        entry += f" — {author_str}"
    if year:
        entry += f" ({year})"

    # Add abstract snippet as indented text
    snippet = get_abstract_snippet(abstract)
    if snippet:
        entry += f"\n  > *{snippet}*"

    return entry


def is_arxiv_category(keyword:str) -> bool:
    """Check if keyword is an arXiv category like cs.CL, stat.ML, etc."""
    prefixes = ('cs.', 'stat.', 'math.', 'physics.', 'q-bio.', 'q-fin.', 'eess.', 'astro-ph.', 'cond-mat.', 'hep-', 'nucl-', 'gr-qc', 'quant-ph', 'nlin.')
    return keyword.lower().startswith(prefixes)


def is_noise_keyword(kw: str) -> bool:
    """Check if keyword is noise (emails, ACM categories, etc.)."""
    if "@" in kw:
        return True
    if kw.startswith("•"):
        return True
    if ":" in kw:
        return True
    return False


def stem_keyword(kw:str) -> str:
    """Simple stemming: remove common suffixes to normalize plurals/variants."""
    # Handle common plural/singular variations
    if kw.endswith("ies"):
        return kw[:-3] + "y"  # studies -> study
    if kw.endswith("es") and not kw.endswith("ses"):
        return kw[:-2]  # diseases -> diseas (not perfect but groups them)
    if kw.endswith("s") and not kw.endswith("ss") and len(kw) > 3:
        return kw[:-1]  # networks -> network
    return kw


def build_keyword_counts(papers: list[dict]) -> dict[str, int]:
    """Count keyword frequency across all papers, normalizing case and stemming."""
    counts = defaultdict(int)
    stem_to_display = {}  # Track best display form for each stem

    for paper in papers:
        keywords = paper.get("keywords", [])
        for kw in keywords:
            # Normalize: lowercase, strip whitespace
            normalized = kw.strip().lower()
            # Skip arXiv categories and noise
            if normalized and not is_arxiv_category(normalized) and not is_noise_keyword(normalized):
                stemmed = stem_keyword(normalized)
                counts[stemmed] += 1
                # Keep the longer form for display (e.g., "networks" over "network")
                if stemmed not in stem_to_display or len(normalized) > len(stem_to_display[stemmed]):
                    stem_to_display[stemmed] = normalized

    # Return counts with display forms
    return {stem_to_display[stem]: count for stem, count in counts.items()}


def normalize_journal(name: str) -> str | None:
    """Normalize journal names to merge duplicates."""
    if not name:
        return None
    # Lowercase for comparison
    lower = name.lower().strip()
    # Remove common suffixes/variations
    if " : jamia" in lower:
        return "Journal of the American Medical Informatics Association"
    return name


def infer_source_from_url(paper: dict) -> str | None:
    """Infer journal/source from URL or identifiers if source is missing."""
    # Check identifiers first
    identifiers = paper.get("identifiers", {})
    if identifiers.get("arxiv"):
        return "arXiv"

    # Check URLs
    urls = paper.get("websites", [])
    url = urls[0].lower() if urls else ""

    if not url:
        doi = identifiers.get("doi", "")
        if doi:
            url = f"https://doi.org/{doi}".lower()

    if "arxiv.org" in url:
        return "arXiv"
    if "biorxiv.org" in url:
        return "bioRxiv"
    if "medrxiv.org" in url:
        return "medRxiv"
    if "nature.com" in url:
        return "Nature"
    if "sciencedirect.com" in url or "elsevier.com" in url:
        return "Elsevier"
    if "springer.com" in url or "springerlink.com" in url:
        return "Springer"
    if "wiley.com" in url:
        return "Wiley"
    if "plos.org" in url or "plosone.org" in url:
        return "PLOS"
    if "acm.org" in url:
        return "ACM"
    if "ieee.org" in url:
        return "IEEE"

    return None


def build_journal_counts(papers: list[dict]) -> dict[str, int]:
    """Count papers by journal/source."""
    counts = defaultdict(int)
    name_to_display = {}

    for paper in papers:
        source = paper.get("source", "")
        # If no source, try to infer from URL
        if not source:
            source = infer_source_from_url(paper)
        if not source:
            continue
        normalized = normalize_journal(source)
        if not normalized:
            continue
        # Use lowercase as key for grouping
        key = normalized.lower()
        counts[key] += 1
        # Keep the longest form for display
        if key not in name_to_display or len(normalized) > len(name_to_display[key]):
            name_to_display[key] = normalized

    return {name_to_display[k]: v for k, v in counts.items()}


def generate_radar_svg(data: dict[str, int], top_n: int = 8, title_case_labels: bool = False) -> str | None:
    """Generate a spider/radar chart SVG from label->count data."""
    if not data:
        return None

    # Sort by count and take top N
    sorted_data = sorted(data.items(), key=lambda x: (-x[1], x[0]))
    top_items = sorted_data[:top_n]

    if len(top_items) < 3:
        return None

    # Chart dimensions
    width = 400
    height = 400
    cx, cy = width // 2, height // 2
    max_radius = 90
    label_radius = max_radius + 35

    n = len(top_items)
    max_count = top_items[0][1]

    # Calculate angles for each axis (starting from top, going clockwise)
    angles = [(i * 2 * math.pi / n) - (math.pi / 2) for i in range(n)]

    svg = f'''<svg width="{width}" height="{height}" xmlns="http://www.w3.org/2000/svg">
  <rect width="{width}" height="{height}" fill="white"/>
  <style>
    text {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif; font-size: 11px; fill: #57606a; }}
    .label {{ font-size: 10px; }}
    .value {{ font-size: 9px; fill: #8b949e; }}
  </style>
'''

    # Draw concentric rings (background grid)
    rings = 4
    for i in range(1, rings + 1):
        r = (max_radius * i) // rings
        svg += f'  <circle cx="{cx}" cy="{cy}" r="{r}" fill="none" stroke="#d0d7de" stroke-width="1"/>\n'

    # Draw axis lines
    for angle in angles:
        x2 = cx + max_radius * math.cos(angle)
        y2 = cy + max_radius * math.sin(angle)
        svg += f'  <line x1="{cx}" y1="{cy}" x2="{x2}" y2="{y2}" stroke="#d0d7de" stroke-width="1"/>\n'

    # Calculate data points
    points = []
    for i, (label, count) in enumerate(top_items):
        # Scale count to radius (minimum 20% so small values are visible)
        ratio = 0.2 + 0.8 * (count / max_count) if max_count > 0 else 0.2
        r = max_radius * ratio
        x = cx + r * math.cos(angles[i])
        y = cy + r * math.sin(angles[i])
        points.append((x, y))

    # Draw filled polygon
    points_str = " ".join(f"{x},{y}" for x, y in points)
    svg += f'  <polygon points="{points_str}" fill="#9be9a7" fill-opacity="0.5" stroke="#40c463" stroke-width="2"/>\n'

    # Draw data points
    for x, y in points:
        svg += f'  <circle cx="{x}" cy="{y}" r="4" fill="#40c463"/>\n'

    # Draw labels with line breaks for long text
    for i, (label, count) in enumerate(top_items):
        angle = angles[i]
        lx = cx + label_radius * math.cos(angle)
        ly = cy + label_radius * math.sin(angle)

        # Adjust text anchor based on position
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

        # Truncate and split long labels into multiple lines
        display = label.title() if title_case_labels else label
        # Truncate very long labels
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
        # Limit to 2 lines max
        if len(lines) > 2:
            lines = [lines[0], lines[1][:9] + "..."]

        # Render each line
        for j, line in enumerate(lines):
            svg += f'  <text x="{lx}" y="{ly + j * 15}" text-anchor="{anchor}" class="label">{line}</text>\n'

        # Add count after last line
        svg += f'  <text x="{lx}" y="{ly + len(lines) * 15}" text-anchor="{anchor}" class="value">({count})</text>\n'

    svg += '</svg>'
    return svg


def generate_journals_svg(journal_counts: dict[str, int], top_n: int = 8) -> str | None:
    """Generate a spider/radar chart SVG for journals."""
    return generate_radar_svg(journal_counts, top_n, title_case_labels=False)


def generate_topics_svg(keyword_counts: dict[str, int], top_n: int = 8) -> str | None:
    """Generate a spider/radar chart SVG for topics."""
    return generate_radar_svg(keyword_counts, top_n, title_case_labels=True)


def generate_combined_svg(
    activity_svg: str,
    topics_svg: str | None,
    journals_svg: str | None,
    papers_last_year: int,
    repo_url: str = "https://github.com/dejori/paper-trail",
) -> str:
    """Generate a combined SVG with all charts and attribution footer."""
    # Parse activity SVG dimensions
    activity_match = re.search(r'width="(\d+)" height="(\d+)"', activity_svg)
    activity_width = int(activity_match.group(1)) if activity_match else 800
    activity_height = int(activity_match.group(2)) if activity_match else 150

    # Radar chart dimensions (from generate_radar_svg)
    radar_width = 400
    radar_height = 400

    # Layout
    padding = 20
    gap = 60  # Space between charts to prevent label overlap
    footer_height = 30

    # Calculate total dimensions
    has_topics = topics_svg is not None
    has_journals = journals_svg is not None

    if has_topics and has_journals:
        radar_section_width = radar_width * 2 + gap
    elif has_topics or has_journals:
        radar_section_width = radar_width
    else:
        radar_section_width = 0

    total_width = max(activity_width, radar_section_width) + padding * 2
    radar_section_height = radar_height if (has_topics or has_journals) else 0
    total_height = activity_height + radar_section_height + footer_height + padding * 2 + (gap if radar_section_height else 0)

    # Center the activity graph
    activity_x = (total_width - activity_width) // 2

    svg = f'''<svg width="{total_width}" height="{total_height}" xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink">
  <rect width="{total_width}" height="{total_height}" fill="white"/>
  <style>
    text {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif; }}
    .footer {{ font-size: 11px; fill: #8b949e; }}
    .footer-link {{ font-size: 11px; fill: #0969da; }}
  </style>
'''

    # Extract inner content from activity SVG (skip the outer svg tags and background rect)
    activity_inner = re.sub(r'^<svg[^>]*>\s*<rect[^/]*/>\s*<style>.*?</style>\s*', '', activity_svg, flags=re.DOTALL)
    activity_inner = re.sub(r'</svg>\s*$', '', activity_inner)

    # Embed activity graph
    svg += f'  <g transform="translate({activity_x}, {padding})">\n'
    svg += activity_inner
    svg += '  </g>\n'

    # Embed radar charts side by side
    if has_topics or has_journals:
        radar_y = padding + activity_height + gap

        if has_topics and has_journals:
            # Both charts - center them
            radar_start_x = (total_width - radar_section_width) // 2

            # Topics on left
            topics_inner = re.sub(r'^<svg[^>]*>\s*<rect[^/]*/>\s*<style>.*?</style>\s*', '', topics_svg, flags=re.DOTALL)
            topics_inner = re.sub(r'</svg>\s*$', '', topics_inner)
            svg += f'  <g transform="translate({radar_start_x}, {radar_y})">\n'
            svg += topics_inner
            svg += '  </g>\n'

            # Journals on right
            journals_inner = re.sub(r'^<svg[^>]*>\s*<rect[^/]*/>\s*<style>.*?</style>\s*', '', journals_svg, flags=re.DOTALL)
            journals_inner = re.sub(r'</svg>\s*$', '', journals_inner)
            svg += f'  <g transform="translate({radar_start_x + radar_width + gap}, {radar_y})">\n'
            svg += journals_inner
            svg += '  </g>\n'
        else:
            # Single chart - center it
            single_svg = topics_svg if has_topics else journals_svg
            single_inner = re.sub(r'^<svg[^>]*>\s*<rect[^/]*/>\s*<style>.*?</style>\s*', '', single_svg, flags=re.DOTALL)
            single_inner = re.sub(r'</svg>\s*$', '', single_inner)
            radar_x = (total_width - radar_width) // 2
            svg += f'  <g transform="translate({radar_x}, {radar_y})">\n'
            svg += single_inner
            svg += '  </g>\n'

    # Footer with attribution (right-aligned)
    footer_y = total_height - padding
    footer_x = total_width - padding
    svg += f'  <text x="{footer_x}" y="{footer_y}" text-anchor="end" class="footer">'
    svg += f'{papers_last_year} papers · '
    svg += f'<a xlink:href="{repo_url}" target="_blank"><tspan class="footer-link">paper-trail</tspan></a>'
    svg += '</text>\n'

    svg += '</svg>'
    return svg


def main() -> None:
    # Get repository URL for badges and attribution
    repo_url = get_repo_url()

    papers, sources = get_all_papers()

    if not papers:
        log.warning("No papers found. Check your API credentials.")
        return

    log.info(f"Found {len(papers)} papers total")

    # Build keyword counts for topics section
    keyword_counts = build_keyword_counts(papers)
    log.info(f"Found {len(keyword_counts)} unique keywords")

    # Build journal counts
    journal_counts = build_journal_counts(papers)
    log.info(f"Found {len(journal_counts)} unique journals")

    # Debug: show all journals
    log.debug("All journals:")
    for j, c in sorted(journal_counts.items(), key=lambda x: -x[1]):
        log.debug(f"  {c:3}  {j}")


    # Ensure assets directory exists
    os.makedirs(ASSETS_DIR, exist_ok=True)

    # Generate contribution graph SVG
    svg_content, papers_last_year = generate_contribution_svg(papers)
    with open(f"{ASSETS_DIR}/activity.svg", "w") as f:
        f.write(svg_content)
    log.info(f"Generated {ASSETS_DIR}/activity.svg ({papers_last_year} papers in last year)")

    # Generate topics spider chart SVG
    topics_svg = generate_topics_svg(keyword_counts)
    if topics_svg:
        with open(f"{ASSETS_DIR}/topics.svg", "w") as f:
            f.write(topics_svg)
        log.info(f"Generated {ASSETS_DIR}/topics.svg")

    # Generate journals spider chart SVG
    journals_svg = generate_journals_svg(journal_counts)
    if journals_svg:
        with open(f"{ASSETS_DIR}/journals.svg", "w") as f:
            f.write(journals_svg)
        log.info(f"Generated {ASSETS_DIR}/journals.svg")

    # Generate combined SVG with all charts and attribution
    combined_svg = generate_combined_svg(
        svg_content, topics_svg, journals_svg, papers_last_year, repo_url
    )
    with open(f"{ASSETS_DIR}/paper-trail.svg", "w") as f:
        f.write(combined_svg)
    log.info(f"Generated {ASSETS_DIR}/paper-trail.svg")

    # Build markdown with contribution graph
    source_links = {
        "Mendeley": "[Mendeley](https://www.mendeley.com/)",
        "Zotero": "[Zotero](https://www.zotero.org/)",
    }
    source_str = " and ".join(source_links.get(s, s) for s in sources)

    lines = [
        "# Reading List",
        "",
        f"![Tests]({repo_url}/actions/workflows/test.yml/badge.svg)",
        f"![Sync]({repo_url}/actions/workflows/sync.yml/badge.svg)",
        "",
        f"Papers I'm reading, synced from my {source_str} library.",
        "",
        f"{papers_last_year} papers read in the last year",
        "",
        f"![Reading Activity]({ASSETS_DIR}/activity.svg)",
        "",
        f"![Topics]({ASSETS_DIR}/topics.svg)",
        f"![Journals]({ASSETS_DIR}/journals.svg)",
        "",
    ]

    # Track which years we've seen to add anchors
    years_seen = set()

    # Group papers by month
    current_month = None
    for paper in papers:
        created = paper.get("created", "")
        if created:
            try:
                dt = datetime.fromisoformat(created.replace("Z", "+00:00"))
                month_year = dt.strftime("%B %Y")
                year = dt.year
            except ValueError:
                month_year = None
                year = None
        else:
            month_year = None
            year = None

        if month_year and month_year != current_month:
            if current_month:
                lines.append("")
            # Add anchor for first month of each year
            if year and year not in years_seen:
                lines.append(f'<a id="{year}"></a>')
                lines.append("")
                years_seen.add(year)
            lines.append(f"## {month_year}")
            lines.append("")
            current_month = month_year

        doc_id = paper.get("id")
        entry = format_paper(paper)
        if entry:
            lines.append(entry)

    # Footer
    lines.extend([
        "",
        "---",
        "",
        f"*Last synced: {datetime.now(timezone.utc).strftime('%Y-%m-%d')}*",
    ])

    with open("README.md", "w") as f:
        f.write("\n".join(lines) + "\n")

    log.info("Generated README.md")


if __name__ == "__main__":
    main()
