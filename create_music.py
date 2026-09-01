"""Genera pistas WAV sintéticas. Ejecutar una sola vez: python create_music.py"""
import wave, struct, math, os

OUT = os.path.join(os.path.dirname(__file__), 'static', 'music')
os.makedirs(OUT, exist_ok=True)
RATE, DUR = 44100, 90

def wav(path, samples):
    with wave.open(path, 'w') as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(RATE)
        for s in samples:
            w.writeframes(struct.pack('<h', int(max(-32767, min(32767, s * 32767)))))

def s(f, t, a=0.3):
    return a * math.sin(2 * math.pi * f * t)

def cinematic():
    chords = [(130.81,164.81,196.0),(123.47,155.56,185.0),(146.83,184.99,220.0),(138.59,174.61,207.65)]
    S = []
    for i in range(RATE * DUR):
        t = i / RATE
        env = min(1.0, t * 0.3, (DUR - t) * 0.5)
        f1, f2, f3 = chords[int(t / 8) % len(chords)]
        S.append((s(f1,t,0.18) + s(f2,t,0.14) + s(f3,t,0.10)) * env)
    wav(f'{OUT}/cinematic.wav', S); print('  ✓ cinematic.wav')

def upbeat():
    notes = [261.63, 329.63, 392.0, 523.25, 392.0, 329.63]
    S = []
    for i in range(RATE * DUR):
        t = i / RATE
        env = min(1.0, t * 2, (DUR - t) * 2)
        f = notes[int(t * 2) % len(notes)]
        S.append(s(f, t, 0.25 * env) + s(f*2, t, 0.05 * env))
    wav(f'{OUT}/upbeat.wav', S); print('  ✓ upbeat.wav')

def luxury():
    melody = [392.0, 440.0, 493.88, 523.25, 493.88, 440.0, 392.0, 349.23]
    S = []
    for i in range(RATE * DUR):
        t = i / RATE
        env = min(1.0, t * 1.5, (DUR - t) * 1.5)
        f = melody[int(t * 0.75) % len(melody)]
        decay = math.exp(-((t % 1.33) * 2.5))
        S.append(s(f, t, 0.2 * env * decay) + s(220, t, 0.06 * env))
    wav(f'{OUT}/luxury.wav', S); print('  ✓ luxury.wav')

if __name__ == '__main__':
    print('Generando pistas de música...')
    cinematic(); upbeat(); luxury()
    print('Listo → static/music/')
