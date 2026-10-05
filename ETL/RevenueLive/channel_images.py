"""Decode bounded raster uploads and strip metadata before database storage."""
import io
import warnings

from PIL import Image, ImageOps, UnidentifiedImageError

MAX_LOGO_BYTES = 2 * 1024 * 1024
MAX_LOGO_PIXELS = 4_000_000


def normalize_logo(content):
    if not content or len(content) > MAX_LOGO_BYTES:
        raise ValueError('Choose a PNG, JPG or WebP logo up to 2 MB.')
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error', Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(content)) as source:
                if source.format not in {'PNG', 'JPEG', 'WEBP'}:
                    raise ValueError('Use a PNG, JPG or WebP image.')
                if source.width * source.height > MAX_LOGO_PIXELS:
                    raise ValueError('Logo dimensions must not exceed 4 megapixels.')
                if getattr(source, 'is_animated', False):
                    raise ValueError('Use a still image for the channel logo.')
                source.load()
                image = ImageOps.exif_transpose(source).convert('RGBA')
                image.thumbnail((512, 512), Image.Resampling.LANCZOS)
                # A fresh image drops original EXIF, comments and color profiles.
                clean = Image.new('RGBA', image.size)
                clean.paste(image)
                output = io.BytesIO()
                clean.save(output, format='PNG', optimize=True)
                return output.getvalue()
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError,
            Image.DecompressionBombWarning) as error:
        raise ValueError('This logo could not be read. Choose a valid PNG, JPG or WebP image.') from error
