# src/harmoniq/image_utils.py
import logging
from PIL import Image, ImageDraw, ImageFont, ImageOps # ImageOps might not be needed yet
import os # Ensure os is imported if you use it for path joining here, though config usually handles paths
from . import config

logger = logging.getLogger(__name__)

# (_get_font and _wrap_text helper functions remain the same as your working version)
def _get_font(font_path, size):
    try: return ImageFont.truetype(font_path, size)
    except IOError:
        logger.warning(f"Font not found at '{font_path}'. Attempting default."); return ImageFont.load_default()

def _wrap_text(text: str, font: ImageFont.FreeTypeFont, drawer: ImageDraw.ImageDraw, max_width: int) -> list[str]:
    """Wraps text to fit within a maximum width, using the drawer for textbbox."""
    lines = []
    if not text or not font: return lines
    
    words = text.split()
    current_line = ""
    for word in words:
        test_line = f"{current_line} {word}".strip()
        try:
            # Use the passed drawer object to get textbbox
            bbox = drawer.textbbox((0,0), test_line, font=font) 
            line_width = bbox[2] - bbox[0]
        except AttributeError: # Fallback for older Pillow or basic font if drawer.textbbox not present
            line_width = drawer.textsize(test_line, font=font)[0]

        if line_width <= max_width:
            current_line = test_line
        else:
            if current_line: 
                lines.append(current_line)
            current_line = word
    if current_line:
        lines.append(current_line)
    return lines

def generate_playlist_cover(playlist_title: str, 
                            period_name: str | None = None,
                            active_moods: list[str] | None = None, 
                            active_styles: list[str] | None = None) -> str | None:
    if not config.ENABLE_PLAYLIST_COVERS:
        logger.debug("Playlist cover generation is disabled."); return None

    logger.info(f"Generating improved playlist cover for '{playlist_title}' (Period: {period_name})")
    width, height = 600, 600
    default_colors = config.COVER_PERIOD_COLORS.get("DefaultVibe", ((100,100,100), (150,150,150)))
    period_name_for_color = period_name if period_name else "DefaultVibe"
    colors = config.COVER_PERIOD_COLORS.get(period_name_for_color, default_colors)
    
    try:
        img = Image.new("RGB", (width, height))
        draw = ImageDraw.Draw(img) # Create the ImageDraw object
        color1_rgb, color2_rgb = colors[0], colors[1]
        for y_grad in range(height):
            r = int(color1_rgb[0] + (color2_rgb[0] - color1_rgb[0]) * y_grad / height)
            g = int(color1_rgb[1] + (color2_rgb[1] - color1_rgb[1]) * y_grad / height)
            b = int(color1_rgb[2] + (color2_rgb[2] - color1_rgb[2]) * y_grad / height)
            draw.line([(0, y_grad), (width, y_grad)], fill=(r, g, b))

        margin = 45 
        text_width_max = width - (2 * margin)
        text_color_main = (255, 255, 255, 240) 
        text_color_secondary = (230, 230, 230, 200)
        shadow_color = (0, 0, 0, 80) 

        font_brand = _get_font(config.COVER_FONT_FILE_PATH, 28)
        brand_text = "HARMONIQ"
        if font_brand:
            try: brand_bbox = draw.textbbox((margin, margin), brand_text, font=font_brand)
            except AttributeError: brand_bbox = (margin, margin, margin + font_brand.getsize(brand_text)[0], margin + font_brand.getsize(brand_text)[1])
            draw.text((brand_bbox[0] + 2, brand_bbox[1] + 2), brand_text, font=font_brand, fill=shadow_color)
            draw.text((brand_bbox[0], brand_bbox[1]), brand_text, font=font_brand, fill=text_color_secondary)

        display_period_name = period_name.replace("EarlyMorning", "Early Morning").replace("LateNight", "Late Night") if period_name else "Vibes"
        font_period = _get_font(config.COVER_FONT_FILE_PATH, 100) 
        if font_period:
            # --- CORRECTED CALL TO _wrap_text ---
            period_lines = _wrap_text(display_period_name.upper(), font_period, draw, text_width_max)
            
            line_height_period_approx = font_period.getbbox("A")[3] - font_period.getbbox("A")[1] if hasattr(font_period, 'getbbox') else font_period.getsize("A")[1]
            total_period_height = len(period_lines) * line_height_period_approx + (len(period_lines) - 1) * 15 
            current_y_period = (height - total_period_height) / 2.0
            for line in period_lines:
                bbox_line = draw.textbbox((0,0), line, font=font_period)
                text_w_line = bbox_line[2] - bbox_line[0]
                x_line = (width - text_w_line) / 2
                draw.text((x_line + 3, current_y_period + 3), line, font=font_period, fill=shadow_color)
                draw.text((x_line, current_y_period), line, font=font_period, fill=text_color_main)
                current_y_period += line_height_period_approx + 15

        tagline_parts = []
        if active_moods: tagline_parts.append(", ".join(active_moods[:2])) 
        if active_styles: tagline_parts.append(", ".join(active_styles[:2])) 
        tagline_text = " | ".join(p for p in tagline_parts if p).title() 
        if tagline_text:
            font_tagline = _get_font(config.COVER_FONT_FILE_PATH, 26)
            if font_tagline:
                try: tagline_bbox = draw.textbbox((0,0), tagline_text, font=font_tagline)
                except AttributeError: tagline_bbox = (0,0) + font_tagline.getsize(tagline_text)
                tagline_w = tagline_bbox[2] - tagline_bbox[0]; tagline_h = tagline_bbox[3] - tagline_bbox[1]
                tagline_x = (width - tagline_w) / 2; tagline_y = height - margin - tagline_h - 15 
                draw.text((tagline_x + 1, tagline_y + 1), tagline_text, font=font_tagline, fill=shadow_color)
                draw.text((tagline_x, tagline_y), tagline_text, font=font_tagline, fill=text_color_secondary)

        img.save(config.COVER_OUTPUT_PATH)
        logger.info(f"Playlist cover generated successfully at {config.COVER_OUTPUT_PATH}")
        return config.COVER_OUTPUT_PATH
    except Exception as e:
        logger.exception(f"Failed to generate playlist cover: {e}"); return None