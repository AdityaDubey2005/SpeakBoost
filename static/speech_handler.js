class SpeechHandler {
    constructor() {
        this.audioContext = new (window.AudioContext || window.webkitAudioContext)();
        this.mediaRecorder = null;
        this.audioChunks = [];
    }

    async startRecording() {
        try {
            const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
            this.mediaRecorder = new MediaRecorder(stream);
            this.audioChunks = [];

            this.mediaRecorder.ondataavailable = (event) => {
                this.audioChunks.push(event.data);
            };

            this.mediaRecorder.start();
        } catch (error) {
            console.error('Error starting recording:', error);
        }
    }

    stopRecording() {
        return new Promise((resolve) => {
            this.mediaRecorder.onstop = async () => {
                const audioBlob = new Blob(this.audioChunks, { type: 'audio/wav' });
                resolve(audioBlob);
            };
            this.mediaRecorder.stop();
        });
    }

    async playStreamedAudio(text, scenario) {
        try {
            const response = await fetch('/stream_audio', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ text, scenario })
            });

            if (!response.ok) {
                throw new Error('Audio streaming failed');
            }

            // Audio will play automatically through default speaker
            console.log('Audio streaming started');
        } catch (error) {
            console.error('Error playing audio:', error);
        }
    }
}

// Initialize the speech handler
const speechHandler = new SpeechHandler();