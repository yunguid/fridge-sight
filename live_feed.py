import cv2
from flask import Flask, Response, render_template_string
import threading

app = Flask(__name__)

# HTML template for the live feed page
HTML_PAGE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Fridge Camera Live Feed</title>
    <style>
        body { text-align: center; background-color: #f0f0f0; }
        h1 { color: #333; }
        img { border: 2px solid #333; }
    </style>
</head>
<body>
    <h1>Fridge Camera Live Feed</h1>
    <img src="{{ url_for('video_feed') }}" width="640" height="480">
</body>
</html>
"""

class VideoCamera:
    def __init__(self):
        # Initialize the video camera
        self.video = cv2.VideoCapture(0)  # 0 is the default camera

        if not self.video.isOpened():
            raise RuntimeError("Could not start camera.")

        # Lock for thread-safe frame access
        self.lock = threading.Lock()
        self.frame = None

        # Start the frame update thread
        thread = threading.Thread(target=self.update_frame, args=())
        thread.daemon = True
        thread.start()

    def update_frame(self):
        while True:
            success, frame = self.video.read()
            if not success:
                continue

            # Encode the frame in JPEG format
            ret, jpeg = cv2.imencode('.jpg', frame)
            if not ret:
                continue

            with self.lock:
                self.frame = jpeg.tobytes()

    def get_frame(self):
        with self.lock:
            return self.frame

    def __del__(self):
        if self.video.isOpened():
            self.video.release()

# Initialize the camera
camera = VideoCamera()

def generate_frames():
    while True:
        frame = camera.get_frame()
        if frame is None:
            continue

        # Yield the frame in byte format
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')

@app.route('/')
def index():
    # Render the HTML page
    return render_template_string(HTML_PAGE)

@app.route('/video_feed')
def video_feed():
    # Return the response generated along with the specific media type (mime type)
    return Response(generate_frames(),
                    mimetype='multipart/x-mixed-replace; boundary=frame')

if __name__ == '__main__':
    # Run the Flask app on all available IPs on port 5000
    app.run(host='0.0.0.0', port=5000, threaded=True)

