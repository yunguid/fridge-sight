import cv2
import base64
import json
import os
import argparse
import subprocess
from openai import OpenAI
from datetime import datetime
import time

# Configuration
JSON_OUTPUT_FILE = "detected_objects.json"
CAMERA_INDEX = 0
IMAGE_DIR = "imgs"
MAX_RETRIES = 3
RETRY_DELAY = 2
DEFAULT_NUM_IMAGES = 1
DEFAULT_REMOTE_USER = "luke"
DEFAULT_REMOTE_HOST = "fridgecam.local"
DEFAULT_LOCAL_PATH = "/Users/luke/cursor-projs/sight/images"

def parse_args():
    parser = argparse.ArgumentParser(description='Capture and analyze fridge images')
    parser.add_argument('--num_images', '-n', type=int, default=DEFAULT_NUM_IMAGES,
                      help='Number of images to capture')
    parser.add_argument('--transfer_imgs', '-t', action='store_true',
                      help='Transfer images to local machine after capture')
    parser.add_argument('--remote_user', type=str, default=DEFAULT_REMOTE_USER,
                      help='Remote username for image transfer')
    parser.add_argument('--remote_host', type=str, default=DEFAULT_REMOTE_HOST,
                      help='Remote hostname for image transfer')
    parser.add_argument('--local_path', type=str, default=DEFAULT_LOCAL_PATH,
                      help='Local path to store transferred images')
    return parser.parse_args()

def capture_image(camera_index=0, attempts=3):
    # Create imgs directory if it doesn't exist
    os.makedirs(IMAGE_DIR, exist_ok=True)
    
    for attempt in range(attempts):
        try:
            cap = cv2.VideoCapture(camera_index)
            if not cap.isOpened():
                raise RuntimeError(f"Camera init failed, attempt {attempt + 1}/{attempts}")
            
            # Wait for camera to initialize
            time.sleep(0.5)
            
            ret, frame = cap.read()
            cap.release()
            
            if not ret or frame is None:
                raise RuntimeError("Frame capture failed")
            
            # Generate output path with timestamp
            timestamp = datetime.now().strftime('%y%m%d%H%M%S')
            output_path = os.path.join(IMAGE_DIR, f"{timestamp}.jpg")
            
            cv2.imwrite(output_path, frame)
            return output_path
            
        except Exception as e:
            print(f"Attempt {attempt + 1} failed: {str(e)}")
            if attempt == attempts - 1:
                raise RuntimeError(f"Failed to capture image after {attempts} attempts")
            time.sleep(1)

def encode_image(image_path):
    try:
        with open(image_path, "rb") as image_file:
            return base64.b64encode(image_file.read()).decode("utf-8")
    except Exception as e:
        raise RuntimeError(f"Image encoding failed: {str(e)}")

def ask_openai_for_objects(base64_image, client=None, max_retries=MAX_RETRIES):
    """
    Ask OpenAI to identify objects in the image.
    Args:
        base64_image: Base64 encoded image
        client: OpenAI client instance
        max_retries: Maximum number of retry attempts
    """
    if client is None:
        raise ValueError("OpenAI client must be provided")
        
    prompt_text = """Analyze this fridge image and identify visible items.
    Respond ONLY with valid JSON in this exact format:
    {
      "items": [
        {
          "type": "string",      // Basic category (e.g., "Milk", "Juice", "Yogurt", "Leftovers")
          "brand": "string",     // Brand if clearly visible, "Unknown" if not
          "quantity": {
            "count": number,     // Number of containers
            "size": "string"     // Container size if visible (e.g., "1 gallon", "32 oz", "Unknown")
          },
          "confidence": "string" // "High", "Medium", or "Low" based on visibility/clarity
        }
      ]
    }"""
    messages = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": prompt_text},
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}
                }
            ]
        }
    ]
    
    for attempt in range(max_retries):
        try:
            response = client.chat.completions.create(
                model="gpt-4o",  # Keeping the model as gpt-4o as requested
                messages=messages,
                max_tokens=300,
                temperature=0.3
            )
            
            # Debug print
            print(f"Raw API response: {response.choices[0].message.content}")
            
            response_text = response.choices[0].message.content.strip()
            
            # Try to extract JSON if it's embedded in the response
            if '```json' in response_text:
                response_text = response_text.split('```json')[1].split('```')[0].strip()
            elif '```' in response_text:
                response_text = response_text.split('```')[1].split('```')[0].strip()
                
            # Clean any potential markdown or extra text
            if '{' in response_text:
                response_text = response_text[response_text.find('{'):response_text.rfind('}')+1]
            
            # Validate JSON
            try:
                json.loads(response_text)
                return response_text
            except json.JSONDecodeError as je:
                print(f"JSON validation failed: {je}")
                raise
            
        except Exception as e:
            print(f"Attempt {attempt + 1} failed: {str(e)}")
            print(f"Response text: {response_text if 'response_text' in locals() else 'No response'}")
            if attempt == max_retries - 1:
                raise RuntimeError(f"Failed after {max_retries} attempts: {str(e)}")
            time.sleep(RETRY_DELAY)

def parse_response_to_json(response_str):
    try:
        # Remove any potential Unicode BOM or whitespace
        cleaned_response = response_str.strip().lstrip('\ufeff')
        
        # Try to extract JSON if it's embedded in the response
        if '```json' in cleaned_response:
            cleaned_response = cleaned_response.split('```json')[1].split('```')[0].strip()
        elif '```' in cleaned_response:
            cleaned_response = cleaned_response.split('```')[1].split('```')[0].strip()
            
        # Clean any potential markdown or extra text
        if '{' in cleaned_response:
            cleaned_response = cleaned_response[cleaned_response.find('{'):cleaned_response.rfind('}')+1]
        
        data = json.loads(cleaned_response)
        
        # Validate expected structure - changed from "objects" to "items"
        if not isinstance(data, dict) or "items" not in data:
            raise ValueError("Invalid response structure - missing 'items' key")
            
        # Validate items structure
        for item in data["items"]:
            required_keys = {"type", "brand", "quantity", "confidence"}
            if not all(key in item for key in required_keys):
                raise ValueError(f"Invalid item structure - missing required keys: {required_keys}")
            
            if not isinstance(item["quantity"], dict) or \
               not all(key in item["quantity"] for key in ["count", "size"]):
                raise ValueError("Invalid quantity structure")
        
        return data
        
    except json.JSONDecodeError as e:
        print(f"JSON Parse Error: {str(e)}")
        print(f"Raw response: {response_str}")
        print(f"Cleaned response: {cleaned_response}")
        raise ValueError(f"Invalid JSON response: {str(e)}")

def update_json_file(data, output_file=JSON_OUTPUT_FILE):
    # Create timestamp for the detection
    data['timestamp'] = datetime.now().isoformat()
    
    try:
        # Ensure directory exists
        os.makedirs(os.path.dirname(output_file) or '.', exist_ok=True)
        
        with open(output_file, "w") as f:
            json.dump(data, f, indent=2)
            
    except Exception as e:
        raise RuntimeError(f"Failed to save JSON: {str(e)}")

def transfer_images(remote_user, remote_host, local_path):
    try:
        # Ensure local directory exists
        os.makedirs(local_path, exist_ok=True)
        
        # Construct scp command
        cmd = f"scp -r {remote_user}@{remote_host}:~/fridge_camera/imgs/ {local_path}/"
        print(f"Executing transfer command: {cmd}")
        
        # Execute transfer
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        
        if result.returncode != 0:
            print(f"Transfer failed: {result.stderr}")
            return False
            
        print("Images transferred successfully")
        return True
        
    except Exception as e:
        print(f"Transfer failed: {str(e)}")
        return False

def main():
    args = parse_args()
    
    try:
        # Initialize OpenAI client
        global client
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY environment variable not set")
        client = OpenAI(api_key=api_key)
        
        # Capture multiple images if requested
        captured_images = []
        for i in range(args.num_images):
            print(f"\nCapturing image {i+1}/{args.num_images}")
            img_path = capture_image(CAMERA_INDEX)
            captured_images.append(img_path)
            
            # Process each image
            base64_image = encode_image(img_path)
            response_str = ask_openai_for_objects(base64_image, client)
            parsed_data = parse_response_to_json(response_str)
            
            # Add image path to JSON
            parsed_data['image_path'] = img_path
            update_json_file(parsed_data)
            
            print(f"Detection completed for image {i+1}")
            print(json.dumps(parsed_data, indent=2))
            
            # Wait between captures
            if i < args.num_images - 1:
                time.sleep(2)
        
        # Transfer images if requested
        if args.transfer_imgs:
            print("\nTransferring images to local machine...")
            transfer_images(args.remote_user, args.remote_host, args.local_path)
            
    except Exception as e:
        print(f"Error in main execution: {str(e)}")
        raise

if __name__ == "__main__":
    main()
