from pippi import dsp
from pippi import tune
import alsaaudio
import sys
import time

def play(params={}):

    length = params.get('length', dsp.stf(2))
    volume = params.get('volume', 100.0)
    volume = volume / 100.0 # TODO: move into param filter
    width = params.get('width', 50)
    measures = params.get('multiple', 1)
    beats = params.get('repeats', 8)
    bpm = params.get('bpm', 75.0)
    glitch = params.get('glitch', False)
    alias = params.get('alias', False)
    skitter = params.get('skitter', False)
    bend = params.get('bend', True)
    tweet = params.get('tweet', False)
    pattern = params.get('pattern', True)
    playdrums = params.get('drum', ['k', 'h', 'c'])
    pinecone = params.get('pinecone', False)
    insamp = params.get('rec', False)
    roll = params.get('roll', False)

    drums = [{
        'name': 'clap',
        'shortname': 'c',
        'snd': dsp.read('sounds/lowpaperclips.wav').data if insamp is False else dsp.capture(dsp.mstf(500)),
        'pat': [0, 0, 1, 0],
        'vary': [0, 1, 0, 0],
        'offset': 0,
        'width': 0.6,
        }, {
        'name': 'hihat',
        'shortname': 'h',
        'snd': dsp.read('sounds/paperclips.wav').data,
        'pat': [[1, 1]],
        'vary': [1, [1, 1]],
        'offset': 400,
        'width': 0.05,
        }, {
        'name': 'snare',
        'shortname': 's',
        'snd': dsp.read('sounds/lowpaperclips.wav').data,
        'pat': [1, 0, 1, 0],
        'vary': [0, 0, 1, 1],
        'offset': 500,
        'width': 0.1,
        }, {
        'name': 'kick',
        'shortname': 'k',
        'snd': dsp.read('sounds/lowpaperclips2.wav').data,
        'pat': [1, 0, 1, 0, 0, 0, 0, 0],
        'vary': [0, 0, 1, 0, 0, 1, 0, 0, 0, 0, 1, 0],
        'offset': 0,
        'width': 0.4,
        }]


    wtypes = ['sine', 'phasor', 'line', 'saw']

    out = ''

    beats = beats * measures

    beat = dsp.mstf(60000.0 / bpm) / 4
    width = int(beat * (width / 100.0))

    def tweeter(o):
        o = dsp.split(o, dsp.randint(3,6))
        oo = dsp.randchoose(o)
        o = [ dsp.env(oo, dsp.randchoose(wtypes)) for h in range(len(o)) ]
        return dsp.env(''.join(o), dsp.randchoose(wtypes))


    def kickit(snd):
        out = ''
        for b in range(beats):
            s = dsp.cut(snd['snd'], dsp.randint(0, snd['offset']), width)

            if alias == True:
                s = dsp.alias(s)

            if bend == True:
                s = dsp.transpose(s, dsp.rand(-0.4, 0.4) + 1)

            if skitter == True:
                prebeat = dsp.mstf(dsp.randint(10, 400))
            else:
                prebeat = 0

            if tweet == True:
                s = tweeter(s)

            #if roll is True:
                #if dsp.randint(0, 3) == 0:
                    #s = dsp.split(s, dsp.flen(s) / 2)
                    #s = ''.join([ dsp.amp(s[0], dsp.rand(0.7, 1.0)) for bit in range(beat / dsp.flen(s[0])) ])
            #else:
            s = dsp.pad(s, prebeat, beat - dsp.flen(s))

            if pattern == True:
                if dsp.randint(0,3) == 0:
                    amp = snd['vary'][b % len(snd['vary'])]
                else:
                    amp = snd['pat'][b % len(snd['pat'])]
            else:
                amp = 1.0

            if amp == 1:
                out += s
            elif amp == [1,1]:
                out += dsp.cut(s, 0, dsp.flen(s) / 2) * 2
            elif amp == [0,1]:
                out += dsp.pad(dsp.cut(s, 0, dsp.flen(s) / 2), dsp.flen(s) / 2, 0) 
            elif amp == [1,0]:
                out += dsp.pad(dsp.cut(s, 0, dsp.flen(s) / 2), 0, dsp.flen(s) / 2) 
            else:
                out += dsp.pad('', 0, beat)



        return out

    layers = []
    for drum in drums:
        if drum['shortname'] in playdrums:
            layers += [ kickit(drum) ]

    out = dsp.mix(layers)

    if glitch == True:
        out = dsp.split(out, int(beat * 0.5))
        for i,o in enumerate(out):
            if i % 5 == 0 and dsp.randint(0,1) == 0:
                out[i] = tweeter(o)

        out = ''.join(dsp.randshuffle(out))

    if pinecone == True:
        # Do it in packets
        # Start from position P, take sample of N length (audio rates), apply envelope, move to position P + Q, repeat
        pminlen = dsp.mstf(1)
        pmaxlen = dsp.mstf(500)
        pnum = dsp.randint(3, 5)
        pinecones = []
        for p in range(pnum):
            segment = dsp.cut(out, dsp.randint(0, dsp.flen(out) - pmaxlen), dsp.randint(pminlen, pmaxlen))
            pskip = dsp.flen(segment) / dsp.randint(30, 500) + 1 
            ppos = 0
            pupp = 5000 if dsp.randint(0, 2) == 0 else 50
            plen = dsp.htf(dsp.rand(5, pupp))
            while ppos + pskip + 400 < pmaxlen:
                p = dsp.cut(segment, ppos + dsp.randint(0, 200), plen + dsp.randint(0, 200))
                p = dsp.env(p, 'random', True, dsp.rand(0.8, 1.0), 0.0)
                pinecones += [ p ]
                ppos += pskip

        out = dsp.pan(''.join(pinecones), dsp.rand())


    #out = dsp.pan(out, 1)

    if roll == True:
        out = dsp.split(out, dsp.flen(out) / (measures * 16))
        out = dsp.randshuffle(out)
        out = ''.join(out)

    return dsp.amp(out, volume)
