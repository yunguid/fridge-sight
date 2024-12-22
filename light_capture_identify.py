import cv2
import numpy as np
import time
from datetime import datetime
import os
import logging
from capture_identify import encode_image, ask_openai_for_objects, parse_response_to_json, update_json_file
from openai import OpenAI

# Configuration
CAMERA_INDEX = 0
LIGHT_THRESHOLD = 50
STABILIZATION_TIME = 2
MIN_CAPTURE_INTERVAL = 300
FRAME_SAMPLE_RATE = 0.5
LIGHT_LOG_INTERVAL = 30  # Seconds between light level logs

# Set up logging
def setup_logging():
    log_dir = 'logs'
    os.makedirs(log_dir, exist_ok=True)
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(f'{log_dir}/fridge_monitor.log'),
            logging.StreamHandler()
        ]
    )
    return logging.getLogger('fridge_monitor')

def is_well_lit(frame):
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    avg_brightness = np.mean(gray)
    logger.debug(f"Current brightness: {avg_brightness:.2f}")
    return avg_brightness > LIGHT_THRESHOLD

def setup_camera():
    logger.info("Initializing camera...")
    cap = cv2.VideoCapture(CAMERA_INDEX)
    cap.set(cv2.CAP_PROP_AUTO_EXPOSURE, 1)
    cap.set(cv2.CAP_PROP_AUTOFOCUS, 1)
    
    if not cap.isOpened():
        logger.error("Failed to initialize camera")
        raise RuntimeError("Camera initialization failed")
    
    logger.info("Camera initialized successfully")
    return cap

def capture_and_process(cap, client):
    """Capture and process a single frame"""
    timestamp = datetime.now().strftime('%y%m%d%H%M%S')
    output_path = os.path.join('imgs', f"{timestamp}.jpg")
    os.makedirs('imgs', exist_ok=True)
    
    logger.info(f"Capturing image: {output_path}")
    
    ret, frame = cap.read()
    if not ret:
        logger.error("Frame capture failed")
        raise RuntimeError("Failed to capture frame")
    
    cv2.imwrite(output_path, frame)
    logger.info("Image saved successfully")
    
    try:
        logger.info("Starting OpenAI processing")
        base64_image = encode_image(output_path)
        # Pass client to ask_openai_for_objects
        response_str = ask_openai_for_objects(base64_image, client=client)
        parsed_data = parse_response_to_json(response_str)
        parsed_data['image_path'] = output_path
        update_json_file(parsed_data)
        logger.info("OpenAI processing completed successfully")
        return parsed_data
    except Exception as e:
        logger.error(f"OpenAI processing failed: {str(e)}", exc_info=True)
        raise

def main():
    global logger
    logger = setup_logging()
    logger.info("=== Starting Fridge Monitor ===")
    
    try:
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            logger.error("OPENAI_API_KEY not found in environment")
            raise ValueError("OPENAI_API_KEY environment variable not set")
        
        client = OpenAI(api_key=api_key)
        logger.info("OpenAI client initialized")
        
        cap = setup_camera()
        last_capture_time = 0
        last_light_state = False
        
        last_light_log = 0  # Track last light level log time
        frame_count = 0
        
        logger.info("Beginning light monitoring loop")
        
        while True:
            frame_count += 1
            ret, frame = cap.read()
            if not ret:
                logger.warning("Failed to grab frame, retrying...")
                time.sleep(1)
                continue
            
            current_light_state = is_well_lit(frame)
            current_time = time.time()
            
            # Periodic light level logging
            if current_time - last_light_log >= LIGHT_LOG_INTERVAL:
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                avg_brightness = np.mean(gray)
                logger.info(f"Current light level: {avg_brightness:.2f} (threshold: {LIGHT_THRESHOLD})")
                last_light_log = current_time
            
            # Log every 100 frames to avoid spam
            if frame_count % 100 == 0:
                logger.debug(f"Monitor running: Frame {frame_count}, Light: {current_light_state}")
            
            if (current_light_state and not last_light_state and 
                current_time - last_capture_time > MIN_CAPTURE_INTERVAL):
                
                logger.info("Light change detected, waiting for stabilization...")
                time.sleep(STABILIZATION_TIME)
                
                ret, frame = cap.read()
                if ret and is_well_lit(frame):
                    logger.info("Light stable, initiating capture sequence")
                    try:
                        result = capture_and_process(cap, client)
                        logger.info(f"Detection completed: {len(result.get('items', [])) if result else 0} items found")
                        last_capture_time = current_time
                    except Exception as e:
                        logger.error(f"Capture sequence failed: {str(e)}", exc_info=True)
                else:
                    logger.warning("Light unstable after stabilization period, skipping capture")
            
            last_light_state = current_light_state
            time.sleep(FRAME_SAMPLE_RATE)
            
    except KeyboardInterrupt:
        logger.info("Received shutdown signal")
    except Exception as e:
        logger.critical(f"Unexpected error: {str(e)}", exc_info=True)
    finally:
        if 'cap' in locals():
            cap.release()
        logger.info("=== Fridge Monitor Stopped ===")

if __name__ == "__main__":
    main()

