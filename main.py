import base64
import json
import os
from flask import Flask, request, Response
from flask_sock import Sock
import ngrok
from twilio.rest import Client
from dotenv import load_dotenv

load_dotenv()

from twilio_transcriber import TwilioTranscriber

PORT = 5000
DEBUG = False
INCOMING_CALL_ROUTE = '/'
WEBSOCKET_ROUTE = '/'

account_sid = os.environ['TWILIO_ACCOUNT_SID']
api_key = os.environ['TWILIO_API_KEY_SID']
api_secret = os.environ['TWILIO_API_SECRET']
client = Client(api_key, api_secret, account_sid)

TWILIO_NUMBER = os.environ['TWILIO_NUMBER']

ngrok.set_auth_token(os.getenv("NGROK_AUTHTOKEN"))
app = Flask(__name__)
sock = Sock(app)

@app.route(INCOMING_CALL_ROUTE, methods=['GET', 'POST'])
def receive_call():
    if request.method == 'POST':
        xml = f"""
            <Response>
                <Say>
                    Speak to see your speech transcribed in the console
                </Say>
                <Connect>
                    <Stream url='wss://{request.host}{WEBSOCKET_ROUTE}' />
                </Connect>
            </Response>
            """.strip()
        return Response(xml, mimetype='text/xml')
    else:
        return f"Real-time phone call transcription app"

@sock.route(WEBSOCKET_ROUTE)
def transcription_websocket(ws):
    transcriber = None
    
    try:
        while True:
            data = json.loads(ws.receive())
            match data['event']:
                case "connected":
                    print('Twilio connected, starting transcriber...')
                    transcriber = TwilioTranscriber()
                    transcriber.start_transcription()
                case "start":
                    print('Call started')
                case "media": 
                    if transcriber:
                        payload_b64 = data['media']['payload']
                        payload_mulaw = base64.b64decode(payload_b64)
                        transcriber.stream_audio(payload_mulaw)
                case "stop":
                    print('Call ended')
                    if transcriber:
                        transcriber.stop_transcription()
                    break
    except Exception as e:
        print(f"Error in websocket: {e}")
        import traceback
        traceback.print_exc()
    finally:
        if transcriber:
            try:
                transcriber.stop_transcription()
            except Exception as cleanup_error:
                print(f"Cleanup error: {cleanup_error}")


if __name__ == "__main__":
    try:
        listener = ngrok.forward(f"http://localhost:{PORT}")
        print(f"Ngrok tunnel opened at {listener.url()} for port {PORT}")
        NGROK_URL = listener.url()

        twilio_numbers = client.incoming_phone_numbers.list()
        twilio_number_sid = [num.sid for num in twilio_numbers if num.phone_number == TWILIO_NUMBER][0]
        client.incoming_phone_numbers(twilio_number_sid).update(account_sid, voice_url=f"{NGROK_URL}{INCOMING_CALL_ROUTE}")

        app.run(port=PORT, debug=DEBUG)
    finally:
        ngrok.disconnect()