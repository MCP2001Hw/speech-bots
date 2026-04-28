import threading
import queue
import subprocess
import time
import requests

from modules.utils import init_logger
from modules.base import BaseModule
from modules.audioModules.micSource import AudioFormat


class TTS(BaseModule):
    UTTERANCE_END = object()  # 哨兵值：一条语音合成完毕

    def __init__(self, model="google"):
        super().__init__("TTS")
        self.fmt = AudioFormat()

        # rate: int = 16000
        # frames_per_chunk: int = 256
        #    Chunk = frame x channels x sample_width
        self.bytes_per_chunk = self.fmt.frames_per_chunk * self.fmt.channels * self.fmt.sample_width

        #    Init TTS and FFMPEG processes, prepare for streaming output
        self.edge_TTS_process = None
        self.ffmpeg_process = None

        #    Init queues and flags for streaming control
        self.chunk_queue = queue.Queue()
        self._cancel_flag = threading.Event()
        self.text_queue = queue.Queue()
        if model == "edge":
            threading.Thread(target=self.edge_tts, daemon=True).start()
        elif model == "microsoft":
            threading.Thread(target=self.microsoft_tts, daemon=True).start()
        elif model == "google":
            threading.Thread(target=self.google_tts, daemon=True).start()

    def init(self):
        self.logger.debug("Initialising TTS")
        return True

    def process(self, speech_text):
        self.text_queue.put(speech_text)

    def edge_tts(self):
        while True:
            speech_text = self.text_queue.get()
            self._cancel_flag.clear()
            
            self.edge_TTS_process = subprocess.Popen(
                [
                 'edge-tts', 
                 '--text', 
                 speech_text, 
                 '--voice', 
                 'en-GB-LibbyNeural'
                 ],
                stdout=subprocess.PIPE
            )
            
            self.ffmpeg_process = subprocess.Popen(
                [
                 'ffmpeg', 
                 '-i', 
                 'pipe:0', 
                 '-f', 
                 's16le', 
                 '-ar', 
                 str(self.fmt.rate), 
                 '-ac', 
                 '1', 
                 'pipe:1'
                 ],
                stdin=self.edge_TTS_process.stdout,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL
            )
            
            self.stream_reader()
    
    def microsoft_tts(self):
        #    Azure configuration for authentication and endpoint selection
        azure_key = ""
        region = ""
        
        url = f"https://{region}.tts.speech.microsoft.com/cognitiveservices/v1"
        headers = {
            "Ocp-Apim-Subscription-Key": azure_key,
            "Content-Type": "application/ssml+xml",
            "X-Microsoft-OutputFormat": "raw-16khz-16bit-mono-pcm", 
            "User-Agent": "SpeechBot"
        }

        while True:
            #    Get text from queue and reset cancel flag for new synthesis task
            speech_text = self.text_queue.get()
            self._cancel_flag.clear()
            
            #    Wrap text in SSML format required by Azure REST API
            ssml = f"<speak version='1.0' xml:lang='en-GB'><voice xml:lang='en-GB' name='en-GB-SoniaNeural'>{speech_text}</voice></speak>"
            
            try:
                #    Send POST request to Azure and stream the binary response content
                response = requests.post(url, headers=headers, data=ssml.encode('utf-8'), stream=True)
                response.raise_for_status()
                
                #    Init a buffer to hold incoming raw PCM data
                buffer = bytearray()
                
                #    Read stream in 1024 byte increments and process into chunks until completion or cancellation
                for raw_data in response.iter_content(chunk_size=1024):
                    if self._cancel_flag.is_set():
                        break
                        
                    buffer.extend(raw_data)
                    
                    #    Keep slicing off chunks from the buffer and putting them into the queue until we don't have enough for a full chunk
                    while len(buffer) >= self.bytes_per_chunk:
                        chunk = bytes(buffer[:self.bytes_per_chunk])
                        self.chunk_queue.put(chunk)
                        buffer = buffer[self.bytes_per_chunk:]
                        
                #    If end naturally reached without cancellation, signal completion with a special marker in the queue
                if not self._cancel_flag.is_set():
                    self.chunk_queue.put(b'DONE')
                    
            except Exception as e:
                self.logger.error(f"Azure TTS Error: {e}")

    def google_tts(self):
        from google.oauth2 import service_account
        from google.cloud import texttospeech

        gcp_credentials = {
        }

        credentials = service_account.Credentials.from_service_account_info(gcp_credentials)
        client = texttospeech.TextToSpeechClient(credentials=credentials)

        voice = texttospeech.VoiceSelectionParams(
            language_code="en-GB",
            name="en-GB-Chirp3-HD-Zephyr" 
        )

        streaming_config = texttospeech.StreamingSynthesizeConfig(
            voice=voice,
        )

        while True:
            speech_text = self.text_queue.get()
            self._cancel_flag.clear()

            def request_generator():
                yield texttospeech.StreamingSynthesizeRequest(
                    streaming_config=streaming_config
                )
                yield texttospeech.StreamingSynthesizeRequest(
                    input=texttospeech.StreamingSynthesisInput(text=speech_text)
                )

            try:
                responses = client.streaming_synthesize(request_generator())
                
                buffer = bytearray()
                
                for response in responses:
                    if self._cancel_flag.is_set():
                        break
                    
                    buffer.extend(response.audio_content)
                    
                    while len(buffer) >= self.bytes_per_chunk:
                        chunk = bytes(buffer[:self.bytes_per_chunk])
                        self.chunk_queue.put(chunk)
                        buffer = buffer[self.bytes_per_chunk:]
                        
                if not self._cancel_flag.is_set():
                    self.chunk_queue.put(b'DONE')

            except Exception as e:
                self.logger.error(f"Google TTS Error: {e}")

    
    def stream_reader(self):
        #    Init a buffer to hold incoming raw data until we have enough for a chunk
        buffer = bytearray()
        
        #   Read 1024 bytes at a time from FFmpeg's stdout, append to buffer, and once we have enough for a chunk, put it into chunk_queue (while checking for cancellation)
        while not self._cancel_flag.is_set():
            raw_data = self.ffmpeg_process.stdout.read(1024)
            if not raw_data: 
                break
            buffer.extend(raw_data)
            
            #    Keep slicing off chunks from the buffer and putting them into the queue until we don't have enough for a full chunk
            while len(buffer) >= self.bytes_per_chunk:
                chunk = bytes(buffer[:self.bytes_per_chunk])
                self.chunk_queue.put(chunk)
                buffer = buffer[self.bytes_per_chunk:]
        #    If end naturally reached without cancellation, signal completion with a special marker in the queue
        if not self._cancel_flag.is_set():
            self.chunk_queue.put(b'DONE')

    def get_chunk(self):
        try:
            chunk = self.chunk_queue.get(timeout=0.005)
            if chunk == b"DONE":
                return self.UTTERANCE_END
            return chunk
        except queue.Empty:
            return None

    def cancel(self):
        self._cancel_flag.set()
        
        while not self.text_queue.empty():
            try: 
                self.text_queue.get_nowait()
            except queue.Empty: 
                break
            
        if self.ffmpeg_process: 
            self.ffmpeg_process.terminate()
        if self.edge_TTS_process: 
            self.edge_TTS_process.terminate()
            
        while not self.chunk_queue.empty():
            try: 
                self.chunk_queue.get_nowait()
            except queue.Empty: 
                break

if __name__ == "__main__":
    init_logger()
    tts = TTS()
    tts.init()

    text = "Test speech"

    st = time.time()
    
    tts.process(text)
    first_chunk = tts.chunk_queue.get() 
    elapsed_time = time.time() - st
    
    if first_chunk == b'DONE':
        print(f"Stream finished instantly (or failed) in {elapsed_time:.4f} seconds")
    else:
        print(f"Got first chunk in: {elapsed_time:.4f} seconds")