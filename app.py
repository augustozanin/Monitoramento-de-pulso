from flask import Flask, render_template_string, jsonify, make_response
import serial
import threading
import time
from twilio.rest import Client
import os
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

# Variáveis globais protegidas por lock
pulse_status = "Sem pulso"
pulse_color = "red"
last_pulse = 0
pulse_lock = threading.Lock()
serial_lock = threading.Lock()

# Configurações do Twilio
TWILIO_ACCOUNT_SID = os.getenv('TWILIO_ACCOUNT_SID')
TWILIO_AUTH_TOKEN = os.getenv('TWILIO_AUTH_TOKEN')
TWILIO_PHONE_NUMBER = os.getenv('TWILIO_PHONE_NUMBER')
DESTINATION_PHONE_NUMBER = os.getenv('DESTINATION_PHONE_NUMBER')


# Variável para controlar o envio de alertas
last_alert_time = 0
ALERT_COOLDOWN = 300  # 5 minutos entre alertas

# Inicializa o cliente Twilio
twilio_client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)

def send_emergency_alert():
    global last_alert_time
    
    current_time = time.time()
    if current_time - last_alert_time > ALERT_COOLDOWN:
        try:
            message = twilio_client.messages.create(
                body="ALERTA MÉDICO: Paciente sem pulso detectado! Verifique imediatamente!",
                from_=TWILIO_PHONE_NUMBER,
                to=DESTINATION_PHONE_NUMBER
            )
            print(f"Alerta enviado com sucesso: {message.sid}")
            last_alert_time = current_time
        except Exception as e:
            print(f"Erro ao enviar alerta: {str(e)}")

def read_serial():
    global pulse_status, pulse_color, last_pulse
    arduino = None
    
    while True:
        try:
            with serial_lock:
                if arduino is None or not arduino.is_open:
                    arduino = serial.Serial('/dev/ttyACM0', 9600, timeout=1.1)
                    time.sleep(2)
                    arduino.reset_input_buffer()
                    print("Conectado à porta serial. Monitorando...")

                while arduino.in_waiting > 0:
                    raw_data = arduino.readline()
                    
                    try:
                        data = raw_data.decode('utf-8').strip()
                        if data:
                            pulse = int(data)
                            print(f"Pulso recebido: {pulse}")
                            
                            with pulse_lock:
                                if pulse == 1:
                                    pulse_status = "PULSO DETECTADO!"
                                    pulse_color = "#00FF00"
                                else:
                                    pulse_status = "SEM PULSO"
                                    pulse_color = "#FF0000"
                                    send_emergency_alert()
                                
                                last_pulse = pulse
                    except (UnicodeDecodeError, ValueError) as e:
                        print(f"Erro nos dados: {raw_data}")
                
                time.sleep(0.05)

        except serial.SerialException as e:
            print(f"ERRO SERIAL: {str(e)}")
            with pulse_lock:
                pulse_status = "Erro serial"
                pulse_color = "#FFA500"
            
            if arduino and arduino.is_open:
                arduino.close()
                arduino = None
            
            time.sleep(2)

serial_thread = threading.Thread(target=read_serial)
serial_thread.daemon = True
serial_thread.start()

@app.route('/')
def dashboard():
    html = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Monitoramento de Pulso</title>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <style>
            body {
                font-family: 'Arial Black', Arial, sans-serif;
                text-align: center;
                background-color: #f5f5f5;
                margin: 0;
                padding: 0;
                height: 100vh;
                display: flex;
                flex-direction: column;
                justify-content: center;
                align-items: center;
            }
            h1 {
                font-size: 3rem;
                color: #333;
                margin-bottom: 2rem;
                text-shadow: 2px 2px 4px rgba(0,0,0,0.1);
            }
            .pulse-container {
                display: flex;
                flex-direction: column;
                align-items: center;
                justify-content: center;
                width: 100%;
            }
            .circle {
                width: 300px;
                height: 300px;
                border-radius: 50%;
                background-color: white;
                box-shadow: 0 0 50px {{ color }}, inset 0 0 20px rgba(0,0,0,0.1);
                display: flex;
                align-items: center;
                justify-content: center;
                font-size: 2rem;
                font-weight: bold;
                color: #333;
                margin-bottom: 2rem;
                transition: all 0.3s ease;
            }
            .status-text {
                font-size: 1.8rem;
                font-weight: bold;
                color: #444;
                margin-top: 1rem;
            }
            @keyframes pulse {
                0% { transform: scale(1); }
                50% { transform: scale(1.1); }
                100% { transform: scale(1); }
            }
        </style>
    </head>
    <body>
        <h1>MONITORAMENTO DE PULSO</h1>
        <div class="pulse-container">
            <div class="circle" id="pulseCircle" style="box-shadow: 0 0 50px {{ color }}">{{ status }}</div>
            <div class="status-text">Status: <span id="statusText">{{ status }}</span></div>
        </div>
        <script>
            async function updatePulse() {
                try {
                    const response = await fetch('/pulse_status');
                    if (!response.ok) throw new Error('Erro na rede');
                    const data = await response.json();

                    const circle = document.getElementById("pulseCircle");
                    const statusText = document.getElementById("statusText");

                    if (circle.textContent !== data.status) {
                        circle.textContent = data.status;
                        circle.style.boxShadow = `0 0 50px ${data.color}`;
                        statusText.textContent = data.status;
                        
                        if (data.status === "PULSO DETECTADO!") {
                            circle.style.animation = "pulse 0.5s";
                            setTimeout(() => circle.style.animation = "", 500);
                        }
                    }
                } catch (error) {
                    console.error("Erro ao atualizar:", error);
                }
            }
            setInterval(updatePulse, 250);
            document.addEventListener('DOMContentLoaded', updatePulse);
        </script>
    </body>
    </html>
    """
    with pulse_lock:
        return render_template_string(html, status=pulse_status, color=pulse_color)

@app.route('/pulse_status')
def get_pulse_status():
    with pulse_lock:
        return jsonify({
            "status": pulse_status,
            "color": pulse_color
        })

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False, use_reloader=False)