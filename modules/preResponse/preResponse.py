import os
import random
import wave
from typing import Dict, List

from modules.base import BaseModule
from modules.audioModules.micSource import AudioFormat
from modules.utils import load_wav_chunks
from modules.TTS.tts2 import TTS2 as TTS

HELLO_RESPONSE = {"id": 0, "text": "Hello, thank you for calling Vehicle Service Center. "
                               "I'm the automated booking assistant, and I can help you "
                               "schedule a vehicle service or repair appointment. This will "
                               "only take a couple of minutes. Shall we get started?"}
# HELLO_RESPONSE = {"id": 0, "text": "Hello, thank you for calling Vehicle Service Center."}
END_RESPONSE = {"id": 1, "text": "Thank you for your time. Your responses have been recorded. Have a great day. Goodbye."}
RANDOM_RESPONSE = [
    {"id": 2, "text": "Great."},
    {"id": 3, "text": "Thank you."},
    {"id": 4, "text": "Got it."},
    {"id": 5, "text": "Perfect."},
    {"id": 6, "text": "Understood."},
    {"id": 7, "text": "Alright."},
    {"id": 8, "text": "Sounds good."},
    {"id": 9, "text": "Excellent."},
    {"id": 10, "text": "Sure thing."},
    {"id": 11, "text": "Noted."},
    {"id": 12, "text": "Okay."}
]

ALL_RESPONSES = [HELLO_RESPONSE, END_RESPONSE] + RANDOM_RESPONSE

class PreResponse(BaseModule):
    def __init__(self, fmt: AudioFormat, seed=42):
        super().__init__("PreResponse")
        self.fmt = fmt
        self.seed = seed
        random.seed(self.seed)
        self._audio_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "audio")
        self._cache: Dict[int, List[bytes]] = {}

    def init(self):
        self.logger.info("Initialising PreResponse")
        os.makedirs(self._audio_dir, exist_ok=True)
        tts_module = None

        for resp in ALL_RESPONSES:
            wav_path = os.path.join(self._audio_dir, f"{resp['id']}.wav")

            if not os.path.exists(wav_path):
                self.logger.warning(f"Missing audio file: {wav_path}, generating using TTS...")
                if tts_module is None:
                    tts_module = TTS()
                    tts_module.init()

                tts_module.process(resp['text'])

                pcm_data = bytearray()
                while True:
                    chunk = tts_module.chunk_queue.get()
                    if chunk == b'DONE':
                        break
                    pcm_data.extend(chunk)

                with wave.open(wav_path, 'wb') as wf:
                    wf.setnchannels(self.fmt.channels)
                    wf.setsampwidth(self.fmt.sample_width)
                    wf.setframerate(self.fmt.rate)
                    wf.writeframes(pcm_data)

                self.logger.info(f"Successfully generated and saved: {wav_path}")
            self._cache[resp['id']] = load_wav_chunks(wav_path, self.fmt)

            self.logger.debug(f"Loaded response {resp['id']}: {len(self._cache[resp['id']])} chunks")
        return True

    def get_response(self, re_type) -> List[bytes]:
        if re_type == "hello":
            re = HELLO_RESPONSE
        elif re_type == "random":
            re = random.choice(RANDOM_RESPONSE)
        elif re_type == "end":
            re = END_RESPONSE
        else:
            raise NotImplementedError(f"Invalid type: {re_type}")

        self.logger.debug(f"Response: {re['text']}")
        return self._cache[re['id']]
    
if __name__ == "__main__":
    from modules.utils import init_logger
    init_logger()
    
    print("Starting PreResponse Test...")
    fmt = AudioFormat()
    pr = PreResponse(fmt=fmt)
    
    pr.init() 
    
    print("\n--- Testing Retrieval ---")
    chunks = pr.get_response("random")
    print(f"Test Successful! Retrieved {len(chunks)} chunks of audio for a random response.")
