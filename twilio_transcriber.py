import os
import threading
from typing import Type
import assemblyai as aai
from assemblyai.streaming.v3 import (
    BeginEvent,
    StreamingClient,
    StreamingClientOptions,
    StreamingError,
    StreamingEvents,
    StreamingParameters,
    TerminationEvent,
    TurnEvent,
)
from dotenv import load_dotenv
load_dotenv()

aai.settings.api_key = os.getenv('ASSEMBLYAI_API_KEY')

TWILIO_SAMPLE_RATE = 8000
BUFFER_SIZE_MS = 100 
BYTES_PER_MS = TWILIO_SAMPLE_RATE // 1000


class TranscriptDisplay:
    def __init__(self):
        self.current_partial = ""
        self.lock = threading.Lock()
        self.current_line_printed = False
    
    def update_partial(self, text):
        """Update the current partial transcript"""
        with self.lock:
            self.current_partial = text
            self._display_partial()
    
    def add_final(self, text):
        """Add final transcript as a new line"""
        with self.lock:
            if self.current_partial:
                print("\r" + " " * (len(self.current_partial) + 20) + "\r", end="", flush=True)
            
            print(f"{text}")
            
            self.current_partial = ""
            self.current_line_printed = False
    
    def _display_partial(self):
        """Display the current partial transcript on the same line"""
        print("\r" + " " * 100 + "\r", end="", flush=True)
        if self.current_partial:
            print(f"{self.current_partial}", end="", flush=True)


transcript_display = TranscriptDisplay()


def on_begin(client: StreamingClient, event: BeginEvent):
    print(f"Session ID: {event.id}\n")

def on_turn(client: StreamingClient, event: TurnEvent):
    if event.transcript.strip():
        is_formatted = hasattr(event, 'turn_is_formatted') and event.turn_is_formatted
        
        if is_formatted:
            transcript_display.add_final(event.transcript)
        elif event.end_of_turn:
            pass
        else:
            transcript_display.update_partial(event.transcript)

def on_terminated(client: StreamingClient, event: TerminationEvent):
    print(f"\nSession ended - {event.audio_duration_seconds} seconds processed")

def on_error(client: StreamingClient, error: StreamingError):
    print(f"\nError: {error}")

    
class TwilioTranscriber(StreamingClient):
    def __init__(self):
        options = StreamingClientOptions(
            api_key=aai.settings.api_key,
            api_host="streaming.assemblyai.com"
        )
        
        super().__init__(options)
        
        self.on(StreamingEvents.Begin, on_begin)
        self.on(StreamingEvents.Turn, on_turn)  
        self.on(StreamingEvents.Termination, on_terminated)
        self.on(StreamingEvents.Error, on_error)
        
        self.audio_buffer = bytearray()
        self.buffer_size_bytes = BUFFER_SIZE_MS * BYTES_PER_MS  # 100ms of audio (800 bytes)
        self.buffer_lock = threading.Lock()
        self.is_active = False
        
        global transcript_display
        transcript_display = TranscriptDisplay()
    
    def start_transcription(self):
        """Start the transcription session"""
        params = StreamingParameters(
            sample_rate=TWILIO_SAMPLE_RATE,
            encoding=aai.AudioEncoding.pcm_mulaw,
            format_turns=True
        )
        self.is_active = True
        self.connect(params)
    
    def stream_audio(self, audio_data: bytes):
        """Buffer and stream audio data to AssemblyAI"""
        if not self.is_active:
            return
            
        with self.buffer_lock:
            self.audio_buffer.extend(audio_data)
            
            if len(self.audio_buffer) >= self.buffer_size_bytes:
                self._flush_buffer()
    
    def _flush_buffer(self):
        """Send buffered audio to AssemblyAI"""
        if len(self.audio_buffer) > 0:
            buffered_audio = bytes(self.audio_buffer)
            try:
                self.stream(buffered_audio)
            except Exception as e:
                print(f"\nError sending audio: {e}")
            
            self.audio_buffer.clear()
    
    def stop_transcription(self):
        """Stop the transcription and clean up"""
        self.is_active = False
        
        with self.buffer_lock:
            if len(self.audio_buffer) > 0:
                self._flush_buffer()
        
        self.disconnect(terminate=True)