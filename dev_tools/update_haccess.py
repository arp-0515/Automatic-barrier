# This Python file uses the following encoding: utf-8
# Script to update I_HACCESS template image
# Usage: Run this script when game is showing the Hyakkiyakou page

import sys
import time
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import cv2
from module.config.config import Config
from module.device.device import Device
from module.logger import logger
from tasks.GameUi.page import page_hyakkiyakou


def capture_and_save_template(config_name='oas1'):
    """
    Capture current screen and save I_HACCESS template
    """
    logger.info('Starting template update...')
    
    # Initialize device
    c = Config(config_name)
    d = Device(c)
    
    # Take screenshot
    logger.info('Taking screenshot...')
    d.screenshot()
    
    # Save full screenshot for reference
    full_screenshot_path = project_root / 'log' / 'hya_full_screenshot.png'
    full_screenshot_path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(full_screenshot_path), d.image)
    logger.info(f'Full screenshot saved: {full_screenshot_path}')
    
    # I_HACCESS roi_front=(1070,570,100,100)
    x, y, w, h = 1070, 570, 100, 100
    
    # Ensure ROI is within image bounds
    img_h, img_w = d.image.shape[:2]
    x = min(x, img_w - w)
    y = min(y, img_h - h)
    
    # Crop and save template
    template = d.image[y:y+h, x:x+w]
    template_path = project_root / 'tasks' / 'Hyakkiyakou' / 'hya' / 'hya_haccess.png'
    cv2.imwrite(str(template_path), template)
    logger.info(f'Template saved: {template_path}')
    
    # Also save a version with border for visual verification
    template_with_border = d.image[y:y+h, x:x+w].copy()
    cv2.rectangle(template_with_border, (0, 0), (w-1, h-1), (0, 255, 0), 2)
    verify_path = project_root / 'log' / 'hya_haccess_verify.png'
    cv2.imwrite(str(verify_path), template_with_border)
    logger.info(f'Verification image saved: {verify_path}')
    
    logger.info('Template update completed!')
    logger.info('Please restart the Hyakkiyakou script.')
    
    return str(template_path)


if __name__ == '__main__':
    config_name = sys.argv[1] if len(sys.argv) > 1 else 'oas1'
    capture_and_save_template(config_name)
