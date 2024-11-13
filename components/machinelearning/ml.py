import time
import json
import os
import numpy as np
import cv2
import threading
from time import sleep
import torch
import torchvision
import torchvision.transforms as transforms
import torch.nn.functional as F
import queue
import logging

from components.machinelearning.util import preprocess
from components.communications import esp_server
from components.communications import client_server

class NpEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, np.integer):
            return int(obj)
        if isinstance(obj, np.floating):
            return float(obj)
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        return super(NpEncoder, self).default(obj)

def start_ml():
    global ml_processor
    ml_processor = MLProcessor()
    logging.debug('ML OPEN')

class MLProcessor:

    model_dir = '/home/visionsystem/Vision-System-Python/components/machinelearning/models/'

    def enqueue(self, message):
        message = json.loads(message)
        ip = message['ESPIP'][0]
        team_name = message['team_name']
        model_index = message["model_index"]
        task = {
            'team_name': team_name,
            'ip': ip,
            'model_index' : model_index
        }
        # frame is optional, it is a jpeg encoded image.
        if message['frame']:
            task['frame'] = message['frame']
        self.task_queue.put(task)

    def handler(self, image, team_name, model_index):
        model_fi = None
        for entry in os.scandir(self.model_dir):
            if entry.name.startswith(team_name) and int(entry.name.split('_')[1]) == model_index:
                model_fi = entry.name
                break

        if model_fi is None:
            raise Exception(f"Could not find model for team: {team_name} with model index: {model_index}; Available models: {', '.join([entry.name for entry in os.scandir(self.model_dir)])}")

        num_str = model_fi.split('_')[-1] # get last segment "#.pth"
        num_str = os.path.splitext(num_str)[0] # get rid of ".pth"
        dim = int(num_str)

        self.model.fc = torch.nn.Linear(512, dim)
        self.model = self.model.to(torch.device('cpu'))

        logging.debug(f"using model {model_fi}...")
        self.model.load_state_dict(torch.load(self.model_dir + model_fi, map_location=torch.device('cpu'), weights_only=True))

        self.model.eval()
        output = self.model(image)
        output = F.softmax(output, dim=1).detach().cpu().numpy().flatten()

        return output.argmax()

    def processor(self):
        while True:
            request = self.task_queue.get(block=True, timeout=None)

            ip = request["ip"]
            team_name = request["team_name"]
            model_index = request["model_index"]
            logging.debug(f'Handling message from team {team_name}' )

            start = time.perf_counter()
            try:
                if request.get('frame'):
                    import base64
                    frame_bytes = base64.b64decode(request['frame'].encode())
                    frame = cv2.imdecode(np.frombuffer(frame_bytes, np.uint8), -1)
                else:
                    cap = cv2.VideoCapture('http://' + ip + "/cam.jpg")
                    if cap.isOpened():
                        ret, frame = cap.read()
                    else:
                        raise Exception("Could not get image from WiFiCam (cv2)")

                logging.debug('Got frame. Preprocessing...' )
                picture = preprocess(frame)
                results = self.handler(picture, team_name, model_index)
            except Exception as e:
                logging.debug('ML FAILED :(')
                logging.debug(str(e))
                client_server.send_console_message(
                    f"ML prediction from team {team_name} FAILED with error: {str(e)}.")
                return

            logging.debug('Results: ' + str(results))
            esp_server.send_prediction(team_name, str(results))
            client_server.send_console_message(
                f"ML prediction from team {team_name} finished in {(time.perf_counter() - start):.2f} seconds. Result (prediction: {results}) sent to the teams wifi module.")

    def __init__(self):
        self.task_queue = queue.Queue()
        self.model = torchvision.models.resnet18(weights='IMAGENET1K_V1')

        threading.Thread(name='task queue handler', args=(), target=self.processor).start()

