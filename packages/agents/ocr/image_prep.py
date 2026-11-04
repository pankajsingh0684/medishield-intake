"""Image preprocessing: deskew and rotate correction."""

import logging

import cv2
import numpy as np
from PIL import Image

logger = logging.getLogger(__name__)


def deskew_image(image: Image.Image, angle_threshold: float = 0.5) -> Image.Image:
    """
    Deskew an image by detecting and correcting rotation.

    Uses edge detection and Hough line transform to detect the dominant angle
    and rotate the image back to horizontal.

    Args:
        image: PIL Image to deskew
        angle_threshold: Skip deskewing if detected angle is below this (degrees)

    Returns:
        Deskewed PIL Image
    """
    try:
        # Convert PIL image to numpy array
        img_array = np.array(image.convert("RGB"))

        # Convert to grayscale
        gray = cv2.cvtColor(img_array, cv2.COLOR_RGB2GRAY)

        # Apply edge detection
        edges = cv2.Canny(gray, 50, 150)

        # Detect lines using Hough transform
        lines = cv2.HoughLines(edges, 1, np.pi / 180, 100)

        if lines is None or len(lines) == 0:
            logger.debug("No lines detected for deskewing; returning original image")
            return image

        # Extract angles from detected lines
        angles = []
        for line in lines:
            _, theta = line[0]
            # Convert theta to degrees and normalize to -45 to 45
            angle = (theta * 180 / np.pi) - 90
            if abs(angle) > 45:
                angle = angle - np.sign(angle) * 180
            angles.append(angle)

        # Use median angle
        median_angle = float(np.median(angles))

        # Only deskew if angle is significant
        if abs(median_angle) < angle_threshold:
            logger.debug(f"Detected angle {median_angle:.1f}° below threshold; skipping deskew")
            return image

        logger.debug(f"Detected skew angle: {median_angle:.1f}°; correcting")

        # Rotate image to correct skew
        h, w = img_array.shape[:2]
        center = (w // 2, h // 2)

        rotation_matrix = cv2.getRotationMatrix2D(center, median_angle, 1.0)

        # Apply rotation with white background
        rotated = cv2.warpAffine(
            img_array,
            rotation_matrix,
            (w, h),
            borderMode=cv2.BORDER_CONSTANT,
            borderValue=(255, 255, 255),
        )

        # Convert back to PIL
        corrected = Image.fromarray(rotated)
        corrected.info.update(image.info)
        return corrected

    except (cv2.error, TypeError, ValueError) as e:
        logger.warning(f"Deskewing failed: {e}; returning original image")
        return image


def validate_image_quality(image: Image.Image) -> tuple[bool, str]:
    """
    Validate image quality for OCR.

    Args:
        image: PIL Image to validate

    Returns:
        Tuple of (is_valid, message)
    """
    if image.size[0] < 100 or image.size[1] < 100:
        return False, "Image too small for OCR"

    if image.mode not in ("RGB", "RGBA", "L"):
        return False, f"Unsupported image mode: {image.mode}"

    return True, "OK"
