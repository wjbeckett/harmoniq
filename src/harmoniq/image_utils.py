# src/harmoniq/image_utils.py
import logging
from PIL import Image, ImageDraw, ImageFont, ImageOps
import os
from . import config # For COVER_FONT_FILE_PATH, COVER_PERIOD_COLORS, COVER_OUTPUT_PATH

logger = logging.getLogger(__name__)

def _get_font(font_path, size):
    """Loads a font file or falls back to a default."""
    try:
        return ImageFont.truetype(font_path, size)
    except IOError:
        logger.warning(f"Font not found at '{font_path}'. Attempting to load default system font.")
        try:
            # Pillow's load_default() is very basic, try to get a common one by name
            # This is system-dependent and might not work on slim Docker images
            # common_system_fonts = ["arial.ttf", "LiberationSans-Regular.ttf", "DejaVuSans.ttf"]
            # for sys_font in common_system_fonts:
            #     try: return ImageFont.truetype(sys_font, size)
            #     except IOError: pass
            return ImageFont.load_default() # Very basic fallback
        except IOError:
            logger.error("Could not load any default font. Text rendering will fail.")
            return None # Should ideally not happen

def _wrap_text(text: str, font: ImageFont.FreeTypeFont, max_width: int) -> list[str]:
    """Wraps text to fit within a maximum width."""
    lines = []
    if not text or not font: return lines
    
    words = text.split()
    current_line = ""
    for word in words:
        # Test line with the new word
        test_line = f"{current_line} {word}".strip()
        # Get bounding box for the test line text
        # textbbox is preferred over textsize in newer Pillow
        try:
            bbox = font.getbbox(test_line) # (left, top, right, bottom)
            line_width = bbox[2] - bbox[0]
        except AttributeError: # Fallback for older Pillow or basic font
            line_width = font.getsize(test_line)[0]


        if line_width <= max_width:
            current_line = test_line
        else:
            # Word doesn't fit, push current_line and start new line with word
            if current_line: # Avoid adding empty line if first word is too long
                lines.append(current_line)
            current_line = word
            # If a single word is too long, it will overflow (can be truncated later if needed)
            # For simplicity, we don't split words here.
    if current_line:
        lines.append(current_line)
    return lines

def generate_playlist_cover(playlist_title: str, 
                            period_name: str | None = None,
                            active_moods: list[str] | None = None,
                            active_styles: list[str] | None = None) -> str | None:
    """
    Generates a playlist cover image.

    Args:
        playlist_title: The main title for the playlist (e.g., "Harmoniq Flow").
        period_name: The name of the active period (e.g., "Morning", "Afternoon").
        active_moods: List of dominant moods for the period/playlist.
        active_styles: List of dominant styles/genres.

    Returns:
        Path to the generated image file, or None if generation failed.
    """
    if not config.ENABLE_PLAYLIST_COVERS:
        logger.debug("Playlist cover generation is disabled in config.")
        return None

    logger.info(f"Generating playlist cover for '{playlist_title}' (Period: {period_name})")

    width, height = 600, 600  # Standard cover size
    
    # Determine background colors based on period
    default_colors = config.COVER_PERIOD_COLORS.get("DefaultVibe", ((100,100,100), (150,150,150)))
    colors = config.COVER_PERIOD_COLORS.get(period_name, default_colors) if period_name else default_colors
    
    try:
        # Create a gradient background
        # For simplicity, let's do a two-color vertical gradient
        img = Image.new("RGB", (width, height))
        draw = ImageDraw.Draw(img)
        
        # Top color to bottom color
        color1_rgb = colors[0]
        color2_rgb = colors[1]

        for y in range(height):
            r = int(color1_rgb[0] + (color2_rgb[0] - color1_rgb[0]) * y / height)
            g = int(color1_rgb[1] + (color2_rgb[1] - color1_rgb[1]) * y / height)
            b = int(color1_rgb[2] + (color2_rgb[2] - color1_rgb[2]) * y / height)
            draw.line([(0, y), (width, y)], fill=(r, g, b))

        # --- Text Elements ---
        # Padding and margins
        margin = 40
        text_width_max = width - (2 * margin)

        # Font loading
        title_font_size = 60
        subtitle_font_size = 30
        details_font_size = 24
        
        font_title = _get_font(config.COVER_FONT_FILE_PATH, title_font_size)
        font_subtitle = _get_font(config.COVER_FONT_FILE_PATH, subtitle_font_size)
        # font_details = _get_font(config.COVER_FONT_FILE_PATH, details_font_size) # If adding moods/styles

        if not font_title or not font_subtitle: # or not font_details
            logger.error("Failed to load fonts for cover generation.")
            return None

        text_color = (255, 255, 255) # White text
        shadow_color = (0, 0, 0, 100) # Semi-transparent black shadow

        # 1. Main Playlist Title (e.g., "Harmoniq Flow")
        # Centered, multi-line if needed
        title_lines = _wrap_text(playlist_title.upper(), font_title, text_width_max)
        current_y = margin + 20 # Start a bit down
        line_height_title = font_title.getbbox("A")[3] - font_title.getbbox("A")[1] if hasattr(font_title, 'getbbox') else font_title.getsize("A")[1]


        for line_num, line in enumerate(title_lines):
            bbox = font_title.getbbox(line)
            text_w = bbox[2] - bbox[0]
            text_h = bbox[3] - bbox[1] # Or use line_height_title
            
            x = (width - text_w) / 2
            # Shadow
            draw.text((x + 2, current_y + 2), line, font=font_title, fill=shadow_color)
            # Text
            draw.text((x, current_y), line, font=font_title, fill=text_color)
            current_y += line_height_title + 5 # Add some spacing

        # 2. Subtitle (e.g., Period Name like "Morning Mix" or "Evening Vibes")
        if period_name:
            subtitle_text = f"{period_name}" # Could be "Morning Mix", "Evening Unwind", etc.
            subtitle_lines = _wrap_text(subtitle_text, font_subtitle, text_width_max)
            current_y += 20 # Extra space after title
            line_height_subtitle = font_subtitle.getbbox("A")[3] - font_subtitle.getbbox("A")[1] if hasattr(font_subtitle, 'getbbox') else font_subtitle.getsize("A")[1]

            for line in subtitle_lines:
                bbox = font_subtitle.getbbox(line)
                text_w = bbox[2] - bbox[0]
                x = (width - text_w) / 2
                # Shadow
                draw.text((x + 1, current_y + 1), line, font=font_subtitle, fill=shadow_color)
                # Text
                draw.text((x, current_y), line, font=font_subtitle, fill=text_color)
                current_y += line_height_subtitle + 3


        # (Optional: Add dominant moods/styles as smaller text at the bottom)
        #if active_moods or active_styles:
        #    details_text = []
        #    if active_moods: details_text.append(", ".join(active_moods[:2])) # Show top 2 moods
        #    if active_styles: details_text.append(", ".join(active_styles[:2])) # Show top 2 styles
        #    full_details_str = " | ".join(d for d in details_text if d)
        #    
        #    if full_details_str:
        #        # Position towards bottom
        #        bbox_details = font_details.getbbox(full_details_str)
        #        details_w = bbox_details[2] - bbox_details[0]
        #        details_h = bbox_details[3] - bbox_details[1]
        #        details_x = (width - details_w) / 2
        #        details_y = height - margin - details_h - 10
        #        draw.text((details_x+1, details_y+1), full_details_str, font=font_details, fill=shadow_color)
        #        draw.text((details_x, details_y), full_details_str, font=font_details, fill=text_color)


        # Save the image to the configured temporary path
        img.save(config.COVER_OUTPUT_PATH)
        logger.info(f"Playlist cover generated successfully at {config.COVER_OUTPUT_PATH}")
        return config.COVER_OUTPUT_PATH

    except Exception as e:
        logger.exception(f"Failed to generate playlist cover: {e}")
        return None