def format_color(color: str) -> str:
    c = color.strip()
    if all(ch in "0123456789abcdefABCDEF" for ch in c) and len(c) in (3, 4, 6, 8):
        return f"#{c}"
    return c

def estimate_text_width(text: str, is_caps: bool = False) -> int:
    multiplier = 10.5 if is_caps else 7.5
    padding = 20 if is_caps else 14
    return int(len(text) * multiplier + padding)

def render_logo_svg(path_d: str, logo_color: str = "fff", x_pos: int = 6, y_offset: int = 3, size: int = 14) -> str:
    if not path_d:
        return ""
    fill = format_color(logo_color)
    return (
        f'<svg x="{x_pos}" y="{y_offset}" width="{size}" height="{size}" viewBox="0 0 24 24">'
        f'<path fill="{fill}" d="{path_d}"/></svg>'
    )

def build_badge_svg(
    label: str,
    count: int,
    color: str = "4c1",
    label_color: str = "555",
    style: str = "flat",
    icon_path_d: str | None = None,
    logo_color: str = "fff",
    link_url: str | None = None,
) -> str:
    count_str = str(count)
    style_norm = style.lower().replace("_", "-")
    bg_color = format_color(color)
    lbl_color = format_color(label_color)
    has_logo = bool(icon_path_d)

    # 1. FOR-THE-BADGE (28px height)
    if style_norm in ("for-the-badge", "forthebadge"):
        label_up = label.upper()
        count_up = count_str.upper()
        logo_offset = 24 if has_logo else 0
        lw = estimate_text_width(label_up, is_caps=True) + logo_offset
        cw = estimate_text_width(count_up, is_caps=True)
        tw = lw + cw
        lx = (lw + logo_offset) / 2
        cx = lw + (cw / 2)
        logo_svg = render_logo_svg(icon_path_d, logo_color, x_pos=8, y_offset=7, size=14) if has_logo else ""

        body = f"""  <mask id="a"><rect width="{tw}" height="28" rx="3" fill="#fff"/></mask>
<g mask="url(#a)">
  <rect width="{lw}" height="28" fill="{lbl_color}"/>
  <rect x="{lw}" width="{cw}" height="28" fill="{bg_color}"/>
  {logo_svg}
</g>
<g fill="#fff" text-anchor="middle" font-family="Verdana,Geneva,DejaVu Sans,sans-serif" font-size="10" font-weight="bold" letter-spacing="1">
  <text x="{lx}" y="17.5">{label_up}</text>
  <text x="{cx}" y="17.5">{count_up}</text>
</g>"""

    # 20px Standard Badges
    logo_offset = 18 if has_logo else 0
    lw = estimate_text_width(label) + logo_offset
    cw = estimate_text_width(count_str)
    tw = lw + cw
    lx = (lw + logo_offset) / 2
    cx = lw + (cw / 2)
    logo_svg = render_logo_svg(icon_path_d, logo_color, x_pos=6, y_offset=3, size=14) if has_logo else ""

    # 2. SOCIAL
    if style_norm == "social":
        cw_soc = cw + 6
        tw_soc = lw + cw_soc + 4
        body = f"""  <rect width="{lw}" height="20" rx="3" fill="{lbl_color}" stroke="#d5d5d5"/>
{logo_svg}
<text x="{lx}" y="14" fill="#333" font-family="Helvetica Neue,Helvetica,Arial,sans-serif" font-size="11" font-weight="bold" text-anchor="middle">{label}</text>
<g transform="translate({lw + 4}, 0)">
  <path d="M0 10 L4 6 L4 14 Z" fill="{bg_color}"/>
  <rect x="4" width="{cw_soc - 4}" height="20" rx="3" fill="{bg_color}" stroke="#d5d5d5"/>
  <text x="{(cw_soc + 4)/2}" y="14" fill="#333" font-family="Helvetica Neue,Helvetica,Arial,sans-serif" font-size="11" font-weight="bold" text-anchor="middle">{count_str}</text>
</g>"""

    # 3. PLASTIC
    if style_norm == "plastic":
        body = f"""  <linearGradient id="p" x2="0" y2="100%">
  <stop offset="0" stop-color="#fff" stop-opacity=".7"/>
  <stop offset=".1" stop-color="#aaa" stop-opacity=".1"/>
  <stop offset=".9" stop-color="#000" stop-opacity=".3"/>
  <stop offset="1" stop-color="#000" stop-opacity=".5"/>
</linearGradient>
<mask id="a"><rect width="{tw}" height="20" rx="4" fill="#fff"/></mask>
<g mask="url(#a)">
  <rect width="{lw}" height="20" fill="{lbl_color}"/>
  <rect x="{lw}" width="{cw}" height="20" fill="{bg_color}"/>
  {logo_svg}
  <rect width="{tw}" height="20" fill="url(#p)"/>
</g>
<g fill="#fff" text-anchor="middle" font-family="DejaVu Sans,Verdana,Geneva,sans-serif" font-size="11">
  <text x="{lx}" y="15" fill="#010101" fill-opacity=".3">{label}</text>
  <text x="{lx}" y="14">{label}</text>
  <text x="{cx}" y="15" fill="#010101" fill-opacity=".3">{count_str}</text>
  <text x="{cx}" y="14">{count_str}</text>
</g>"""

    # 4. FLAT-SQUARE
    if style_norm in ("flat-square", "square"):
        body = f"""  <g>
  <rect width="{lw}" height="20" fill="{lbl_color}"/>
  <rect x="{lw}" width="{cw}" height="20" fill="{bg_color}"/>
  {logo_svg}
</g>
<g fill="#fff" text-anchor="middle" font-family="DejaVu Sans,Verdana,Geneva,sans-serif" font-size="11">
  <text x="{lx}" y="15" fill="#010101" fill-opacity=".3">{label}</text>
  <text x="{lx}" y="14">{label}</text>
  <text x="{cx}" y="15" fill="#010101" fill-opacity=".3">{count_str}</text>
  <text x="{cx}" y="14">{count_str}</text>
</g>"""

    # 5. FLAT (Default)
    body = f"""  <linearGradient id="b" x2="0" y2="100%"><stop offset="0" stop-color="#bbb" stop-opacity=".1"/><stop offset="1" stop-opacity=".1"/></linearGradient>
<mask id="a"><rect width="{tw}" height="20" rx="3" fill="#fff"/></mask>
<g mask="url(#a)">
  <rect width="{lw}" height="20" fill="{lbl_color}"/>
  <rect x="{lw}" width="{cw}" height="20" fill="{bg_color}"/>
  {logo_svg}
  <rect width="{tw}" height="20" fill="url(#b)"/>
</g>
<g fill="#fff" text-anchor="middle" font-family="DejaVu Sans,Verdana,Geneva,sans-serif" font-size="11">
  <text x="{lx}" y="15" fill="#010101" fill-opacity=".3">{label}</text>
  <text x="{lx}" y="14">{label}</text>
  <text x="{cx}" y="15" fill="#010101" fill-opacity=".3">{count_str}</text>
  <text x="{cx}" y="14">{count_str}</text>
</g>"""

    height = 28 if style_norm in ("for-the-badge", "forthebadge") else 20

    if link_url:
      body = f'<a href="{link_url}" target="_blank">\n{body}\n</a>'

    return f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" width="{tw}" height="{height}">\n{body}\n</svg>'
