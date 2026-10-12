#!/usr/bin/env python3
"""Generate the dependency-free SVG used to explain the Week 3 results."""

from pathlib import Path


ROWS = [
    ("Crew", 53.33, 46.41, 11.87),
    ("Mission control", 46.13, 53.33, 15.77),
    ("Recovery", 0.13, 0.06, 6.00),
    ("Remote site", 0.42, 0.20, 6.66),
]
COLORS = {"utterances": "#2563eb", "words": "#f97316", "average": "#16a34a"}


def chart(output: Path):
    parts = [
        '<svg xmlns="http://www.w3.org/2000/svg" width="1000" height="500" viewBox="0 0 1000 500">',
        '<rect width="1000" height="500" fill="white"/>',
        '<style>text{font-family:Arial,sans-serif;fill:#172033}.title{font-size:22px;font-weight:700}.axis{font-size:13px}.label{font-size:14px}.value{font-size:12px;font-weight:700}</style>',
        '<text x="40" y="35" class="title">Apollo 11 speaking patterns by category</text>',
        '<text x="40" y="65" class="axis">Share of matched utterances and words</text>',
        '<text x="560" y="65" class="axis">Average words per utterance</text>',
        f'<rect x="40" y="78" width="12" height="12" fill="{COLORS["utterances"]}"/><text x="58" y="89" class="axis">Utterances</text>',
        f'<rect x="145" y="78" width="12" height="12" fill="{COLORS["words"]}"/><text x="163" y="89" class="axis">Words</text>',
    ]
    for index, (name, utterances, words, average) in enumerate(ROWS):
        y = 125 + index * 88
        parts.append(f'<text x="40" y="{y + 18}" class="label">{name}</text>')
        u_width = utterances * 7
        w_width = words * 7
        parts.append(f'<rect x="165" y="{y}" width="{u_width:.1f}" height="18" rx="2" fill="{COLORS["utterances"]}"/>')
        parts.append(f'<rect x="165" y="{y + 24}" width="{w_width:.1f}" height="18" rx="2" fill="{COLORS["words"]}"/>')
        parts.append(f'<text x="{170 + max(u_width, 2):.1f}" y="{y + 14}" class="value">{utterances:.2f}%</text>')
        parts.append(f'<text x="{170 + max(w_width, 2):.1f}" y="{y + 38}" class="value">{words:.2f}%</text>')
        avg_width = average * 20
        parts.append(f'<rect x="560" y="{y + 9}" width="{avg_width:.1f}" height="25" rx="3" fill="{COLORS["average"]}"/>')
        parts.append(f'<text x="{568 + avg_width:.1f}" y="{y + 27}" class="value">{average:.2f}</text>')
    parts.extend(
        [
            '<line x1="165" y1="105" x2="165" y2="460" stroke="#94a3b8"/>',
            '<line x1="560" y1="105" x2="560" y2="460" stroke="#94a3b8"/>',
            '<text x="40" y="482" class="axis">Source: 8,420 matched transcript utterances; descriptive, not causal.</text>',
            '</svg>',
        ]
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(parts) + "\n", encoding="utf-8")


if __name__ == "__main__":
    chart(Path(__file__).resolve().parents[1] / "docs" / "speaker-results.svg")
