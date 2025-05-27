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
    if not words: return []

    current_line = words[0]
    for i in range(1, len(words)):
        word = words[i]
        test_line = f"{current_line} {word}"
        try:
            bbox = drawer.textbbox((0,0), test_line, font=font) 
            line_width = bbox[2] - bbox[0]
        except AttributeError: 
            line_width = drawer.textsize(test_line, font=font)[0]

        if line_width <= max_width:
            current_line = test_line
        else:
            lines.append(current_line)
            current_line = word
    if current_line:
        lines.append(current_line)
    return lines

def generate_playlist_cover(playlist_title: str, # "Harmoniq Flow"
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
        draw = ImageDraw.Draw(img)
        color1_rgb, color2_rgb = colors[0], colors[1]
        for y_grad in range(height):
            r = int(color1_rgb[0] + (color2_rgb[0] - color1_rgb[0]) * y_grad / height)
            g = int(color1_rgb[1] + (color2_rgb[1] - color1_rgb[1]) * y_grad / height)
            b = int(color1_rgb[2] + (color2_rgb[2] - color1_rgb[2]) * y_grad / height)
            draw.line([(0, y_grad), (width, y_grad)], fill=(r, g, b))

        margin = 45
        text_width_max = width - (2 * margin)
        text_color_main = (255, 255, 255, 245) 
        text_color_secondary = (230, 230, 230, 220)
        text_color_brand = (255, 255, 255, 180) # More subtle for brand
        shadow_color = (0, 0, 0, 70) 
        shadow_offset = 3 # Make shadow slightly more offset for depth

        # --- 1. "HARMONIQ" Brand (Top Center, smaller) ---
        font_brand_size = 32
        font_brand = _get_font(config.COVER_FONT_FILE_PATH, font_brand_size)
        brand_text = "HARMONIQ" # Or could be playlist_title if we want "Harmoniq Flow" here
        if font_brand:
            try: brand_bbox = draw.textbbox((0,0), brand_text, font=font_brand)
            except AttributeError: brand_bbox = (0,0) + font_brand.getsize(brand_text)
            brand_w = brand_bbox[2] - brand_bbox[0]
            brand_x = (width - brand_w) / 2
            brand_y = margin 
            draw.text((brand_x + 1, brand_y + 1), brand_text, font=font_brand, fill=shadow_color)
            draw.text((brand_x, brand_y), brand_text, font=font_brand, fill=text_color_brand)

        # --- 2. Period Name (Large, Centered below brand) ---
        display_period_name = period_name.replace("EarlyMorning", "Early Morning").replace("LateNight", "Late Night") if period_name else "Daily Mix"
        
        # Dynamically adjust font size for period name to fit
        period_font_size_initial = 110
        font_period = _get_font(config.COVER_FONT_FILE_PATH, period_font_size_initial)
        
        if font_period:
            period_lines = _wrap_text(display_period_name.upper(), font_period, draw, text_width_max - 20) # Slightly smaller max_width for safety
            # Reduce font size if still too wide or too many lines
            while (any(draw.textbbox((0,0),line,font=font_period)[2] > text_width_max for line in period_lines) or \
                  len(period_lines) > 2) and period_font_size_initial > 40: # Min font size
                period_font_size_initial -= 5
                font_period = _get_font(config.COVER_FONT_FILE_PATH, period_font_size_initial)
                period_lines = _wrap_text(display_period_name.upper(), font_period, draw, text_width_max - 20)

            try: line_height_period = font_period.getbbox("A")[3] - font_period.getbbox("A")[1]
            except AttributeError: line_height_period = font_period.getsize("A")[1]
            
            total_period_height = len(period_lines) * line_height_period + (len(period_lines) - 1) * 10 
            
            # Position below brand text, more towards center
            current_y_period = (height - total_period_height) / 2 # Center it more aggressively
            if font_brand: current_y_period = max(current_y_period, brand_bbox[3] + 25) # Ensure it's below brand

            for line in period_lines:
                bbox_line = draw.textbbox((0,0), line, font=font_period)
                text_w_line = bbox_line[2] - bbox_line[0]
                x_line = (width - text_w_line) / 2
                draw.text((x_line + shadow_offset, current_y_period + shadow_offset), line, font=font_period, fill=shadow_color)
                draw.text((x_line, current_y_period), line, font=font_period, fill=text_color_main)
                current_y_period += line_height_period + 10


        # --- 3. Tagline (Dominant Moods/Styles - Bottom, smaller) ---
        tagline_parts = []
        if active_moods: tagline_parts.append(", ".join(active_moods[:2]))
        if active_styles: tagline_parts.append(", ".join(active_styles[:2]))
        tagline_text = " | ".join(p for p in tagline_parts if p).title() 

        if tagline_text:
            font_tagline_size = 28
            font_tagline = _get_font(config.COVER_FONT_FILE_PATH, font_tagline_size)
            if font_tagline:
                # Ensure tagline also fits
                tagline_lines = _wrap_text(tagline_text, font_tagline, draw, text_width_max)
                
                try: line_height_tagline = font_tagline.getbbox("A")[3] - font_tagline.getbbox("A")[1]
                except AttributeError: line_height_tagline = font_tagline.getsize("A")[1]
                
                total_tagline_height = len(tagline_lines) * line_height_tagline + (len(tagline_lines)-1) * 5
                tagline_y_start = height - margin - total_tagline_height # Position from bottom

                for line in tagline_lines:
                    bbox_tagline = draw.textbbox((0,0), line, font=font_tagline)
                    tagline_w_line = bbox_tagline[2] - bbox_tagline[0]
                    tagline_x_line = (width - tagline_w_line) / 2
                    draw.text((tagline_x_line + 1, tagline_y_start + 1), line, font=font_tagline, fill=shadow_color)
                    draw.text((tagline_x_line, tagline_y_start), line, font=font_tagline, fill=text_color_secondary)
                    tagline_y_start += line_height_tagline + 5


        img.save(config.COVER_OUTPUT_PATH)
        logger.info(f"Playlist cover generated (improved) successfully at {config.COVER_OUTPUT_PATH}")
        return config.COVER_OUTPUT_PATH
    except Exception as e:
        logger.exception(f"Failed to generate playlist cover: {e}"); return None