"""Build the bundled, wet-only close-mic doctor's-office response. No voice input."""
from pathlib import Path
import wave

import numpy as np


def build(target):
    rate=48000
    count=round(rate*.24)
    response=np.zeros((count,2),dtype=np.float64)
    rng=np.random.default_rng(20261111)
    # Small furnished office: uneven, diffused wall/desk/ceiling reflections.
    # Every reflection is spread over a short cluster to avoid a second clear voice.
    for delay,level,width,pan in [(8.1,.40,5.2,.18),(12.7,.38,6.2,-.16),
                                 (17.8,.32,7.0,.12),(24.3,.27,8.0,-.09),
                                 (32.6,.20,10.5,.07),(45.1,.12,13.0,-.05)]:
        size=round(width/1000*rate)
        burst=rng.standard_normal(size)*np.hanning(size)
        start=round(delay/1000*rate)
        for channel,balance in enumerate((1-pan,1+pan)):
            response[start:start+size,channel]+=burst*level*balance
    # Upholstery and cabinets give a dense, quiet tail with a deliberately short decay.
    t=np.arange(count)/rate
    envelope=np.where(t>.025,np.exp(-np.maximum(0,t-.025)/.020),0)
    diffuse=rng.standard_normal((count,2))*.09
    response+=diffuse*envelope[:,None]
    # Absorb bass and sibilance in the reflected path while leaving the dry voice intact.
    frequency=np.fft.rfftfreq(count,1/rate)
    damping=(frequency**2/(frequency**2+240**2))/(1+(frequency/3900)**4)
    response=np.fft.irfft(np.fft.rfft(response,axis=0)*damping[:,None],n=count,axis=0)
    response[:round(rate*.006)]=0
    response[-round(rate*.04):]*=np.linspace(1,0,round(rate*.04))[:,None]
    response/=np.sqrt(np.sum(response*response)/2)
    pcm=np.round(response*32767).astype('<i2')
    target.parent.mkdir(parents=True,exist_ok=True)
    with wave.open(str(target),'wb') as out:
        out.setnchannels(2);out.setsampwidth(2);out.setframerate(rate);out.writeframes(pcm.tobytes())


if __name__=='__main__':
    build(Path(__file__).resolve().parents[1]/'backend/resources/voice-rooms/office.wav')
